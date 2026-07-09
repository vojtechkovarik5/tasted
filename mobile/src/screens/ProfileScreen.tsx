// Profile (designs 1f + 1d).
//
// Two states, split by auth:
//   signed OUT -> full sign-in screen (design 1f): Tasted branding, Clerk
//                 Apple/Google + email magic-code, "Skip for now" to browse.
//   signed IN  -> Settings (design 1d): account, watch chips, macros, the
//                 language + currency card, footer links, log out.
//
// Settings wiring (all user-scoped via the auth header on the backend):
//   watch chips  -> GET/POST /restrictions (allergens) + /dietary (diets)
//   language     -> GET /preferences/languages (options) + POST /preferences/language
//   currency     -> GET /currencies (options) + POST /currencies
//   macros + section order -> preferences blob (kept, not shown on this screen)
//   my questions -> GET /questions (count only; the list is its own screen, 2b)

import { useEffect, useState } from "react";
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  Currency,
  getCurrencies,
  getDietary,
  getLanguages,
  getPreferences,
  getQuestions,
  getRestrictions,
  Language,
  Preferences,
  putPreferences,
  setDietary,
  setMyCurrency,
  setMyLanguage,
  setRestrictions,
} from "../api";
import { useAuth } from "../auth";
import { Card, Chip, SectionHeader } from "../components";
import { loadPrefs } from "../prefs";
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

const DEFAULT_PREFS: Preferences = {
  watch_list: [],
  macros: ["protein", "fat"],
  section_order: ["restrictions", "macros", "spice_price"],
  currency: "CZK",
  language: "en",
};

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
const EMAIL_RE = /\S+@\S+\.\S+/;

/** Signed-out state (design 1f): the full sign-in screen. */
function LoginView(props: { onSkip?: () => void }) {
  const { colors } = useTheme();
  const { signIn, signInWithEmail } = useAuth();
  const [email, setEmail] = useState("");
  const emailValid = EMAIL_RE.test(email.trim());

  return (
    <View style={{ flex: 1 }}>
      <View style={{ flex: 1, justifyContent: "center" }}>
        <Text style={[styles.brand, { color: colors.text }]}>Tasted</Text>
        <Text style={[styles.brandSub, { color: colors.textMuted }]}>
          Sign in to vote, sync your restrictions and keep menus across devices
        </Text>

        <Card style={{ marginTop: spacing.xxl }}>
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

          <View style={styles.orRow}>
            <View style={[styles.orLine, { backgroundColor: colors.border }]} />
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>OR</Text>
            <View style={[styles.orLine, { backgroundColor: colors.border }]} />
          </View>

          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="email address"
            placeholderTextColor={colors.textMuted}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            onSubmitEditing={() => emailValid && signInWithEmail(email.trim())}
            style={[styles.input, { borderColor: colors.border, color: colors.text }]}
          />
          <Pressable
            disabled={!emailValid}
            onPress={() => signInWithEmail(email.trim())}
            style={[
              styles.authBtn,
              {
                backgroundColor: colors.background,
                borderWidth: 1,
                borderColor: colors.text,
                opacity: emailValid ? 1 : 0.45,
              },
            ]}
          >
            <Text style={{ color: colors.text, fontWeight: "700" }}>Continue →</Text>
          </Pressable>
        </Card>

        <Text style={[styles.securedText, { color: colors.textMuted }]}>
          🔒 Secured by Clerk · no password, magic code by email
        </Text>
      </View>

      <Pressable onPress={props.onSkip} style={{ paddingVertical: spacing.l }}>
        <Text style={{ color: colors.primary, textAlign: "center", fontWeight: "600" }}>
          Skip for now — browse without an account
        </Text>
      </Pressable>
    </View>
  );
}

