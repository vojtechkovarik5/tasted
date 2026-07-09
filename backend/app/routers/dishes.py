import uuid

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth import CurrentUserDep
from app.schemas import DishOut, VoteAck, VoteDirection, VoteTarget
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
    direction flips it. The client nudges optimistically and reconciles from
    the next dish/menu fetch, so only an ack is returned.
    """
    direction = 1 if body.direction == VoteDirection.up else -1
    value = await service.vote(dish_id, user_id, target.value, direction)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dish not found")
    return VoteAck()


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
