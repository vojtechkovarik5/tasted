// API client for the Tasted backend + the data-loading pattern.
//
// ── How a menu loads (async, two-phase) ─────────────────────────────────────
// Menu items don't all resolve at once:
//   - items already in the backend's dish cache come back IMMEDIATELY
//     (status "ready", `dish` populated)
//   - items the AI is still enriching come back as status "pending"
//     (`dish` is null) and flip to "ready" on a later poll
//
// The flow the UI implements:
//   1. POST /menus (photos[])      -> Menu { status: "processing", items }
//   2. keep menu.id; render "ready" items now, skeletons for "pending"
//   3. poll GET /menus/{id} every ~1.5s (pollMenu below)
//   4. stop when menu.status === "complete"
//
// ── Auth ────────────────────────────────────────────────────────────────────
// User-scoped endpoints (menu history, restrictions, dietary, currency,
// votes, photo upload) resolve the user from the Authorization header.
// auth.tsx calls setAuthToken() on sign-in/out; while signed out no header is
// sent — menus are then created anonymously (the app keeps the current menu
// locally) and GET /menus returns []. With real Clerk the token becomes
// `await getToken()` instead of the stub user id.
//
// NOTE: types mirror backend/app/schemas/*. Later they can be generated from
// the backend's /openapi.json so they can't drift.

import { Platform } from "react-native";

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types (mirror backend schemas) ──────────────────────────────────────────

export type Money = { amount: number; currency: string };

export type Allergen = { name: string; probability: number };

/** Probability the dish SATISFIES a diet (0.02 => almost certainly not vegetarian). */
export type DietaryFlag = { name: string; probability: number };

export type DishInfo = {
  original_name: string;
  aliases: string[];
  translated_name: string | null;
  summary: string | null; // one-liner for list cards
  description: string; // rich text for the detail screen
  origin: string | null;
  allergens: Allergen[];
  dietary: DietaryFlag[];
  spice_level: number; // 0..5, fractional (vote-aggregated)
  price_level: number | null; // 0..5, fractional
};

export type Photo = { url: string; source: string }; // source: user | ai

/** Photo urls from the dev backend are relative ("/static/..."); real ones
 *  (object storage) will be absolute. Resolve both. */
export function resolveUrl(url: string): string {
  return url.startsWith("/") ? `${API_URL}${url}` : url;
}

export type Dish = {
  id: string;
  canonical_name: string;
  region: string | null;
  info: DishInfo;
  photos: Photo[];
};

export type MenuItemStatus = "ready" | "pending" | "failed";

export type MenuItem = {
  id: string;
  original_name: string;
  status: MenuItemStatus;
  menu_price: Money | null;
  approx_price: Money | null;
  regional_note: string | null;
  dish: Dish | null; // null while pending
};

export type Menu = {
  id: string;
  name: string | null; // restaurant name
  status: "processing" | "complete";
  created_at: string; // ISO 8601
  items: MenuItem[];
};

export type MenuSummary = {
  id: string;
  name: string | null;
  status: "processing" | "complete";
  created_at: string;
  item_count: number;
};

export type Currency = {
  code: string; // "CZK"
  name: string; // "Czech koruna"
  symbol: string | null; // "Kč"
  rate_per_eur: number;
};

// Only spice and price are votable; allergen/dietary values are not.
export type VoteTarget = "spice" | "price";

export type Preferences = {
  watch_list: { key: string; kind: "allergen" | "dietary"; on: boolean }[];
  macros: string[];
  section_order: string[];
  currency: string;
};

// ── Fetch helpers ───────────────────────────────────────────────────────────

// Set by auth.tsx on sign-in/out; attached to every request when present.
let authToken: string | null = null;
export function setAuthToken(token: string | null) {
  authToken = token;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: HeadersInit = {
    ...(init?.headers as Record<string, string> | undefined),
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  };
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`HTTP ${res.status} on ${path}`);
  return res.json() as Promise<T>;
}

