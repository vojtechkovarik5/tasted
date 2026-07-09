# Tasted

Photograph a foreign menu → get dish descriptions, allergen probabilities and
dietary info. Monorepo with a Python backend and a React Native (Expo) mobile app.

```
tasted/
  backend/            # FastAPI + Postgres/pgvector (see backend/README.md)
  mobile/             # Expo / React Native app (see mobile/README.md)
  docker-compose.yml  # runs the backend stack (api + db)
  .env.example        # template for .env.dev (copy it); read by docker compose
```

## Quick start

**Backend** (from the repo root):

```sh
docker compose up --build
# API:  http://localhost:8000        docs: http://localhost:8000/docs
```

**Mobile** (in another terminal):

```sh
cd mobile
npm install
cp .env.dev.example .env.dev      # set EXPO_PUBLIC_API_URL to a URL your device can reach
npm start                 # scan the QR code with the Expo Go app
```

See [backend/README.md](backend/README.md) and [mobile/README.md](mobile/README.md)
for details.

## How the two halves connect

The mobile app talks to the backend over HTTP. Its API base URL is configured via
`EXPO_PUBLIC_API_URL` (in `mobile/.env`). The backend serves an OpenAPI schema at
`/openapi.json`, which will later be used to generate the mobile app's API types so
they stay in sync automatically.
