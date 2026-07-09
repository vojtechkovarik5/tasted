"""The AI boundary of the scan pipeline.

Everything the pipeline needs from AI is behind the `MenuAI` protocol:

  extract_menu  photo -> the printed line items (name, price, allergen marks)
  enrich_dish   one item name -> full DishInfo (description, allergens, ...)
  embed         dish names -> vectors for the pgvector cache lookup

`StubMenuAI` is a deterministic dev implementation so the whole pipeline runs
without API keys. `OpenAIMenuAI` is the real adapter (ChatGPT vision +
structured output for extract/enrich, OpenAI embeddings for the cache);
`get_menu_ai()` picks it when an API key is configured.
"""

from __future__ import annotations

import base64
import hashlib
import random
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.domain import (
    LANGUAGE_NAMES,
    Allergen,
    DietaryFlag,
    DishInfo,
    ExtractedGroup,
    ExtractedMenuItem,
    Language,
    Macros,
    MenuExtraction,
    SuggestedQuestions,
    TranslatedQuestions,
    WatchChip,
)
from app.llm.clients import get_chat_client, get_embeddings_client
from app.llm.prompts import (
    ENRICH_SYSTEM,
    EXTRACT_SYSTEM,
    SUGGEST_QUESTIONS_SYSTEM,
    TRANSLATE_QUESTIONS_SYSTEM,
    enrich_user,
    extract_user,
    suggest_questions_user,
    translate_questions_user,
)
from app.models import EMBEDDING_DIM


class MenuAI(Protocol):
    async def extract_menu(
        self, image: bytes, media_type: str | None, *, user_language: Language = Language.en
    ) -> MenuExtraction:
        """First pass over a menu photo: list what's printed (items, groups,
        printed descriptions) plus translations into `user_language` — the
        scanning user's preferred language."""
        ...

    async def enrich_dish(
        self,
        name: str,
        *,
        hints: list[str] | None = None,
        menu_description: str | None = None,
    ) -> DishInfo:
        """Full canonical dish knowledge for one item that missed the cache.
        `menu_description` is the description printed on the menu, extra
        context only — the result describes the typical dish."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embedding per text, EMBEDDING_DIM-dimensional, batched."""
        ...