/** Signed-in state (design 1d): account header + all settings. */
function SettingsView(props: { onOpenQuestions?: () => void }) {
  const { colors } = useTheme();
  const { user, signOut } = useAuth();

  const [restrictions, setRestrictionsState] = useState<string[]>([]);
  const [dietary, setDietaryState] = useState<string[]>([]);
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS); // macros + order
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [languages, setLanguages] = useState<Language[]>([]);
  const [myCurrency, setMyCurrencyState] = useState("CZK");
  const [myLanguage, setMyLanguageState] = useState("en");
  const [questionCount, setQuestionCount] = useState<number | null>(null);
  const [open, setOpen] = useState<null | "language" | "currency">(null);

  useEffect(() => {
    getRestrictions().then(setRestrictionsState).catch(() => {});
    getDietary().then(setDietaryState).catch(() => {});
    getCurrencies().then(setCurrencies).catch(() => {});
    getLanguages().then(setLanguages).catch(() => {});
    getQuestions()
      .then((qs) => setQuestionCount(qs.length))
      .catch(() => {});
    getPreferences()
      .then((p) => {
        setPrefs(p);
        setMyCurrencyState(p.currency);
        setMyLanguageState(p.language);
      })
      .catch(() => {});
  }, []);

  /** Toggle a watch chip; sync the matching list to its endpoint.
   *  Every mutation also refreshes the shared prefs store (src/prefs.ts) so
   *  listing badges and price conversion pick the change up immediately. */
  function toggleWatch(key: string, kind: "allergen" | "dietary") {
    if (kind === "allergen") {
      const next = restrictions.includes(key)
        ? restrictions.filter((k) => k !== key)
        : [...restrictions, key];
      setRestrictionsState(next);
      setRestrictions(next).then(loadPrefs).catch(() => {});
    } else {
      const next = dietary.includes(key)
        ? dietary.filter((k) => k !== key)
        : [...dietary, key];
      setDietaryState(next);
      setDietary(next).then(loadPrefs).catch(() => {});
    }
  }

  function toggleMacro(m: string) {
    const next: Preferences = {
      ...prefs,
      macros: prefs.macros.includes(m)
        ? prefs.macros.filter((x) => x !== m)
        : [...prefs.macros, m],
    };
    setPrefs(next);
    putPreferences(next).then(loadPrefs).catch(() => {});
  }

  // Language/currency are patched via their own endpoints; mirror into `prefs`
  // too so a later putPreferences (macros) doesn't overwrite the fresh value.
  function pickLanguage(code: string) {
    setMyLanguageState(code);
    setOpen(null);
    setPrefs((p) => ({ ...p, language: code }));
    setMyLanguage(code).then(loadPrefs).catch(() => {});
  }

  function pickCurrency(code: string) {
    setMyCurrencyState(code);
    setOpen(null);
    setPrefs((p) => ({ ...p, currency: code }));
    setMyCurrency(code).then(loadPrefs).catch(() => {});
  }

  const watched = new Set([...restrictions, ...dietary]);
  const currency = currencies.find((c) => c.code === myCurrency);
  const currencyLabel = `${myCurrency}${currency?.symbol ? ` ${currency.symbol}` : ""}`;
  const languageLabel = languages.find((l) => l.code === myLanguage)?.name ?? myLanguage;

  return (
    <>
      <Text style={[styles.title, { color: colors.text }]}>Settings</Text>

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
            <Text style={{ color: colors.textMuted, fontSize: 13 }}>
              {user?.email} · voting & sync on
            </Text>
          </View>
          <Pressable onPress={() => Alert.alert("Account", "Manage your account")} hitSlop={8}>
            <Text style={{ color: colors.textMuted, fontWeight: "600" }}>Manage ›</Text>
          </Pressable>
        </View>
      </Card>

      {/* ── Watch out for ── */}
      <SectionHeader title="Watch out for" />
      <Text style={[styles.caption, { color: colors.textMuted }]}>
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

      {/* ── My questions (managed on their own screen, design 2b) ── */}
      <Card style={{ padding: 0, marginTop: spacing.xxl }}>
        <Pressable onPress={props.onOpenQuestions} style={styles.settingRow}>
          <View>
            <Text style={{ color: colors.text, fontSize: 15 }}>My questions</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }}>
              suggested when you ask the staff
            </Text>
          </View>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {questionCount != null ? `${questionCount} ` : ""}›
          </Text>
        </Pressable>
      </Card>

      {/* ── Language + currency (options from the backend) ── */}
      <Card style={{ padding: 0, marginTop: spacing.l }}>
        <Pressable
          onPress={() => setOpen((o) => (o === "language" ? null : "language"))}
          style={styles.settingRow}
        >
          <Text style={{ color: colors.text, fontSize: 15 }}>My language</Text>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {languageLabel} {open === "language" ? "▾" : "›"}
          </Text>
        </Pressable>
        {open === "language" ? (
          <View style={[styles.pickerWrap, { borderTopColor: colors.border }]}>
            {languages.map((l) => (
              <Chip
                key={l.code}
                label={l.name}
                active={l.code === myLanguage}
                onPress={() => pickLanguage(l.code)}
              />
            ))}
          </View>
        ) : null}

        <Pressable
          onPress={() => setOpen((o) => (o === "currency" ? null : "currency"))}
          style={[styles.settingRow, { borderTopWidth: 1, borderTopColor: colors.border }]}
        >
          <Text style={{ color: colors.text, fontSize: 15 }}>My currency</Text>
          <Text style={{ color: colors.text, fontWeight: "700" }}>
            {currencyLabel} {open === "currency" ? "▾" : "›"}
          </Text>
        </Pressable>
        {open === "currency" ? (
          <View style={[styles.pickerWrap, { borderTopColor: colors.border }]}>
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
      </Card>
      <Text style={[styles.caption, { color: colors.textMuted, marginTop: spacing.s }]}>
        menus translate into your language · converted prices at daily rate
      </Text>

      {/* ── Footer links ── */}
      <Text style={{ color: colors.textMuted, textAlign: "center", marginTop: spacing.xxl }}>
        My edits & votes
      </Text>

      {/* ── Log out ── */}
      <Pressable
        onPress={signOut}
        style={[styles.logoutBtn, { backgroundColor: colors.surface, borderColor: colors.border }]}
      >
        <Text style={{ color: colors.danger, fontWeight: "700", fontSize: 16 }}>Log out</Text>
      </Pressable>
    </>
  );
}

