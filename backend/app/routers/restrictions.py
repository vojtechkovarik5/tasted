from fastapi import APIRouter

from app.auth import CurrentUserDep
from app.services.users import UserServiceDep

router = APIRouter(tags=["restrictions"])

# User-scoped watch lists (the "What I track" chips), split by kind:
#   /restrictions -> allergens (fixed EU-14 keys: "gluten", "peanuts")
#   /dietary      -> diet flags the user follows ("vegetarian", "halal")
#   /ingredients  -> tracked ingredients ("coriander", "olives")
# POST replaces the whole list for its kind (the chips UI always knows the
# full set). All are views over prefs.watch_list, so they stay in sync with
# the PUT /preferences payload the profile screen sends.


@router.get("/restrictions", response_model=list[str])
async def get_restrictions(user_id: CurrentUserDep, users: UserServiceDep) -> list[str]:
    return await users.get_watch_keys(user_id, "allergen")


@router.post("/restrictions", response_model=list[str])
async def set_restrictions(
    keys: list[str], user_id: CurrentUserDep, users: UserServiceDep
) -> list[str]:
    return await users.set_watch_keys(user_id, "allergen", keys)


@router.get("/dietary", response_model=list[str])
async def get_dietary(user_id: CurrentUserDep, users: UserServiceDep) -> list[str]:
    return await users.get_watch_keys(user_id, "dietary")


@router.post("/dietary", response_model=list[str])
async def set_dietary(
    keys: list[str], user_id: CurrentUserDep, users: UserServiceDep
) -> list[str]:
    return await users.set_watch_keys(user_id, "dietary", keys)


@router.get("/ingredients", response_model=list[str])
async def get_ingredients(user_id: CurrentUserDep, users: UserServiceDep) -> list[str]:
    return await users.get_watch_keys(user_id, "ingredient")


@router.post("/ingredients", response_model=list[str])
async def set_ingredients(
    keys: list[str], user_id: CurrentUserDep, users: UserServiceDep
) -> list[str]:
    return await users.set_watch_keys(user_id, "ingredient", keys)
