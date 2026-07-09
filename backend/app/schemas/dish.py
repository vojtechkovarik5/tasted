from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.domain.dish import Allergen, DietaryFlag, DishInfo


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    source: str  # user | ai


class DishOut(BaseModel):
    """Dish as returned by the API."""

    id: uuid.UUID
    canonical_name: str
    region: str | None = None
    info: DishInfo
    photos: list[PhotoOut] = []

    @classmethod
    def from_orm_dish(cls, dish) -> DishOut:
        info = DishInfo.model_validate(dish.data)
        # Scored fields come from dish_attributes (0-100 ints, vote-adjusted),
        # not from the descriptive JSONB payload.
        allergens: list[Allergen] = []
        dietary: list[DietaryFlag] = []
        for attr in dish.attributes:
            if attr.kind == "allergen":
                allergens.append(Allergen(name=attr.key, probability=attr.value / 100))
            elif attr.kind == "dietary":
                dietary.append(DietaryFlag(name=attr.key, probability=attr.value / 100))
            elif attr.kind == "spice":
                info.spice_level = attr.value / 20
            elif attr.kind == "price":
                info.price_level = attr.value / 20
        info.allergens = allergens
        info.dietary = dietary
        return cls(
            id=dish.id,
            canonical_name=dish.canonical_name,
            region=dish.region,
            info=info,
            # Only moderated photos are public; user uploads sit in
            # pending_moderation until a moderation pass flips them.
            photos=[PhotoOut.model_validate(p) for p in dish.photos if p.status == "active"],
        )
