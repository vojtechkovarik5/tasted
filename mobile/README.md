# Tasted — mobile app

React Native app built with [Expo](https://expo.dev). One codebase → iOS + Android.
Written in TypeScript. You do **not** need Xcode or Android Studio to develop —
Expo Go (a free app on your phone) runs the app over Wi-Fi.

## First-time setup

```sh
cd mobile
npm install                 # once (already done if you just scaffolded it)
cp .env.example .env        # then edit .env — see below
```

Set `EXPO_PUBLIC_API_URL` in `.env` to a backend address your device can reach:

| Where you run the app | Value |
|---|---|
| iOS simulator (on the Mac) | `http://localhost:8000` |
| Android emulator | `http://10.0.2.2:8000` |
| Physical phone (Expo Go) | `http://<your-Mac-LAN-IP>:8000` (find it: `ipconfig getifaddr en0`) |

The backend must be running (`docker compose up` from the repo root).

## Run it

```sh
npm start          # opens Expo; scan the QR code with the Expo Go app
# or target a simulator/emulator directly:
npm run ios
npm run android
```

The starter screen shows whether the backend is reachable and lists the dishes
from `GET /dishes`. Tap **Refresh** to reload.

## Where things are

```
mobile/
  App.tsx                        # theme provider + tiny state-based navigator + tab bar
  src/theme.ts                   # ALL colors live here (light + dark palettes)
  src/api.ts                     # backend client + types + the scan polling helper
  src/components.tsx             # Chip, CircleBtn, Bar, Card, PrimaryButton, ...
  src/screens/HomeScreen.tsx     # scan entry; renders ready cards + pending skeletons
  src/screens/DishDetailScreen.tsx  # design 1c: photo, price, spice/€, voting rows, CTA
  src/screens/ProfileScreen.tsx  # design 1d: sign-in, chips, priorities, currency
  .env                           # your EXPO_PUBLIC_API_URL (gitignored)
```

## How data loads (async dishes)

Menu items resolve in two phases: dishes already in the backend cache come back
`ready` immediately; new ones come back `pending` while the AI enriches them.

```
POST /scan  -> render "ready" items now, skeleton cards for "pending"
poll GET /scans/{id} (src/api.ts pollScan) -> items flip to "ready" -> re-render
stop when scan.status === "complete"
```

## Changing colors / dark mode

Edit `src/theme.ts` — every component reads colors via `useTheme()`, no hex
values in screens. A dark palette already exists; wire it in `App.tsx` by
passing `darkColors` (e.g. via `useColorScheme()`).

## Auth (Clerk — not wired yet)

Login goes through [Clerk](https://clerk.com); the "Continue with Apple/Google"
buttons on the Profile screen will be powered by it (Clerk owns the OAuth flows).
Integration steps when ready:

1. `npx expo install @clerk/clerk-expo expo-secure-store`
2. Wrap the app in `<ClerkProvider publishableKey={...} tokenCache={tokenCache}>`
   (key from `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY` in `.env`)
3. Buttons call `useSSO()` with strategy `oauth_apple` / `oauth_google`
4. API calls attach `Authorization: Bearer ${await getToken()}` (Clerk session JWT)
5. Backend verifies the JWT against Clerk's JWKS and creates/loads the user row
   by `clerk_user_id` (`users` table is already keyed that way)

## Notes for later

- The types in `src/api.ts` are hand-written for now. Once the API stabilises,
  generate them from the backend's `/openapi.json` so they can't drift.
- Camera capture (`expo-camera`) replaces the "demo scan" button: take photo →
  `postScan(photo.uri)` → `pollScan`.
- Reordering on Profile is tap-to-move-up; upgrade path is
  react-native-draggable-flatlist. Dish photo pager: react-native-pager-view.
