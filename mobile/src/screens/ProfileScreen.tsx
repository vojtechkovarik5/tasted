// Profile (design 1d).
//
// Two states:
//   signed OUT -> login screen (Clerk-powered Apple/Google buttons)
//   signed IN  -> profile settings
//
// Settings wiring (all user-scoped via the auth header on the backend):
//   watch chips  -> GET/POST /restrictions (allergens) + /dietary (diets)
//   currency     -> GET /currencies (dropdown options) + POST /currencies
//   macros + "what matters most" order -> preferences blob (kept as is)

import { useEffect, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import {
  Currency,
  getCurrencies,
  getDietary,
  getPreferences,
  getRestrictions,
  Preferences,
  putPreferences,
  setDietary,
  setMyCurrency,
  setRestrictions,
} from "../api";
import { useAuth } from "../auth";
import { Card, Chip, SectionHeader } from "../components";
import { radius, spacing, useTheme } from "../theme";

// All chips offered in the UI; the user's saved lists decide which are on.
const ALL_CHIPS: { key: string; kind: "allergen" | "dietary" }[] = [
  { key: "gluten", kind: "allergen" },
  { key: "vegetarian", kind: "dietary" },
  { key: "milk", kind: "allergen" },
  { key: "egg", kind: "allergen" },
  { key: "fish", kind: "allergen" },
  { key: "pork", kind: "allergen" },
  { key: "lamb", kind: "allergen" },
];

const ALL_MACROS = ["protein", "fat", "carbs", "kcal"];

const SECTION_LABELS: Record<string, string> = {
  restrictions: "My restrictions",
  macros: "Macros",
  spice_price: "Spice · price level",
};

const DEFAULT_PREFS: Preferences = {
  watch_list: [],
  macros: ["protein", "fat"],
  section_order: ["restrictions", "macros", "spice_price"],
  currency: "CZK",
};

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/** Signed-out state: just the login card. */
function LoginView() {
  const { colors } = useTheme();
  const { signIn } = useAuth();
  return (
    <View style={{ flex: 1 }}>
      <Text style={[styles.title, { color: colors.text }]}>Profile</Text>
      <Card style={{ marginTop: spacing.xl }}>
        <View style={styles.signinHeader}>
          <View style={[styles.avatar, { backgroundColor: colors.warnBg }]}>
            <Text style={{ color: colors.warnText, fontWeight: "700" }}>?</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: "700" }}>
              Sign in to vote & sync
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 13 }}>
              scanning works without an account
            </Text>
          </View>
        </View>
        <Pressable
          onPress={() => signIn("oauth_apple")}
          style={[styles.authBtn, { backgroundColor: colors.chipActiveBg }]}
        >
          <Text style={{ color: colors.chipActiveText, fontWeight: "700" }}>
            Continue with Apple
          </Text>
        </Pressable>
        <Pressable
          onPress={() => signIn("oauth_google")}
          style={[styles.authBtn, { borderWidth: 1, borderColor: colors.border }]}
        >
          <Text style={{ color: colors.text, fontWeight: "700" }}>Continue with Google</Text>
        </Pressable>
      </Card>
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: spacing.m }}>
        Signing in lets you vote on dishes and keeps your preferences in sync
        across devices.
      </Text>
    </View>
  );
}