class StubMenuAI:
    """Deterministic stand-in: same name -> same embedding, so cache hits
    work across scans exactly like they will with real embeddings."""

    async def extract_menu(
        self, image: bytes, media_type: str | None, *, user_language: Language = Language.en
    ) -> MenuExtraction:
        return MenuExtraction(
            items=[
                ExtractedMenuItem(
                    name="Francesinha",
                    number="1",
                    # Proper dish name — the prompt says no translation.
                    translated_name=None,
                    description="pão, linguiça, salsicha fresca, fiambre",
                    translated_description="bread, linguiça, fresh sausage, ham",
                    group="Pratos",
                    price=9.50,
                    currency="EUR",
                ),
                ExtractedMenuItem(
                    name="Bacalhau à Brás",
                    translated_name=None,
                    group="Pratos",
                    price=12.00,
                    currency="EUR",
                    allergen_hints=["fish", "egg"],
                ),
            ],
            groups=[ExtractedGroup(name="Pratos", translated_name="Mains")],
            language="pt",  # the canned menu is Portuguese
        )

    async def enrich_dish(
        self,
        name: str,
        *,
        hints: list[str] | None = None,
        menu_description: str | None = None,
    ) -> DishInfo:
        return DishInfo(
            original_name=name,
            summary=f"{name} — stub enrichment.",
            description=f"Stub description for {name}. Replace StubMenuAI with a real adapter.",
            allergens=[Allergen(name=h, probability=0.9) for h in (hints or [])],
            dietary=[DietaryFlag(name="vegetarian", probability=0.5)],
            macros=Macros(kcal=650, protein_g=30, fat_g=35, carbs_g=50),
            spice_level=1.0,
            price_level=2.0,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        # Hash-seeded pseudo-embedding: identical (normalized) names collide,
        # different names land far apart — good enough to exercise the cache.
        seed = hashlib.sha256(text.strip().lower().encode()).digest()
        rng = random.Random(seed)
        return [rng.uniform(-1, 1) for _ in range(EMBEDDING_DIM)]


class OpenAIMenuAI:
    """ChatGPT-backed adapter.

    extract/enrich use `.with_structured_output(Model)` so the model returns
    validated pydantic directly (function-calling under the hood); embeddings
    come from OpenAI sized to the dishes column (see llm/clients).
    """

    async def extract_menu(
        self, image: bytes, media_type: str | None, *, user_language: Language = Language.en
    ) -> MenuExtraction:
        b64 = base64.b64encode(image).decode()
        data_url = f"data:{media_type or 'image/jpeg'};base64,{b64}"
        messages = [
            SystemMessage(content=EXTRACT_SYSTEM),
            HumanMessage(
                content=[
                    {"type": "text", "text": extract_user(LANGUAGE_NAMES[user_language])},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            ),
        ]
        llm = get_chat_client(settings.openai_extract_model).with_structured_output(
            MenuExtraction
        )
        extraction = await llm.ainvoke(messages)
        if extraction.language:
            extraction.language = extraction.language.strip().lower()[:2] or None
        return extraction

    async def enrich_dish(
        self,
        name: str,
        *,
        hints: list[str] | None = None,
        menu_description: str | None = None,
    ) -> DishInfo:
        messages = [
            SystemMessage(content=ENRICH_SYSTEM),
            HumanMessage(content=enrich_user(name, hints, menu_description)),
        ]
        llm = get_chat_client(settings.openai_enrich_model).with_structured_output(DishInfo)
        info = await llm.ainvoke(messages)
        info.original_name = name  # never let the model rename the item
        return info

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await get_embeddings_client().aembed_documents(texts)


def get_menu_ai() -> MenuAI:
    """AI adapter used by the pipeline: OpenAI when a key is set, else the
    deterministic stub (keeps local dev and tests runnable without a key)."""
    if settings.openai_configured:
        return OpenAIMenuAI()
    return StubMenuAI()


class QuestionAI(Protocol):
    """AI boundary of the "My questions" feature: suggest ask-the-staff
    questions from the "Watch out for" chips, and translate saved questions
    into the staff's language for the ask-staff sheet."""

    async def suggest_questions(
        self, chips: list[WatchChip], language: Language, existing: list[str]
    ) -> list[str]:
        """2-4 short questions in the user's language, none repeating
        `existing` (their already-saved questions)."""
        ...

    async def translate_questions(
        self, texts: list[str], *, dish_name: str, origin: str | None, language: str | None
    ) -> TranslatedQuestions:
        """Translate each text into the staff's language, preserving order.

        `language` is the menu's stored language (read off the photo during
        extraction) — used verbatim when present; inferred from the dish and
        origin when the menu didn't record one (older scans, unreadable photo).
        """
        ...


class StubQuestionAI:
    """Deterministic stand-in: one templated question per watched chip, so the
    suggestions flow (and its exclusion of saved questions) is testable
    without an API key. Always English — the stub ignores `language`."""

    async def suggest_questions(
        self, chips: list[WatchChip], language: Language, existing: list[str]
    ) -> list[str]:
        taken = {q.strip().lower() for q in existing}
        suggestions = []
        for chip in chips:
            if chip.kind == "dietary":
                text = f"Can this be made {chip.key}?"
            else:
                text = f"Does this dish contain {chip.key}?"
            if text.lower() not in taken:
                suggestions.append(text)
        return suggestions[:4]

    async def translate_questions(
        self, texts: list[str], *, dish_name: str, origin: str | None, language: str | None
    ) -> TranslatedQuestions:
        # Honors an explicit menu language, else "pt" — matches StubMenuAI's
        # canned Portuguese menu (Francesinha, Bacalhau à Brás). The [lang]
        # prefix makes it obvious in the UI that these are stub translations.
        lang = language or "pt"
        return TranslatedQuestions(
            language=lang, translations=[f"[{lang}] {t}" for t in texts]
        )


class OpenAIQuestionAI:
    """ChatGPT-backed adapter, same structured-output pattern as OpenAIMenuAI."""

    async def suggest_questions(
        self, chips: list[WatchChip], language: Language, existing: list[str]
    ) -> list[str]:
        messages = [
            SystemMessage(content=SUGGEST_QUESTIONS_SYSTEM),
            HumanMessage(
                content=suggest_questions_user(
                    [c.key for c in chips], LANGUAGE_NAMES[language], existing
                )
            ),
        ]
        llm = get_chat_client(settings.openai_enrich_model).with_structured_output(
            SuggestedQuestions
        )
        result = await llm.ainvoke(messages)
        return result.questions[:4]

    async def translate_questions(
        self, texts: list[str], *, dish_name: str, origin: str | None, language: str | None
    ) -> TranslatedQuestions:
        messages = [
            SystemMessage(content=TRANSLATE_QUESTIONS_SYSTEM),
            HumanMessage(content=translate_questions_user(texts, dish_name, origin, language)),
        ]
        llm = get_chat_client(settings.openai_enrich_model).with_structured_output(
            TranslatedQuestions
        )
        result = await llm.ainvoke(messages)
        # The sheet zips translations with the originals — never let a chatty
        # model change the count. Missing entries fall back to the original.
        result.language = result.language.strip().lower()[:2]
        result.translations = (result.translations + texts[len(result.translations):])[
            : len(texts)
        ]
        return result


def get_question_ai() -> QuestionAI:
    """Suggestion adapter: OpenAI when a key is set, else the deterministic
    stub (same policy as get_menu_ai)."""
    if settings.openai_configured:
        return OpenAIQuestionAI()
    return StubQuestionAI()