export default function ProfileScreen(props: {
  onSkip?: () => void;
  onOpenQuestions?: () => void;
}) {
  const { colors } = useTheme();
  const { isSignedIn } = useAuth();

  if (!isSignedIn) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: colors.background,
          paddingHorizontal: spacing.xl,
          paddingTop: 70,
          paddingBottom: 40,
        }}
      >
        <LoginView onSkip={props.onSkip} />
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ padding: spacing.xl, paddingTop: 70, paddingBottom: 120 }}
    >
      <SettingsView onOpenQuestions={props.onOpenQuestions} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 30, fontWeight: "800" },
  brand: { fontSize: 42, fontWeight: "800", textAlign: "center" },
  brandSub: {
    fontSize: 15,
    textAlign: "center",
    marginTop: spacing.m,
    paddingHorizontal: spacing.l,
    lineHeight: 21,
  },
  securedText: { fontSize: 12, textAlign: "center", marginTop: spacing.l },
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
  orRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    marginVertical: spacing.m,
  },
  orLine: { flex: 1, height: 1 },
  input: {
    borderWidth: 1,
    borderRadius: radius.l,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.l - 2,
    fontSize: 15,
  },
  caption: { marginTop: -spacing.s, marginBottom: spacing.m, fontSize: 13 },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.s + 2 },
  settingRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.l,
  },
  pickerWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.s + 2,
    padding: spacing.l,
    borderTopWidth: 1,
  },
  logoutBtn: {
    borderRadius: radius.l,
    borderWidth: 1,
    paddingVertical: spacing.l,
    alignItems: "center",
    marginTop: spacing.l,
  },
});