/** Signed-in state: account header + all settings. */
function SettingsView() {
  const { colors } = useTheme();
  const { user, signOut } = useAuth();

  const [restrictions, setRestrictionsState] = useState<string[]>([]);
  const [dietary, setDietaryState] = useState<string[]>([]);
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS); // macros + order
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [myCurrency, setMyCurrencyState] = useState("CZK");
  const [currencyOpen, setCurrencyOpen] = useState(false);

  useEffect(() => {
    getRestrictions().then(setRestrictionsState).catch(() => {});
    getDietary().then(setDietaryState).catch(() => {});
    getCurrencies().then(setCurrencies).catch(() => {});
    getPreferences()
      .then((p) => {
        setPrefs(p);
        setMyCurrencyState(p.currency);
      })
      .catch(() => {});
  }, []);

  /** Toggle a watch chip; sync the matching list to its endpoint. */
  function toggleWatch(key: string, kind: "allergen" | "dietary") {
    if (kind === "allergen") {
      const next = restrictions.includes(key)
        ? restrictions.filter((k) => k !== key)
        : [...restrictions, key];
      setRestrictionsState(next);
      setRestrictions(next).catch(() => {});
    } else {
      const next = dietary.includes(key)
        ? dietary.filter((k) => k !== key)
        : [...dietary, key];
      setDietaryState(next);
      setDietary(next).catch(() => {});
    }
  }

  function updatePrefs(next: Preferences) {
    setPrefs(next);
    putPreferences(next).catch(() => {});
  }

  function toggleMacro(m: string) {
    updatePrefs({
      ...prefs,
      macros: prefs.macros.includes(m)
        ? prefs.macros.filter((x) => x !== m)
        : [...prefs.macros, m],
    });
  }

  /** Move a priority row up one place. (Upgrade path: drag with
   *  react-native-draggable-flatlist.) */
  function moveUp(index: number) {
    if (index === 0) return;
    const order = [...prefs.section_order];
    [order[index - 1], order[index]] = [order[index], order[index - 1]];
    updatePrefs({ ...prefs, section_order: order });
  }

  function pickCurrency(code: string) {
    setMyCurrencyState(code);
    setCurrencyOpen(false);
    setMyCurrency(code).catch(() => {});
  }

  const watched = new Set([...restrictions, ...dietary]);
  const current = currencies.find((c) => c.code === myCurrency);

  return (
    <>
      <Text style={[styles.title, { color: colors.text }]}>Profile</Text>

      {/* ── Account ── */}
      <Card style={{ marginTop: spacing.l }}>
        <View style={styles.signinHeader}>
          <View style={[styles.avatar, { backgroundColor: colors.warnBg }]}>
            <Text style={{ color: colors.warnText, fontWeight: "700" }}>
              {user?.initials ?? "?"}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 16, fontWeight: "700" }}>
              {user?.name}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 13 }}>{user?.email}</Text>
          </View>
          <Pressable onPress={signOut} hitSlop={8}>
            <Text style={{ color: colors.danger, fontWeight: "600" }}>Sign out</Text>
          </Pressable>
        </View>
      </Card>

      {/* ── Watch out for ── */}
      <SectionHeader title="Watch out for" />
      <Text style={{ color: colors.textMuted, marginTop: -spacing.s, marginBottom: spacing.m }}>
        one list — allergens, diets, whole categories or exact meats
      </Text>
      <View style={styles.chipWrap}>
        {ALL_CHIPS.map((c) => (
          <Chip
            key={c.key}
            label={cap(c.key)}
            active={watched.has(c.key)}
            onPress={() => toggleWatch(c.key, c.kind)}
          />
        ))}
        <Chip label="+ Search..." dashed onPress={() => Alert.alert("TODO", "chip search")} />
      </View>

      {/* ── Macros ── */}
      <SectionHeader title="Macros I track" />
      <View style={styles.chipWrap}>
        {ALL_MACROS.map((m) => (
          <Chip
            key={m}
            label={m === "kcal" ? m : cap(m)}
            active={prefs.macros.includes(m)}
            onPress={() => toggleMacro(m)}
          />
        ))}
      </View>

      {/* ── Priority order ── */}
      <SectionHeader title="What matters most" />
      <Text style={{ color: colors.textMuted, marginTop: -spacing.s, marginBottom: spacing.m }}>
        tap ≡ to move up — sets badge order on every card
      </Text>
      <Card style={{ padding: 0 }}>
        {prefs.section_order.map((sec, i) => (
          <View
            key={sec}
            style={[
              styles.orderRow,
              i > 0 && { borderTopWidth: 1, borderTopColor: colors.border },
            ]}
          >
            <Pressable onPress={() => moveUp(i)} hitSlop={10}>
              <Text style={{ color: colors.textMuted, fontSize: 18 }}>≡</Text>
            </Pressable>
            <Text style={{ color: colors.text, fontSize: 15 }}>
              {i + 1}. {SECTION_LABELS[sec] ?? sec}
            </Text>
          </View>
        ))}
      </Card>

      {/* ── Currency (options from GET /currencies) ── */}
      <Pressable onPress={() => setCurrencyOpen((o) => !o)}>
        <Card style={{ marginTop: spacing.xxl }}>
          <View style={styles.currencyRow}>
            <Text style={{ color: colors.text, fontSize: 15 }}>My currency</Text>
            <Text style={{ color: colors.text, fontWeight: "700" }}>
              {myCurrency}
              {current?.symbol ? ` ${current.symbol}` : ""} {currencyOpen ? "▾" : "›"}
            </Text>
          </View>
        </Card>
      </Pressable>
      {currencyOpen ? (
        <View style={[styles.chipWrap, { marginTop: spacing.m }]}>
          {currencies.map((c) => (
            <Chip
              key={c.code}
              label={c.symbol ? `${c.code} ${c.symbol}` : c.code}
              active={c.code === myCurrency}
              onPress={() => pickCurrency(c.code)}
            />
          ))}
        </View>
      ) : null}
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: spacing.s }}>
        shown next to every original price · daily rate
      </Text>

      {/* ── Footer links ── */}
      <Text style={{ color: colors.textMuted, textAlign: "center", marginTop: spacing.xxl }}>
        My phrases · My edits & votes
      </Text>
    </>
  );
}

export default function ProfileScreen() {
  const { colors } = useTheme();
  const { isSignedIn } = useAuth();
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ padding: spacing.xl, paddingTop: 70, paddingBottom: 120 }}
    >
      {isSignedIn ? <SettingsView /> : <LoginView />}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 30, fontWeight: "800" },
  signinHeader: { flexDirection: "row", alignItems: "center", gap: spacing.m },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  authBtn: {
    borderRadius: radius.l,
    paddingVertical: spacing.l - 2,
    alignItems: "center",
    marginTop: spacing.m,
  },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.s + 2 },
  orderRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.l,
  },
  currencyRow: { flexDirection: "row", justifyContent: "space-between" },
});
