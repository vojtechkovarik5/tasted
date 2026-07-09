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
from app.domain import Allergen, DietaryFlag, DishInfo, ExtractedMenuItem, MenuExtraction
from app.llm.clients import get_chat_client, get_embeddings_client
from app.llm.prompts import (
    ENRICH_SYSTEM,
    EXTRACT_SYSTEM,
    EXTRACT_USER,
    enrich_user,
)
from app.models import EMBEDDING_DIM


class MenuAI(Protocol):
    async def extract_menu(self, image: bytes, media_type: str | None) -> MenuExtraction:
        """First pass over a menu photo: list what's printed, nothing more."""
        ...

    async def enrich_dish(self, name: str, *, hints: list[str] | None = None) -> DishInfo:
        """Full dish knowledge for one item that missed the cache."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embedding per text, EMBEDDING_DIM-dimensional, batched."""
        ...


class StubMenuAI:
    """Deterministic stand-in: same name -> same embedding, so cache hits
    work across scans exactly like they will with real embeddings."""

    async def extract_menu(self, image: bytes, media_type: str | None) -> MenuExtraction:
        return MenuExtraction(
            items=[
                ExtractedMenuItem(name="Francesinha", price=9.50, currency="EUR"),
                ExtractedMenuItem(
                    name="Bacalhau à Brás", price=12.00, currency="EUR",
                    allergen_hints=["fish", "egg"],
                ),
            ]
        )

    async def enrich_dish(self, name: str, *, hints: list[str] | None = None) -> DishInfo:
        return DishInfo(
            original_name=name,
            summary=f"{name} — stub enrichment.",
            description=f"Stub description for {name}. Replace StubMenuAI with a real adapter.",
            allergens=[Allergen(name=h, probability=0.9) for h in (hints or [])],
            dietary=[DietaryFlag(name="vegetarian", probability=0.5)],
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

    async def extract_menu(self, image: bytes, media_type: str | None) -> MenuExtraction:
        b64 = base64.b64encode(image).decode()
        data_url = f"data:{media_type or 'image/jpeg'};base64,{b64}"
        messages = [
            SystemMessage(content=EXTRACT_SYSTEM),
            HumanMessage(
                content=[
                    {"type": "text", "text": EXTRACT_USER},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            ),
        ]
        llm = get_chat_client(settings.openai_extract_model).with_structured_output(
            MenuExtraction
        )
        return await llm.ainvoke(messages)

    async def enrich_dish(self, name: str, *, hints: list[str] | None = None) -> DishInfo:
        messages = [
            SystemMessage(content=ENRICH_SYSTEM),
            HumanMessage(content=enrich_user(name, hints)),
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
