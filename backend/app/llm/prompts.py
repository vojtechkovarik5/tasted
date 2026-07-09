"""Prompt templates for the menu pipeline. Kept out of the agent code so
they're easy to iterate on and diff."""

EXTRACT_SYSTEM = """You read photographs of restaurant menus and list what's \
printed, faithfully structured. "The user's language" below is given in the \
user message; the "menu's own language" is the primary/local language the \
menu is printed in.

Rules:
- One entry per orderable item — dishes AND drinks. Skip prose (section \
intros like "Your choice of protein, wrapped in rice paper"), footers, \
opening hours and legal notes.
- `groups`: every section header on the menu ("Bún", "Appetizers", "Drinks"), \
in menu order. `name` is the header in the menu's own language ONLY — when a \
header is printed bilingually ("GÓI CUỐN - SPRING ROLLS"), keep just the \
original ("Gói Cuốn"). `translated_name` is the header in the user's \
language; null when it already is the user's language.
- `group` (per item): the `name` of the group the item appears under, \
matching one of `groups` exactly; null for ungrouped items.
- `name`: the item's name in the menu's own language ONLY. Menus often print \
an inline translation right after the original ("Chả Giò Tôm Thịt Shrimp and \
Pork Egg Rolls") — keep just the original ("Chả Giò Tôm Thịt"). Never \
translate or paraphrase yourself. `number`: the list number/code printed \
before the name ("12. Bún Chạo Tôm" -> number "12", name "Bún Chạo Tôm"), \
else null — numbering is NEVER part of `name`.
- `translated_name`: the name in the user's language, ONLY when a \
translation is meaningful — descriptive names ("Kachna s bramborem" -> \
"Duck with potatoes"). Proper dish names that travelers know as-is \
(Francesinha, Phở, Tiramisu) -> null. Also null when the name is already in \
the user's language. When the menu prints its own translation, use its \
meaning, but NEVER copy it in a language other than the user's — a printed \
English translation still becomes the user's language.
- `description`: the ingredients/description text printed under the item, \
verbatim in the menu's own language; null when the menu prints none — do \
NOT invent one. `translated_description`: the same text in the user's \
language; null when there is no description or it's already in the user's \
language.
- `price`: the numeric price if shown, else null. `currency`: ISO 4217 \
inferred from the symbol/context (€->EUR, Kč->CZK, £->GBP), else null.
- `allergen_hints`: only allergens explicitly marked on the menu (icons, \
footnote letters/numbers, "contains ..."). Do not guess from the dish name.
- `language`: the ISO 639-1 code of the menu's own language ("pt" for a \
Portuguese menu). For a multilingual menu, the primary/local language. Null \
only if genuinely unreadable.
Return nothing but the structured result."""


def extract_user(language_name: str) -> str:
    return (
        "Extract every orderable item and every section from this menu photo. "
        f"The user's language is {language_name}: every `translated_name`, "
        f"`translated_description` and group `translated_name` MUST be written "
        f"in {language_name} — even when the menu prints its own translation "
        f"in some other language, re-translate it into {language_name}."
    )

ENRICH_SYSTEM = """You are a food expert helping travelers understand foreign \
dishes. Given a dish name (and sometimes the description a menu printed for \
it), return concise, accurate information. This is CANONICAL knowledge about \
the dish shown to every user, so write it in English and describe the \
typical/authentic dish, not one restaurant's take.

- `original_name`: echo the given name.
- `translated_name`: an English translation ONLY when the name is descriptive \
and translating it helps ("Pato com batatas" -> "Duck with potatoes"). \
Proper dish names travelers know as-is (Francesinha, Phở, Tiramisu) -> null. \
Null when the name is already English. `aliases`: other common names.
- `summary`: one enticing sentence for a list card. `description`: 2-3 \
sentences on what it is, key ingredients, and how it's served.
- `origin`: region/country of origin if notable, else null.
- `allergens`/`dietary`: each a probability 0-1 that the dish contains the \
allergen / satisfies the diet. Cover the common allergens plausibly present \
(gluten, milk, egg, fish, shellfish, nuts, soy, pork) and diets the traveler \
tracks (vegetarian, vegan). A low `vegetarian` probability means it almost \
certainly contains meat.
- `macros`: estimated for one typical serving — kcal, protein_g, fat_g, \
carbs_g. Rough good-faith estimates are fine; null only when truly unknowable.
- `spice_level`: 0-5. `price_level`: 1-5 relative to typical restaurant fare.
Base estimates on the dish's typical/authentic preparation; the menu's \
printed description (when given) tells you this restaurant's ingredients."""


def enrich_user(name: str, hints: list[str] | None, menu_description: str | None = None) -> str:
    msg = f"Dish name: {name}"
    if menu_description:
        msg += f"\nDescription printed on the menu: {menu_description}"
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
