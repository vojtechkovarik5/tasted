from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.domain.dish import Allergen, DietaryFlag, DishInfo, Ingredient
from app.domain.preferences import Language

# (kind, key) -> localized display name; built by TrackableService.labels.
Labels = dict[tuple[str, str], str]


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    source: str  # user | ai


class VariantOut(BaseModel):
    """One variant chip on the family page ("Gai · chicken"). Facets, not
    separate pages; the client highlights the one the menu item matched."""

    id: uuid.UUID
    key: str
    name: str
    description: str | None = None


class DishOut(BaseModel):
    """One canonical dish FAMILY as returned by the API.

    The prose in `info` is resolved to the requested language from the
    stored translations, falling back to English; allergen/dietary/ingredient
    labels are localized from the trackables catalog the same way.
    """

    id: uuid.UUID
    canonical_name: str
    region: str | None = None
    info: DishInfo
    photos: list[PhotoOut] = []
    variants: list[VariantOut] = []

    @classmethod
    def from_orm_dish(
        cls,
        dish,
        *,
        language: Language = Language.en,
        labels: Labels | None = None,
    ) -> DishOut:
        info = DishInfo.model_validate(dish.data)
        # Stored translation of the prose, English (the base fields) fallback.
        translation = info.translation_for(language.value)
        if translation is not None:
            info.summary = translation.summary or info.summary
            info.description = translation.description or info.description
        info.translations = []  # resolved above — don't ship every language

        def label(kind: str, key: str) -> str | None:
            return labels.get((kind, key)) if labels else None

        # Scored fields come from dish_attributes (0-100 ints, vote-adjusted),
        # not from the descriptive JSONB payload.
        allergens: list[Allergen] = []
        dietary: list[DietaryFlag] = []
        ingredients: list[Ingredient] = []
        for attr in dish.attributes:
            if attr.kind == "allergen":
                allergens.append(
                    Allergen(
                        name=attr.key,
                        probability=attr.value / 100,
                        label=label("allergen", attr.key),
                    )
                )
            elif attr.kind == "dietary":
                dietary.append(
                    DietaryFlag(
                        name=attr.key,
                        probability=attr.value / 100,
                        label=label("dietary", attr.key),
                    )
                )
            elif attr.kind == "ingredient":
                ingredients.append(
                    Ingredient(
                        name=attr.key,
                        probability=attr.value / 100,
                        label=label("ingredient", attr.key),
                    )
                )
            elif attr.kind == "spice":
                info.spice_level = attr.value / 20
            elif attr.kind == "price":
                info.price_level = attr.value / 20
        info.allergens = allergens
        info.dietary = dietary
        info.ingredients = sorted(ingredients, key=lambda i: -i.probability)
        return cls(
            id=dish.id,
            canonical_name=dish.canonical_name,
            region=dish.region,
            info=info,
            # Only moderated photos are public; user uploads sit in
            # pending_moderation until a moderation pass flips them.
            photos=[PhotoOut.model_validate(p) for p in dish.photos if p.status == "active"],
            variants=[
                VariantOut(
                    id=v.id,
                    key=v.key,
                    name=_variant_name(v, language),
                    description=v.description,
                )
                for v in dish.variants
            ],
        )


def _variant_name(variant, language: Language) -> str:
    entry = (variant.translations or {}).get(language.value) or {}
    return entry.get("name") or variant.name


def attribute_label_pairs(dish) -> set[tuple[str, str]]:
    """The (kind, key) pairs a dish's DishOut needs localized — feed to
    TrackableService.labels (batchable across a whole menu)."""
    return {
        (attr.kind, attr.key)
        for attr in dish.attributes
        if attr.kind in ("allergen", "dietary", "ingredient")
    }
