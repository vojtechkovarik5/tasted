// My questions (design 2b) — reached from Settings.
//
// The saved ask-the-staff questions, written once in the user's own language;
// the ask-staff sheet translates them into the menu's language at any table.
// Wiring:
//   list      -> GET /questions
//   add       -> POST /questions (typed, or a suggestion via "+ Add")
//   delete    -> DELETE /questions/{id}
//   reorder   -> PUT /questions/order (drag rows by the ≡ handle)
//   suggested -> GET /questions/suggestions (LLM, seeded from watch chips)
//
// Reordering is a hand-rolled PanResponder drag (no list library, matching
// the no-navigation-library stance): rows have a fixed height, so the target
// index is just a division; rows swap live as the finger crosses slots.

import { useEffect, useRef, useState } from "react";
import {
  Animated,
  PanResponder,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  addQuestion,
  deleteQuestion,
  getLanguages,
  getPreferences,
  getQuestions,
  getQuestionSuggestions,
  Question,
  QuestionSuggestions,
  reorderQuestions,
} from "../api";
import { CircleBtn, SectionHeader } from "../components";
import { radius, spacing, useTheme } from "../theme";

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

// Fixed row geometry so the drag math is exact: slot index = dy / SLOT.
const ROW_H = 56;
const ROW_GAP = spacing.m;
const SLOT = ROW_H + ROW_GAP;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