const json = (method: "POST" | "PUT", body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

/** A FormData file part from a local uri (camera / image picker).
 *
 * Native (iOS/Android): RN's fetch understands the {uri,name,type} shape.
 * Web: the browser's FormData needs a real Blob/File — a plain object gets
 * serialised to the literal "[object Object]" and the server rejects it —
 * so fetch the uri (blob:/data:) into an actual File first. */
async function filePart(uri: string, name: string): Promise<Blob> {
  if (Platform.OS === "web") {
    const blob = await (await fetch(uri)).blob();
    return new File([blob], name, { type: blob.type || "image/jpeg" });
  }
  return { uri, name, type: "image/jpeg" } as unknown as Blob;
}

// ── Health ──────────────────────────────────────────────────────────────────

export const getHealth = () => request<{ status: string }>("/health");

// ── Menus (scan flow + history) ─────────────────────────────────────────────

/** Upload the photo(s) of one menu — several pages allowed. Keep the id. */
export async function postMenu(photoUris: string[], name?: string): Promise<Menu> {
  const form = new FormData();
  for (const [i, uri] of photoUris.entries()) {
    form.append("photos", await filePart(uri, `page-${i + 1}.jpg`));
  }
  if (name) form.append("name", name);
  return request<Menu>("/menus", { method: "POST", body: form });
}

export const getMenu = (id: string) => request<Menu>(`/menus/${id}`);

/** My scan history (user resolved from the auth header — no user_id param). */
export const listMenus = () => request<MenuSummary[]>("/menus");

/**
 * Poll a menu until complete. Calls `onUpdate` with every intermediate state
 * so the UI can flip pending cards to ready as they resolve.
 */
export async function pollMenu(
  menuId: string,
  onUpdate: (menu: Menu) => void,
  intervalMs = 1500,
  maxAttempts = 40,
): Promise<Menu> {
  for (let i = 0; i < maxAttempts; i++) {
    const menu = await getMenu(menuId);
    onUpdate(menu);
    if (menu.status === "complete") return menu;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error("menu polling timed out");
}

// ── Dishes ──────────────────────────────────────────────────────────────────

export const getDish = (id: string) => request<Dish>(`/dishes/${id}`);

/** Nudge spice / price level. Fire-and-forget from the UI (optimistic). */
export const sendVote = (dishId: string, target: VoteTarget, direction: "up" | "down") =>
  request<{ accepted: boolean }>(
    `/dishes/${dishId}/vote/${target}`,
    json("POST", { direction }),
  );

/** Upload a user photo of a dish (goes through moderation). */
export async function uploadDishPhoto(dishId: string, photoUri: string) {
  const form = new FormData();
  form.append("photo", await filePart(photoUri, "dish.jpg"));
  return request<{ accepted: boolean; status: string }>(`/dishes/${dishId}/photo`, {
    method: "POST",
    body: form,
  });
}

// ── User settings (all user-scoped via auth header) ─────────────────────────

export const getRestrictions = () => request<string[]>("/restrictions");
export const setRestrictions = (keys: string[]) =>
  request<string[]>("/restrictions", json("POST", keys));

export const getDietary = () => request<string[]>("/dietary");
export const setDietary = (keys: string[]) =>
  request<string[]>("/dietary", json("POST", keys));

export const getCurrencies = () => request<Currency[]>("/currencies");
export const setMyCurrency = (code: string) =>
  request<{ code: string }>("/currencies", json("POST", { code }));

// Macros + section order stay on the preferences blob for now.
export const getPreferences = () => request<Preferences>("/preferences");
export const putPreferences = (prefs: Preferences) =>
  request<Preferences>("/preferences", json("PUT", prefs));

// Fixed id of the backend's canned demo menu (see backend routers/menus.py).
export const DEMO_MENU_ID = "00000000-0000-0000-0000-00000000aaaa";
