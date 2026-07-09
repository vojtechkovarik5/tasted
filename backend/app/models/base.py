from sqlalchemy.orm import DeclarativeBase

# Dimension of the dish-name embeddings used for the semantic cache lookup.
# 1024 matches Voyage's voyage-3 family (Anthropic's recommended embedding models).
EMBEDDING_DIM = 1024


class Base(DeclarativeBase):
    pass
