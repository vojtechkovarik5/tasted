import uuid

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import CurrentUserDep
from app.schemas import DishOut, MyVotesOut, VoteAck, VoteDirection, VoteTarget
from app.services.dishes import DishServiceDep

router = APIRouter(prefix="/dishes", tags=["dishes"])

# NOTE: there is deliberately no GET /dishes (list) or POST /dishes here —
# the app always reaches dishes through a menu; creation happens inside the
# AI ingest pipeline, not over the public API.


class VoteBody(BaseModel):
    direction: VoteDirection  # "up" | "down"


class PhotoAck(BaseModel):
    accepted: bool = True
    status: str = "pending_moderation"


@router.get("/{dish_id}", response_model=DishOut)
async def get_dish(dish_id: uuid.UUID, service: DishServiceDep) -> DishOut:
    """Dish detail (canonical cached dish, moderated photos included)."""
    dish = await service.get(dish_id)
    if dish is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dish not found")
    return DishOut.from_orm_dish(dish)


@router.post("/{dish_id}/vote/{target}", response_model=VoteAck)
async def vote(
    dish_id: uuid.UUID,
    target: VoteTarget,  # "spice" | "price" — the only votable attributes
    body: VoteBody,
    user_id: CurrentUserDep,
    service: DishServiceDep,
) -> VoteAck:
    """Nudge the dish's spice or price level.

    One vote per user per attribute — a repeat is idempotent, the opposite
    direction flips it. The displayed level doesn't move right away (votes
    are folded in by periodic recalculation), so the client only marks the
    pressed arrow; GET /dishes/{id}/votes restores that mark across reloads.
    """
    direction = 1 if body.direction == VoteDirection.up else -1
    value = await service.vote(dish_id, user_id, target.value, direction)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dish not found")
    return VoteAck()


@router.get("/{dish_id}/votes", response_model=MyVotesOut)
async def my_votes(
    dish_id: uuid.UUID, user_id: CurrentUserDep, service: DishServiceDep
) -> MyVotesOut:
    """The current user's standing spice/price votes on this dish — lets the
    UI show "you already voted" (and which way) after a reload."""
    votes = await service.my_votes(dish_id, user_id)
    if votes is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dish not found")

    def to_direction(direction: int | None) -> VoteDirection | None:
        if direction is None:
            return None
        return VoteDirection.up if direction > 0 else VoteDirection.down

    return MyVotesOut(
        spice=to_direction(votes.get("spice")), price=to_direction(votes.get("price"))
    )


@router.post("/{dish_id}/photo", response_model=PhotoAck)
async def upload_photo(
    dish_id: uuid.UUID,
    photo: UploadFile,
    user_id: CurrentUserDep,
    service: DishServiceDep,
) -> PhotoAck:
    """Upload a user photo of the dish.

    Stored to object storage right away, but hidden from API responses until
    a moderation pass flips its status to `active`.
    """
    if photo.content_type and not photo.content_type.startswith("image/"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Expected an image upload")
    stored = await service.add_user_photo(dish_id, await photo.read(), photo.content_type)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dish not found")
    return PhotoAck()
