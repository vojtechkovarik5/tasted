// The user's synced preferences — one module-level store shared by the menu
// listing badges, DishDetail rows and price formatting. Loaded from
// GET /preferences on app start (loadPrefs) and refreshed by the Profile
// screen whenever the user changes something there. Signed-out users keep
// the defaults (which mirror the backend's Preferences defaults).

import { useSyncExternalStore } from "react";
import { getPreferences, Preferences } from "./api";

const DEFAULT_PREFS: Preferences = {
  watch_list: [
    { key: "gluten", kind: "allergen", on: true },
    { key: "vegetarian", kind: "dietary", on: true },
  ],
  macros: ["protein", "fat"],
  section_order: ["restrictions", "macros", "spice_price"],
  currency: "CZK",
  language: "en",
};

let prefs: Preferences = DEFAULT_PREFS;
const listeners = new Set<() => void>();

export function setLocalPrefs(next: Preferences) {
  prefs = next;
  listeners.forEach((l) => l());
}

/** Fetch the synced preferences into the store. Silent failure (signed out /
 *  offline) keeps whatever we have — defaults at worst. */
export async function loadPrefs(): Promise<void> {
  try {
    setLocalPrefs(await getPreferences());
  } catch {
    // keep current prefs
  }
}

/** Reactive read — components re-render when the store updates. */
export function usePrefs(): Preferences {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => prefs,
  );
}

export const watchedAllergens = (p: Preferences) =>
  new Set(p.watch_list.filter((c) => c.on && c.kind === "allergen").map((c) => c.key));

export const watchedDietary = (p: Preferences) =>
  new Set(p.watch_list.filter((c) => c.on && c.kind === "dietary").map((c) => c.key));

export const isWatched = (name: string, p: Preferences) =>
  p.watch_list.some((c) => c.on && c.key === name);
