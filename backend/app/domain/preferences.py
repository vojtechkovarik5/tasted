from pydantic import BaseModel

# Mirrors User.prefs (JSONB) — the device is the source of truth (MMKV),
# this is the sync payload once the user is logged in. Last-write-wins.


class WatchChip(BaseModel):
    """One chip in the "Watch out for" list. Order in the list matters."""

    key: str  # "gluten", "vegetarian", "pork", ...
    kind: str  # "allergen" | "dietary"
    on: bool = True


class Preferences(BaseModel):
    """User preferences (Profile screen). Works locally without an account."""

    # One ordered list — allergens, diets, whole categories or exact meats.
    watch_list: list[WatchChip] = [
        WatchChip(key="gluten", kind="allergen"),
        WatchChip(key="vegetarian", kind="dietary"),
    ]
    # Which macros to show on cards: "protein" | "fat" | "carbs" | "kcal".
    macros: list[str] = ["protein", "fat"]
    # Badge order on every card: "restrictions" | "macros" | "spice_price".
    section_order: list[str] = ["restrictions", "macros", "spice_price"]
    # ISO 4217 — original menu prices get an approximate conversion to this.
    currency: str = "CZK"
