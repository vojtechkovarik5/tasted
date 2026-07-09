from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import engine
from app.routers import currencies, dishes, health, menus, preferences, restrictions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic migrations (`alembic upgrade head`), run
    # before the server starts — see docker-compose command / README.
    yield
    await engine.dispose()


app = FastAPI(title="Tasted API", version="0.1.0", lifespan=lifespan)

# Browsers block cross-origin requests (the Expo web app runs on :8081, the
# API on :8000). Native iOS/Android apps don't enforce CORS — this is only
# for web/dev. TODO: restrict origins before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(currencies.router)
app.include_router(dishes.router)
app.include_router(menus.router)
app.include_router(restrictions.router)
app.include_router(preferences.router)

# Dev-only file serving for demo dish photos. Real photos will live in object
# storage (S3/R2) and PhotoOut.url will be absolute.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# When object storage isn't configured we use LocalStorage (disk); serve that
# dir so its public_url (/uploads/...) actually resolves in the demo. With S3
# configured this mount is skipped — URLs point at the bucket/CDN instead.
if not settings.s3_configured:
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