function moveItem<T>(arr: T[], from: number, to: number): T[] {
  const next = arr.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export default function MyQuestionsScreen(props: { onBack: () => void }) {
  const { colors } = useTheme();

  const [questions, setQuestions] = useState<Question[]>([]);
  const [suggestions, setSuggestions] = useState<QuestionSuggestions | null>(null);
  const [languageName, setLanguageName] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");

  // Drag state. The gesture callbacks outlive re-renders, so everything they
  // read/write lives in refs; `dragId` only drives styling + scroll lock.
  const [dragId, setDragId] = useState<string | null>(null);
  const questionsRef = useRef<Question[]>([]);
  const startIndexRef = useRef(0);
  const curIndexRef = useRef(0);
  const dragY = useRef(new Animated.Value(0)).current;

  /** Keep state and the ref the gesture reads in sync. */
  function setList(next: Question[]) {
    questionsRef.current = next;
    setQuestions(next);
  }

  useEffect(() => {
    getQuestions().then(setList).catch(() => {});
    getQuestionSuggestions().then(setSuggestions).catch(() => {});
    // "written once in Čeština" — resolve the language code to its endonym.
    Promise.all([getPreferences(), getLanguages()])
      .then(([prefs, languages]) =>
        setLanguageName(languages.find((l) => l.code === prefs.language)?.name ?? null),
      )
      .catch(() => {});
  }, []);

  function endDrag() {
    setDragId(null);
    dragY.setValue(0);
    if (curIndexRef.current !== startIndexRef.current) {
      reorderQuestions(questionsRef.current.map((q) => q.id)).catch(() => {});
    }
  }

  /** One responder per row render; refs carry the state across moves. */
  const responderFor = (index: number) =>
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        startIndexRef.current = index;
        curIndexRef.current = index;
        dragY.setValue(0);
        setDragId(questionsRef.current[index].id);
      },
      onPanResponderMove: (_e, g) => {
        const list = questionsRef.current;
        const target = clamp(
          startIndexRef.current + Math.round(g.dy / SLOT),
          0,
          list.length - 1,
        );
        if (target !== curIndexRef.current) {
          setList(moveItem(list, curIndexRef.current, target));
          curIndexRef.current = target;
        }
        // Keep the row under the finger, relative to its current slot.
        dragY.setValue(g.dy - (curIndexRef.current - startIndexRef.current) * SLOT);
      },
      onPanResponderRelease: endDrag,
      onPanResponderTerminate: endDrag,
    });

  function removeQuestion(q: Question) {
    setList(questionsRef.current.filter((x) => x.id !== q.id));
    deleteQuestion(q.id).catch(() => {});
  }

  async function saveQuestion(text: string) {
    try {
      const saved = await addQuestion(text);
      setList([...questionsRef.current, saved]);
      // A now-saved suggestion shouldn't keep being suggested.
      setSuggestions(
        (s) =>
          s && {
            ...s,
            questions: s.questions.filter((t) => t.toLowerCase() !== text.toLowerCase()),
          },
      );
    } catch {
      // Fire-and-forget UX elsewhere, but adds render from the response —
      // on failure just leave the list as it was.
    }
  }

  function submitDraft() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setAdding(false);
    saveQuestion(text);
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView
        scrollEnabled={dragId === null}
        contentContainerStyle={{ padding: spacing.xl, paddingTop: 70, paddingBottom: 60 }}
      >
        {/* ── Header ── */}
        <View style={styles.headerRow}>
          <CircleBtn label="‹" onPress={props.onBack} />
          <Text style={[styles.title, { color: colors.text }]}>My questions</Text>
        </View>
        <Text style={[styles.caption, { color: colors.textMuted }]}>
          {languageName ? `written once in ${languageName} · ` : ""}translated at any table
        </Text>

        {/* ── Saved questions (drag ≡ to reorder, ✕ to remove) ── */}
        {questions.map((q, i) => {
          const dragging = q.id === dragId;
          return (
            <Animated.View
              key={q.id}
              style={[
                styles.row,
                {
                  backgroundColor: colors.surface,
                  borderColor: dragging ? colors.text : colors.border,
                },
                dragging && { transform: [{ translateY: dragY }], zIndex: 10, elevation: 4 },
              ]}
            >
              <View {...responderFor(i).panHandlers} hitSlop={12} style={styles.handle}>
                <Text style={{ color: colors.textMuted, fontSize: 18 }}>≡</Text>
              </View>
              <Text
                numberOfLines={1}
                style={{ flex: 1, color: colors.text, fontSize: 15, fontWeight: "700" }}
              >
                {q.text}
              </Text>
              <Pressable onPress={() => removeQuestion(q)} hitSlop={12}>
                <Text style={{ color: colors.textMuted, fontSize: 16 }}>✕</Text>
              </Pressable>
            </Animated.View>
          );
        })}

        {/* ── Add a question ── */}
        {adding ? (
          <View style={[styles.row, { backgroundColor: colors.surface, borderColor: colors.text }]}>
            <TextInput
              value={draft}
              onChangeText={setDraft}
              placeholder="Write a new question..."
              placeholderTextColor={colors.textMuted}
              autoFocus
              onSubmitEditing={submitDraft}
              onBlur={() => !draft.trim() && setAdding(false)}
              style={{ flex: 1, color: colors.text, fontSize: 15 }}
            />
            <Pressable onPress={submitDraft} hitSlop={12} disabled={!draft.trim()}>
              <Text
                style={{
                  color: colors.primary,
                  fontWeight: "700",
                  opacity: draft.trim() ? 1 : 0.45,
                }}
              >
                Add →
              </Text>
            </Pressable>
          </View>
        ) : (
          <Pressable
            onPress={() => setAdding(true)}
            style={[styles.addRow, { borderColor: colors.textMuted }]}
          >
            <Text style={{ color: colors.textMuted, fontSize: 15 }}>+ Add a question...</Text>
          </Pressable>
        )}

        {/* ── Suggested for you (LLM, from the watch chips) ── */}
        {suggestions && suggestions.questions.length > 0 ? (
          <>
            <SectionHeader
              title="✦ Suggested for you"
              caption={`from ${suggestions.based_on.map(cap).join(" · ")}`}
            />
            {suggestions.questions.map((text) => (
              <View key={text} style={[styles.suggestionRow, { backgroundColor: colors.warnBg }]}>
                <Text
                  numberOfLines={1}
                  style={{ flex: 1, color: colors.text, fontSize: 15 }}
                >
                  {text}
                </Text>
                <Pressable onPress={() => saveQuestion(text)} hitSlop={12}>
                  <Text style={{ color: colors.primary, fontWeight: "700" }}>+ Add</Text>
                </Pressable>
              </View>
            ))}
            <Text style={[styles.footer, { color: colors.textMuted }]}>
              suggestions are generated from your Watch out for list
            </Text>
          </>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.m },
  title: { fontSize: 30, fontWeight: "800" },
  caption: { fontSize: 13, marginTop: spacing.s, marginBottom: spacing.xl },
  row: {
    height: ROW_H,
    marginBottom: ROW_GAP,
    borderRadius: radius.m,
    borderWidth: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    paddingHorizontal: spacing.l,
  },
  handle: { paddingVertical: spacing.s },
  addRow: {
    height: ROW_H,
    borderRadius: radius.m,
    borderWidth: 1,
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
  },
  suggestionRow: {
    height: ROW_H,
    marginBottom: ROW_GAP,
    borderRadius: radius.m,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    paddingHorizontal: spacing.l,
  },
  footer: { fontSize: 12, textAlign: "center", marginTop: spacing.s },
});
