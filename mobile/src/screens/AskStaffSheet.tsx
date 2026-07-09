// Ask the staff (design 2a) — bottom sheet over the dish detail.
//
// The saved questions (written once in the user's language, managed on
// Settings -> My questions) are translated into the staff's language in one
// round trip. The target is the menu's stored language (read off the photo
// during extraction, passed in as `menuLanguage`); menus scanned before
// languages were recorded have none, and POST /questions/translate then
// infers it from the dish. The active question renders as a big
// high-contrast card to show across the counter; "Say it" speaks it
// (expo-speech), "Bigger" bumps the type. A typed one-off question takes the
// same round trip and lands on the card — it is NOT saved to the list.
//
// Built on RN's Modal (no bottom-sheet library, matching the app's
// no-navigation-library stance).

import { useEffect, useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as Speech from "expo-speech";

import { getQuestions, MenuItem, Question, translateQuestions } from "../api";
import { CircleBtn, Skeleton } from "../components";
import { radius, spacing, useTheme } from "../theme";

// Flag shown on the card kicker, keyed by the backend's ISO 639-1 code.
const FLAGS: Record<string, string> = {
  en: "🇬🇧", de: "🇩🇪", fr: "🇫🇷", es: "🇪🇸", it: "🇮🇹", pt: "🇵🇹",
  nl: "🇳🇱", pl: "🇵🇱", cs: "🇨🇿", ja: "🇯🇵", zh: "🇨🇳", ko: "🇰🇷",
};

// "translations cached per target language" (design 2b note): survive sheet
// close/reopen without another LLM round trip. The language cache only backs
// up dishes whose menu didn't record a language (the backend infers one).
const translationCache = new Map<string, string>(); // `${lang}|${text}` -> translated
const languageCache = new Map<string, string>(); // dish id -> ISO 639-1

type Shown = { original: string; translated: string };

export default function AskStaffSheet(props: {
  item: MenuItem;
  menuLanguage?: string | null; // Menu.language — the translation target
  onClose: () => void;
  onEditQuestions?: () => void;
}) {
  const { colors } = useTheme();
  const dish = props.item.dish!; // sheet opens from a ready dish detail
  const origin = dish.info.origin;
  const menuLanguage = props.menuLanguage ?? null;

  const [saved, setSaved] = useState<Question[] | null>(null); // null = loading
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const [language, setLanguage] = useState<string | null>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [bigger, setBigger] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const qs = await getQuestions().catch(() => [] as Question[]);
      if (cancelled) return;
      setSaved(qs);
      if (qs.length === 0) return;

      let lang = menuLanguage ?? languageCache.get(dish.id);
      const missing = qs.filter((q) => !lang || !translationCache.has(`${lang}|${q.text}`));
      if (missing.length > 0) {
        try {
          const res = await translateQuestions(
            missing.map((q) => q.text),
            dish.canonical_name,
            origin,
            menuLanguage,
          );
          lang = res.language;
          languageCache.set(dish.id, lang);
          missing.forEach((q, i) =>
            translationCache.set(`${lang}|${q.text}`, res.translations[i]),
          );
        } catch {
          // Rows fall back to the original text below.
        }
      }
      if (cancelled) return;

      const map: Record<string, string> = {};
      for (const q of qs) {
        map[q.text] = (lang && translationCache.get(`${lang}|${q.text}`)) || q.text;
      }
      setLanguage(lang ?? null);
      setTranslations(map);
      setShown({ original: qs[0].text, translated: map[qs[0].text] });
    })();
    return () => {
      cancelled = true;
    };
  }, [dish.id]);

  /** Send = translate the typed question, then show it big (not saved). */
  async function send() {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      const res = await translateQuestions([text], dish.canonical_name, origin, menuLanguage);
      languageCache.set(dish.id, res.language);
      translationCache.set(`${res.language}|${text}`, res.translations[0]);
      setLanguage(res.language);
      setShown({ original: text, translated: res.translations[0] });
      setDraft("");
    } catch {
      // Keep the draft so the user can retry.
    } finally {
      setSending(false);
    }
  }

  function sayIt() {
    if (shown) Speech.speak(shown.translated, language ? { language } : undefined);
  }

  return (
    <Modal transparent animationType="slide" visible onRequestClose={props.onClose}>
      <View style={[styles.backdrop, { backgroundColor: colors.overlay }]}>
        <Pressable style={{ flex: 1 }} onPress={props.onClose} />
        <View style={[styles.sheet, { backgroundColor: colors.background }]}>
          {/* ── Header ── */}
          <View style={styles.headerRow}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.title, { color: colors.text }]}>Ask the staff</Text>
              <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 2 }}>
                about <Text style={{ fontWeight: "700" }}>{dish.canonical_name}</Text>
                {origin ? ` · ${origin}` : ""}
              </Text>
            </View>
            <CircleBtn label="✕" onPress={props.onClose} />
          </View>

          {/* ── The show-it card ── */}
          {shown ? (
            <View style={[styles.card, { backgroundColor: colors.chipActiveBg }]}>
              <Text style={[styles.kicker, { color: colors.chipActiveText }]}>
                SHOW THIS TO THE STAFF{language && FLAGS[language] ? ` ${FLAGS[language]}` : ""}
              </Text>
              <Text
                style={{
                  color: colors.chipActiveText,
                  fontSize: bigger ? 40 : 28,
                  lineHeight: bigger ? 46 : 34,
                  fontWeight: "800",
                  marginTop: spacing.m,
                }}
              >
                {shown.translated}
              </Text>
              {shown.translated !== shown.original ? (
                <Text style={{ color: colors.chipActiveText, opacity: 0.55, marginTop: spacing.m }}>
                  {shown.original}
                </Text>
              ) : null}
              <View style={styles.cardBtnRow}>
                <Pressable onPress={sayIt} style={[styles.cardBtn, { borderColor: colors.chipActiveText }]}>
                  <Text style={{ color: colors.chipActiveText, fontWeight: "700" }}>🔊 Say it</Text>
                </Pressable>
                <Pressable
                  onPress={() => setBigger((b) => !b)}
                  style={[styles.cardBtn, { borderColor: colors.chipActiveText }]}
                >
                  <Text style={{ color: colors.chipActiveText, fontWeight: "700" }}>
                    A⁺ {bigger ? "Smaller" : "Bigger"}
                  </Text>
                </Pressable>
              </View>
            </View>
          ) : saved === null || (saved.length > 0 && !shown) ? (
            <Skeleton style={{ height: 180, marginTop: spacing.l }} />
          ) : null}

          {/* ── Your questions ── */}
          <View style={styles.listHeader}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Your questions</Text>
            <Pressable onPress={props.onEditQuestions} hitSlop={8}>
              <Text style={{ color: colors.primary, fontWeight: "600", fontSize: 13 }}>
                edit in Settings ›
              </Text>
            </Pressable>
          </View>

          {saved && saved.length === 0 ? (
            <Text style={{ color: colors.textMuted, fontSize: 13 }}>
              No saved questions yet — keep the ones you always ask in Settings, or type one below.
            </Text>
          ) : (
            <ScrollView style={{ maxHeight: 250 }}>
              {(saved ?? []).map((q) => {
                const showing = shown?.original === q.text;
                return (
                  <Pressable
                    key={q.id}
                    onPress={() =>
                      setShown({ original: q.text, translated: translations[q.text] ?? q.text })
                    }
                    style={[
                      styles.qRow,
                      {
                        backgroundColor: colors.surface,
                        borderColor: showing ? colors.text : colors.border,
                      },
                    ]}
                  >
                    <View style={{ flex: 1 }}>
                      <Text
                        numberOfLines={1}
                        style={{ color: colors.text, fontWeight: "700", fontSize: 15 }}
                      >
                        {q.text}
                      </Text>
                      {translations[q.text] && translations[q.text] !== q.text ? (
                        <Text
                          numberOfLines={1}
                          style={{ color: colors.textMuted, fontSize: 13, marginTop: 2 }}
                        >
                          {translations[q.text]}
                        </Text>
                      ) : null}
                    </View>
                    {showing ? (
                      <Text style={{ color: colors.primary, fontWeight: "700", fontSize: 11 }}>
                        SHOWING
                      </Text>
                    ) : null}
                  </Pressable>
                );
              })}
            </ScrollView>
          )}

          {/* ── One-off question ── */}
          <View style={styles.sendRow}>
            <TextInput
              value={draft}
              onChangeText={setDraft}
              placeholder="Write a new question..."
              placeholderTextColor={colors.textMuted}
              onSubmitEditing={send}
              style={[
                styles.input,
                { borderColor: colors.border, color: colors.text, backgroundColor: colors.surface },
              ]}
            />
            <Pressable
              onPress={send}
              disabled={!draft.trim() || sending}
              style={[
                styles.sendBtn,
                { backgroundColor: colors.chipActiveBg, opacity: draft.trim() && !sending ? 1 : 0.45 },
              ]}
            >
              <Text style={{ color: colors.chipActiveText, fontWeight: "700" }}>
                {sending ? "…" : "Send →"}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "flex-end" },
  sheet: {
    borderTopLeftRadius: radius.l,
    borderTopRightRadius: radius.l,
    padding: spacing.xl,
    paddingBottom: spacing.xl + 20, // home-indicator area
  },
  headerRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.m },
  title: { fontSize: 24, fontWeight: "800" },
  card: {
    borderRadius: radius.l,
    padding: spacing.xl,
    marginTop: spacing.l,
  },
  kicker: { fontSize: 11, fontWeight: "700", letterSpacing: 2, opacity: 0.7 },
  cardBtnRow: { flexDirection: "row", gap: spacing.m, marginTop: spacing.l },
  cardBtn: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.s + 2,
  },
  listHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginTop: spacing.xl,
    marginBottom: spacing.m,
  },
  sectionTitle: { fontSize: 16, fontWeight: "700" },
  qRow: {
    borderRadius: radius.m,
    borderWidth: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.m,
    marginBottom: spacing.s + 2,
  },
  sendRow: { flexDirection: "row", gap: spacing.m, marginTop: spacing.l },
  input: {
    flex: 1,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.m,
    fontSize: 15,
  },
  sendBtn: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.xl,
    justifyContent: "center",
  },
});
