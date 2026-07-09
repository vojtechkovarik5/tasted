// What the current user watches — shared by Home badges and DishDetail rows.
// TODO: replace with real preferences state (MMKV + context) fed by the
// Profile screen; hardcoded for now.

export const WATCHED_ALLERGENS = new Set(["gluten"]);
export const WATCHED_DIETARY = new Set(["vegetarian"]);

export const isWatched = (name: string) =>
  WATCHED_ALLERGENS.has(name) || WATCHED_DIETARY.has(name);
