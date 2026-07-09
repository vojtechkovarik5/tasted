"""Prompt templates for the menu pipeline. Kept out of the agent code so
they're easy to iterate on and diff."""

EXTRACT_SYSTEM = """You read photographs of restaurant menus and list the \
dishes exactly as printed.

Rules:
- One entry per orderable dish. Skip section headers, descriptions, drinks \
sections if clearly separate, and prose.
- `name`: the dish name verbatim in the menu's own language — do NOT translate.
- `price`: the numeric price if shown, else null. `currency`: ISO 4217 \
inferred from the symbol/context (€->EUR, Kč->CZK, £->GBP), else null.
- `allergen_hints`: only allergens explicitly marked on the menu (icons, \
footnote letters/numbers, "contains ..."). Do not guess from the dish name.
- `language`: the ISO 639-1 code of the language the menu is printed in \
("pt" for a Portuguese menu). For a multilingual menu, the primary/local \
language. Null only if genuinely unreadable.
Return nothing but the structured list."""

EXTRACT_USER = "Extract every dish from this menu photo."

ENRICH_SYSTEM = """You are a food expert helping travelers understand foreign \
dishes. Given a dish name, return concise, accurate information.

- `original_name`: echo the given name.
- `translated_name`: an English translation if the name is not English, else \
null. `aliases`: other common names.
- `summary`: one enticing sentence for a list card. `description`: 2-3 \
sentences on what it is, key ingredients, and how it's served.
- `origin`: region/country of origin if notable, else null.
- `allergens`/`dietary`: each a probability 0-1 that the dish contains the \
allergen / satisfies the diet. Cover the common allergens plausibly present \
(gluten, milk, egg, fish, shellfish, nuts, soy, pork) and diets the traveler \
tracks (vegetarian, vegan). A low `vegetarian` probability means it almost \
certainly contains meat.
- `spice_level`: 0-5. `price_level`: 1-5 relative to typical restaurant fare.
Base estimates on the dish's typical/authentic preparation."""


def enrich_user(name: str, hints: list[str] | None) -> str:
    msg = f"Dish name: {name}"
    if hints:
        msg += f"\nAllergens marked on the menu: {', '.join(hints)}"
    return msg


SUGGEST_QUESTIONS_SYSTEM = """You help a traveler with dietary restrictions \
prepare questions to ask restaurant staff about a dish.

Given the restrictions they watch out for, propose 2-4 SHORT questions they \
would plausibly want to ask about any dish — the kind that catch what a menu \
doesn't say (shared fryer oil, hidden stock/broth ingredients, cross \
contamination, substitutions).

Rules:
- Write every question in the requested language, phrased naturally.
- One sentence each, ending with a question mark. No numbering, no preamble.
- Cover the given restrictions only; don't invent others.
- Do not repeat or trivially rephrase any of the questions the user already \
saved (provided below).
Return nothing but the structured list."""


def suggest_questions_user(watch: list[str], language_name: str, existing: list[str]) -> str:
    msg = (
        f"Restrictions they watch out for: {', '.join(watch)}\n"
        f"Language for the questions: {language_name}"
    )
    if existing:
        msg += "\nQuestions they already saved (do not repeat):\n" + "\n".join(
            f"- {q}" for q in existing
        )
    return msg


TRANSLATE_QUESTIONS_SYSTEM = """You help a traveler ask restaurant staff \
about a dish. Given the dish (name, and origin if known) and the traveler's \
questions:

- `language`: the ISO 639-1 code of the language the restaurant's staff most \
likely speaks. When the menu's language is given, use exactly that; \
otherwise infer it from the dish and its origin ("Francesinha" -> "pt").
- `translations`: every question translated into that language, same order — \
natural, polite spoken phrasing a waiter understands at a glance. Keep them \
short and unambiguous; phrasings answerable with yes/no are best.
Return nothing but the structured result."""


def translate_questions_user(
    texts: list[str], dish_name: str, origin: str | None, language: str | None
) -> str:
    msg = f"Dish: {dish_name}"
    if origin:
        msg += f"\nOrigin: {origin}"
    if language:
        msg += f"\nMenu language: {language}"
    return msg + "\nQuestions:\n" + "\n".join(f"- {t}" for t in texts)
