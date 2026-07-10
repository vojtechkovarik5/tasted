# Tasted

Photograph a foreign menu → get dish descriptions, allergen probabilities and
dietary info. Monorepo with a Python backend and a React Native (Expo) mobile app.

```
tasted/
  backend/            # FastAPI + Celery + Postgres/pgvector (see backend/README.md)
  mobile/             # Expo / React Native app (see mobile/README.md)
  docker-compose.yml  # runs the backend stack (api + worker + db + redis)
  .env.example        # template for .env.dev (copy it); read by docker compose
```

## Prerequisites

| Tool | Needed for | Notes |
| --- | --- | --- |
| [Docker Desktop](https://docs.docker.com/get-docker/) (with Compose) | backend | the whole backend stack runs in containers |
| [Node.js](https://nodejs.org) 20+ (ships with npm) | frontend | Expo dev server + web build |
| [Expo Go](https://expo.dev/go) app | frontend on a phone | optional — only for running on a physical device |
| [uv](https://docs.astral.sh/uv/) + Python 3.12 | backend *outside* Docker | optional — only for running tests / alembic locally |

No API keys are required to get started: with a blank `.env.dev` the backend
uses a deterministic stub AI, a fixed dev user instead of real auth
(any `Authorization: Bearer <id>` is trusted), and local-disk photo storage.

## Start the backend

From the repo root:

```sh
cp .env.example .env.dev     # first time only; blank values = local-dev defaults
docker compose up --build
```

This starts four services:

- **db** — Postgres 17 with pgvector (data persists in the `pgdata` volume)
- **redis** — Celery broker
- **api** — FastAPI on <http://localhost:8000> (docs at [/docs](http://localhost:8000/docs));
  runs `alembic upgrade head` automatically before starting, and hot-reloads
  on source changes (the source tree is mounted into the container)
- **worker** — Celery worker + beat (menu processing pipeline, daily currency refresh)

Optional keys in `.env.dev`:

- `OPENAI_API_KEY` — real menu extraction/enrichment instead of the stub AI
- `CLERK_JWKS_URL` / `CLERK_SECRET_KEY` — real auth instead of the dev user
- `S3_BUCKET` + AWS creds — object storage instead of `backend/uploads/`

Gotchas:

- **The worker does NOT hot-reload.** After changing backend code that the
  pipeline touches, run `docker compose restart worker`.
- New migrations are applied on the next `docker compose up` (or manually:
  `docker compose exec api alembic upgrade head`).

### Backend tests (outside Docker)

```sh
cd backend
uv sync                      # creates .venv with all dependencies
uv run pytest                # integration tests need the compose db running
```

## Start the frontend

In another terminal:

```sh
cd mobile
npm install                  # first time only
cp .env.example .env.dev     # set EXPO_PUBLIC_API_URL (see below)
npm start                    # Expo dev server — press w for web, or scan the QR with Expo Go
```

`EXPO_PUBLIC_API_URL` in `mobile/.env.dev` must be a URL **your device** can
reach:

| Where the app runs | URL |
| --- | --- |
| Web browser / iOS simulator | `http://localhost:8000` |
| Android emulator | `http://10.0.2.2:8000` |
| Physical phone (Expo Go) | `http://<your-computer-LAN-IP>:8000` |

Shortcuts: `npm run web` opens the web build directly (on
<http://localhost:8081>), `npm run ios` / `npm run android` target a simulator.

Typecheck with `npx tsc --noEmit`.

## How the two halves connect

The mobile app talks to the backend over HTTP. Its API base URL is configured via
`EXPO_PUBLIC_API_URL` (in `mobile/.env.dev`). The backend serves an OpenAPI schema at
`/openapi.json`, which will later be used to generate the mobile app's API types so
they stay in sync automatically.

See [backend/README.md](backend/README.md) and [mobile/README.md](mobile/README.md)
for details.
