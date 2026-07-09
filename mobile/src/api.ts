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

// `name` is the canonical slug ("gluten", "rice-noodles"); `label` is the
// display name localized to the user's language (English fallback).
export type Allergen = { name: string; probability: number; label: string | null };

/** DIET FIT — share of versions of the dish worldwide fitting the flag
 *  (vegetarian 0.35 => about a third of versions are vegetarian). */
export type DietaryFlag = { name: string; probability: number; label: string | null };

/** Probability a typical version of the dish contains the ingredient. */
export type Ingredient = { name: string; probability: number; label: string | null };

/** Whole-dish average macros PER 100 g across variants — an AI estimate. */
export type Macros = {
  kcal: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carbs_g: number | null;
};

/** One variant chip of a dish family ("Gai · chicken") — a facet, not a
 *  separate page; the matched one gets highlighted. */
export type DishVariant = {
  id: string;
  key: string;
  name: string;
  description: string | null;
};

export type DishInfo = {
  original_name: string; // canonical family name ("Pad Thai")
  aliases: string[];
  // English translation, only when the name is descriptive enough that
  // translating helps; proper dish names (Francesinha, Phở) stay null.
  translated_name: string | null;
  native_name: string | null; // original script ("ผัดไทย")
  pronunciation: string | null; // IPA ("pʰàt tʰāj")
  summary: string | null; // one-liner for list cards
  description: string; // rich text, already resolved to the user's language
  origin: string | null; // "Thailand"
  category: string | null; // "stir-fried rice-noodle dish"
  national_dish: boolean;
  allergens: Allergen[];
  dietary: DietaryFlag[]; // diet fit percentages
  ingredients: Ingredient[]; // common ingredients, most likely first
  macros: Macros | null;
  spice_level: number; // 0..5, fractional (vote-aggregated)
  price_level: number | null; // 0..5, fractional
  similar: string[]; // names of related families ("Pad See Ew")
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
  variants: DishVariant[];
};

export type MenuItemStatus = "ready" | "pending" | "failed";

export type MenuItem = {
  id: string;
  // The menu's own language, inline printed translations stripped. The
  // *_translated twins are the scanning user's language (made once during
  // extraction) — the listing mirrors the menu + these translations.
  original_name: string;
  menu_number: string | null; // printed list number/code ("5", "A12")
  translated_name: string | null; // only when translating is meaningful
  menu_description: string | null; // ingredients/description as printed
  menu_description_translated: string | null;
  group_name: string | null; // menu section ("Bún", "Drinks")
  group_name_translated: string | null;
  status: MenuItemStatus;
  menu_price: Money | null;
  approx_price: Money | null; // user's currency; null when same as printed
  regional_note: string | null;
  // What the menu itself prints for this item, localized server-side:
  // "Contains: rice noodles · chicken", "Allergens: peanuts · egg".
  menu_ingredients: MenuTag[];
  menu_allergens: MenuTag[];
  // The OPTIONAL canonical-family match. A ready item without `dish` simply
  // "stays as written" (no confident match) — that's a normal state.
  dish: Dish | null;
  match_confidence: number | null; // 0-100, "Pad Thai · 91%"
  matched_variant_key: string | null; // highlighted variant chip
};

/** One printed ingredient/allergen tag; `key` is the canonical trackables
 *  slug (matches watch_list chips), `name` is already localized. */
export type MenuTag = { key: string | null; name: string };

