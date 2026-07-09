// Design tokens for the whole app.
//
// HOW TO CHANGE COLORS: edit `lightColors` (and `darkColors`) below — nothing
// else. Every component reads colors through `useTheme()`, so there are no
// hardcoded hex values anywhere in the screens.
//
// HOW TO ADD DARK MODE LATER: the dark palette already exists; switch the
// value passed to <ThemeProvider> in App.tsx (e.g. based on
// `useColorScheme()` from react-native) and everything follows.

import { createContext, useContext } from "react";

export const lightColors = {
  // surfaces
  background: "#EFEAE0", // warm beige app background
  surface: "#FDFBF7", // cards
  surfaceAlt: "#F3EEE3", // photo placeholder / subtle blocks
  border: "#E5DECE",

  // text
  text: "#2B2318", // near-black warm ink
  textMuted: "#8B8171",

  // brand / actions
  primary: "#B8492B", // terracotta — CTA buttons
  onPrimary: "#FFFFFF",

  // chips (Profile screen)
  chipBg: "#FDFBF7",
  chipActiveBg: "#2B2318",
  chipActiveText: "#FFF7EC",

  // semantic
  success: "#3E7A46", // dietary OK (vegetarian...)
  successBg: "#E9F1E5",
  danger: "#B03A2E", // allergen warnings
  dangerBg: "#F7E9E2",
  warnBg: "#F7F0DA", // "regional specialty" banner
  warnText: "#6C5B2A",

  // probability bars
  barTrack: "#E4DDCC",
  barNeutral: "#A99F8B",

  // scrim behind bottom sheets / modals
  overlay: "rgba(43, 35, 24, 0.45)",
};

export type Palette = typeof lightColors;

// Dark palette — same tokens, darker values. Not wired to a toggle yet.
export const darkColors: Palette = {
  background: "#1C1813",
  surface: "#282219",
  surfaceAlt: "#2F2820",
  border: "#3D352A",

  text: "#F2EBDD",
  textMuted: "#A79C89",

  primary: "#D06A4A",
  onPrimary: "#FFFFFF",

  chipBg: "#282219",
  chipActiveBg: "#F2EBDD",
  chipActiveText: "#1C1813",

  success: "#7CB47F",
  successBg: "#233123",
  danger: "#E07B63",
  dangerBg: "#3A2620",
  warnBg: "#332C1B",
  warnText: "#D8C787",

  barTrack: "#3D352A",
  barNeutral: "#8B8171",

  overlay: "rgba(0, 0, 0, 0.55)",
};

export const spacing = { xs: 4, s: 8, m: 12, l: 16, xl: 20, xxl: 28 } as const;
export const radius = { s: 10, m: 14, l: 22, pill: 999 } as const;

type Theme = { colors: Palette; mode: "light" | "dark" };

const ThemeContext = createContext<Theme>({ colors: lightColors, mode: "light" });

export const ThemeProvider = ThemeContext.Provider;

export function useTheme(): Theme {
  return useContext(ThemeContext);
}
