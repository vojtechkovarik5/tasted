from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.dev", extra="ignore")

    # Postgres connection components (override via env: POSTGRES_USER, ...).
    postgres_user: str = "tasted"
    postgres_password: str = "tasted"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "tasted"

    # Redis — Celery broker (override via env: REDIS_HOST, REDIS_PORT).
    # Default port matches the compose redis as published on the host (6380,
    # see docker-compose.yml); inside compose the services get 6379.
    redis_host: str = "localhost"
    redis_port: int = 6380

    # "local" | "staging" | "production". Drives the Clerk auth bypass and the
    # S3 key prefix (so envs don't collide in a shared bucket).
    app_env: str = "local"

    # A scan stuck in `processing` longer than this is assumed dead (worker
    # crashed mid-page); the cleanup beat task resets it to `new` and reschedules
    # its menu. Comfortably above the longest a real page takes to process.
    menu_processing_stale_after_seconds: int = 600
    # A page that raises during processing (e.g. a transient AI error) reverts to
    # `new` and is retried after this delay, up to this many total attempts; then
    # we give up so an unreadable photo doesn't re-queue indefinitely.
    menu_processing_max_attempts: int = 3
    menu_processing_retry_delay_seconds: int = 30
    # Enrichment below this family-match confidence (0-1) links no dish — the
    # menu item "stays as written" and the card shows the no-match state.
    menu_match_min_confidence: float = 0.5

    # --- Clerk (auth) ------------------------------------------------------
    # JWKS_URL verifies session JWTs; secret key is for the Clerk admin SDK.
    # When unset (local dev) auth falls back to a fixed dev user — see auth.py.
    clerk_jwks_url: str = ""
    clerk_secret_key: str = ""
    # Optional azp allow-list (Clerk "authorized parties").
    clerk_authorized_parties: list[str] = []

    # --- Object storage (menu photos, user dish photos) --------------------
    # When s3_bucket is unset, uploads fall back to local disk (upload_dir),
    # so the app runs without AWS creds — see services/storage.py.
    upload_dir: str = "uploads"  # local-disk fallback root
    s3_bucket: str = ""
    aws_region: str = "eu-central-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    # Set for S3-compatible stores (Cloudflare R2, MinIO); blank = real AWS.
    aws_endpoint_url: str = ""
    # Public base for object URLs. Blank => derive the standard AWS URL.
    # For R2/CloudFront set the CDN origin, e.g. "https://cdn.tasted.app".
    s3_public_base_url: str = ""

    # --- OpenAI (LLM extraction/enrichment + embeddings) -------------------
    # When unset the pipeline uses the deterministic StubMenuAI — see
    # services/ai.py.
    openai_api_key: str = ""
    openai_extract_model: str = "gpt-4.1-mini"  # vision, reads the menu photo
    openai_enrich_model: str = "gpt-4.1-mini"  # per-dish knowledge
    openai_embedding_model: str = "text-embedding-3-small"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def clerk_configured(self) -> bool:
        return bool(self.clerk_jwks_url)

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_bucket)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL assembled from the components above."""
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
