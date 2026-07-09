"""OpenAI (ChatGPT) client factories.

Thin wrappers over langchain-openai so callers don't repeat api-key/model
wiring. Chains bind structured output on top of these (see services/ai.py):

    llm = get_chat_client(settings.openai_extract_model)
    result = await llm.with_structured_output(MenuExtraction).ainvoke(messages)

Clients are cheap to construct; we make one per call rather than holding a
singleton, which keeps them bound to the running event loop (Celery runs each
task in its own loop).
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings
from app.models import EMBEDDING_DIM


def get_chat_client(model: str, **kwargs) -> ChatOpenAI:
    """A ChatOpenAI client. `temperature=0` by default for stable extraction."""
    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        temperature=kwargs.pop("temperature", 0),
        **kwargs,
    )


def get_embeddings_client() -> OpenAIEmbeddings:
    """Embeddings sized to EMBEDDING_DIM so vectors fit the dishes column.

    text-embedding-3-* support Matryoshka truncation via `dimensions`, so we
    ask for exactly the column width (1024) instead of the model default.
    """
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
        dimensions=EMBEDDING_DIM,
    )
