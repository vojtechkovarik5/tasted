"""Fixed parts of the "What I track" catalog.

The 14 EU allergens and the diet-fit flags are seeded into the `trackables`
table by migration and never suggestable; ingredients grow organically (AI
ingest + user suggestions). These constants are the single source for the
seed, the prompts (canonical slugs the models must use) and validation.
"""

# key -> English display name. Slugs are what the AI pipeline and the
# preferences watch_list speak; display names are localized via trackables.
EU_ALLERGENS: dict[str, str] = {
    "gluten": "gluten",
    "crustaceans": "crustaceans",
    "egg": "egg",
    "fish": "fish",
    "peanuts": "peanuts",
    "soy": "soy",
    "milk": "milk",
    "nuts": "tree nuts",
    "celery": "celery",
    "mustard": "mustard",
    "sesame": "sesame",
    "sulphites": "sulphites",
    "lupin": "lupin",
    "molluscs": "molluscs",
}

# Diet-fit flags: share of versions of a dish worldwide that fit each one.
# Users can track any of these; more can be suggested (pending) by users.
DIET_FLAGS: dict[str, str] = {
    "vegetarian": "vegetarian",
    "vegan": "vegan",
    "meat": "meat",
    "fish-seafood": "fish/seafood",
    "raw": "raw",
    "fried": "fried",
    "halal": "halal",
    "kosher": "kosher",
}


def slugify(name: str) -> str:
    """Canonical trackables slug from a free-form (English) name:
    lowercase, hyphenated, ascii-ish. "Rice noodles" -> "rice-noodles"."""
    cleaned = "".join(c if c.isalnum() or c in " -" else " " for c in name.strip().lower())
    return "-".join(part for part in cleaned.split() if part)[:64]