export type Menu = {
  id: string;
  name: string | null; // restaurant name
  status: "processing" | "complete";
  created_at: string; // ISO 8601
  // ISO 639-1 the menu is printed in (read off the photo during extraction).
  // The ask-staff sheet uses it as the translation target. Null for menus
  // scanned before languages were recorded.
  language: string | null;
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

export type Language = {
  code: string; // ISO 639-1, "cs"
  name: string; // endonym, "Čeština"
};

// Only spice and price are votable; allergen/dietary values are not.
export type VoteTarget = "spice" | "price";

export type WatchKind = "allergen" | "dietary" | "ingredient";

export type Preferences = {
  // "What I track" — picked things show as tags on every menu item and dish.
  watch_list: { key: string; kind: WatchKind; on: boolean }[];
  macros: string[];
  section_order: string[];
  currency: string;
  language: string; // ISO 639-1; app chrome stays English, this is display-only
};

/** One "What I track" catalog entry. Allergens are the fixed EU-14; diet
 *  flags and ingredients can also be user-suggested — those come back as
 *  `pending` (visible only to their suggester until vetted). */
export type Trackable = {
  id: string;
  kind: WatchKind;
  key: string;
  name: string; // localized display name
  description: string | null;
  status: "active" | "pending";
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
  if (res.status === 204) return undefined as T; // DELETE responses have no body
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

/** Nudge spice / price level. Fire-and-forget from the UI. The displayed
 *  level doesn't move right away — votes are folded in by periodic
 *  recalculation — the UI just marks the pressed arrow. */
export const sendVote = (dishId: string, target: VoteTarget, direction: "up" | "down") =>
  request<{ accepted: boolean }>(
    `/dishes/${dishId}/vote/${target}`,
    json("POST", { direction }),
  );

/** My standing votes on a dish — restores the pressed-arrow state across
 *  reloads (one vote per user per target; pressing the other arrow flips). */
export type MyVotes = { spice: "up" | "down" | null; price: "up" | "down" | null };

export const getMyVotes = (dishId: string) => request<MyVotes>(`/dishes/${dishId}/votes`);

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

export const getTrackedIngredients = () => request<string[]>("/ingredients");
export const setTrackedIngredients = (keys: string[]) =>
  request<string[]>("/ingredients", json("POST", keys));

// ── "What I track" catalog ──────────────────────────────────────────────────

/** List/search the catalog. `q` powers the ingredients "Search any..." box. */
export const getTrackables = (kind?: WatchKind, q?: string) => {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (q) params.set("q", q);
  const qs = params.toString();
  return request<Trackable[]>(`/trackables${qs ? `?${qs}` : ""}`);
};

/** Suggest a new diet flag or ingredient (name + description). It is NOT
 *  added to the shared catalog automatically — it lands as `pending` and an
 *  AI check decides later; the suggester can track it right away. */
export const suggestTrackable = (
  kind: "dietary" | "ingredient",
  name: string,
  description?: string,
) =>
  request<Trackable>(
    "/trackables/suggest",
    json("POST", { kind, name, description: description || null }),
  );

export const getCurrencies = () => request<Currency[]>("/currencies");
export const setMyCurrency = (code: string) =>
  request<{ code: string }>("/currencies", json("POST", { code }));

// Language: a fixed allow-list (options from the backend), display-only for now.
export const getLanguages = () => request<Language[]>("/preferences/languages");
export const setMyLanguage = (code: string) =>
  request<{ code: string }>("/preferences/language", json("POST", { code }));

// Macros + section order stay on the preferences blob for now.
export const getPreferences = () => request<Preferences>("/preferences");
export const putPreferences = (prefs: Preferences) =>
  request<Preferences>("/preferences", json("PUT", prefs));

// ── My questions (saved ask-the-staff questions, Settings -> My questions) ──
// Written once in the user's language; the ask-staff sheet translates them
// per menu on demand. Order matters — the sheet lists them as arranged here.

export type Question = { id: string; text: string };

/** LLM suggestions seeded from the "Watch out for" chips (`based_on`). */
export type QuestionSuggestions = { based_on: string[]; questions: string[] };

export const getQuestions = () => request<Question[]>("/questions");
export const addQuestion = (text: string) =>
  request<Question>("/questions", json("POST", { text }));
export const deleteQuestion = (id: string) =>
  request<void>(`/questions/${id}`, { method: "DELETE" });
/** Persist a drag-reorder; `ids` must be the full list in its new order. */
export const reorderQuestions = (ids: string[]) =>
  request<Question[]>("/questions/order", json("PUT", { ids }));
export const getQuestionSuggestions = () =>
  request<QuestionSuggestions>("/questions/suggestions");

/** Ask-staff sheet: questions translated into the staff's language — the
 *  menu's stored language when known (Menu.language), otherwise inferred by
 *  the backend LLM from the dish (`language` is ISO 639-1). Stateless — the
 *  device caches translations per target language. */
export type TranslatedQuestions = { language: string; translations: string[] };

export const translateQuestions = (
  texts: string[],
  dishName: string,
  origin?: string | null,
  language?: string | null,
) =>
  request<TranslatedQuestions>(
    "/questions/translate",
    json("POST", {
      texts,
      dish_name: dishName,
      origin: origin ?? null,
      language: language ?? null,
    }),
  );

// Fixed id of the backend's canned demo menu (see backend routers/menus.py).
export const DEMO_MENU_ID = "00000000-0000-0000-0000-00000000aaaa";
