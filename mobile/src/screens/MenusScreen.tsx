// Menus tab: the user's scan history — one menu per restaurant (design 1e).
//
// Each row: name + pencil (inline rename), date on the right, and a
// "2 scans · 12 dishes · 🇵🇹 Portuguese" line. Swiping a row left reveals
// Delete (works with mouse drag on web too).
//
// GET /menus is user-scoped on the backend (resolved from the auth header —
// deliberately NOT a ?user_id= query param, which anyone could spoof).
//
// The list always leads with this session's scan (`localMenu`), refetched by
// id so its status/item count are live. Signed in, the rest of the server
// history follows (deduped); logged out there is no server history — that
// one current menu is all there is.

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Animated,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  deleteMenu,
  getMenu,
  listMenus,
  Menu,
  MenuSummary,
  renameMenu,
} from "../api";
import { useAuth } from "../auth";
import { Card } from "../components";
import { radius, spacing, useTheme } from "../theme";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

/** Alert.alert is a no-op on react-native-web — fall back to window.alert. */
function notify(message: string) {
  if (Platform.OS === "web") {
    (globalThis as { alert?: (m: string) => void }).alert?.(message);
  } else {
    Alert.alert("Something went wrong", message);
  }
}

// Menu languages come from extraction as ISO 639-1 — label the common ones
// with a flag + English name; anything unknown shows its bare code.
const LANGUAGE_LABELS: Record<string, string> = {
  en: "🇬🇧 English",
  de: "🇩🇪 German",
  fr: "🇫🇷 French",
  es: "🇪🇸 Spanish",
  it: "🇮🇹 Italian",
  pt: "🇵🇹 Portuguese",
  nl: "🇳🇱 Dutch",
  pl: "🇵🇱 Polish",
  cs: "🇨🇿 Czech",
  sk: "🇸🇰 Slovak",
  hu: "🇭🇺 Hungarian",
  el: "🇬🇷 Greek",
  tr: "🇹🇷 Turkish",
  ja: "🇯🇵 Japanese",
  zh: "🇨🇳 Chinese",
  ko: "🇰🇷 Korean",
  th: "🇹🇭 Thai",
  vi: "🇻🇳 Vietnamese",
};

const DELETE_WIDTH = 88;

// Inner controls (pencil, save tick) live INSIDE the row's tap target. On
// react-native-web a click on them can also reach the row Pressable
// (stopPropagation across nested Pressables is unreliable), which navigated
// into the menu instead of editing. They stamp this timestamp on press and
// the row ignores taps that follow within the same click burst.
let lastInnerPress = 0;
const markInnerPress = () => {
  lastInnerPress = Date.now();
};

/** A row that slides left to reveal a Delete button (design 1e). Plain
 *  PanResponder + Animated — no gesture library, and mouse-draggable on web.
 *  Taps pass through to `onPress` when the row isn't open. */
function SwipeableRow(props: {
  children: React.ReactNode;
  onPress: () => void;
  onDelete: () => void;
  pressDisabled?: boolean; // while renaming, taps must reach the TextInput
}) {
  const { colors } = useTheme();
  const translateX = useRef(new Animated.Value(0)).current;
  const offset = useRef(0); // committed position: 0 (closed) or -DELETE_WIDTH
  const dragging = useRef(false);

  const snap = (to: number) => {
    offset.current = to;
    Animated.spring(translateX, { toValue: to, useNativeDriver: true, bounciness: 4 }).start();
  };

  const isHorizontal = (_e: unknown, g: { dx: number; dy: number }) =>
    Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy) * 1.2;

  const pan = useRef(
    PanResponder.create({
      // Claim only clearly-horizontal moves so vertical list scrolling wins.
      // Capture phase too, so the inner Pressable can't hold onto the touch.
      onMoveShouldSetPanResponder: isHorizontal,
      onMoveShouldSetPanResponderCapture: isHorizontal,
      // Don't let the enclosing ScrollView steal a swipe that already
      // started — without this iOS terminates the pan after a few pixels.
      onPanResponderTerminationRequest: () => false,
      onShouldBlockNativeResponder: () => true,
      onPanResponderGrant: () => {
        dragging.current = true;
      },
      onPanResponderMove: (_e, g) => {
        const x = Math.min(0, Math.max(-DELETE_WIDTH * 1.4, offset.current + g.dx));
        translateX.setValue(x);
      },
      onPanResponderRelease: (_e, g) => {
        const open = offset.current + g.dx < -DELETE_WIDTH / 2;
        snap(open ? -DELETE_WIDTH : 0);
        // Let the tap-suppression flag outlive this event loop's click.
        setTimeout(() => {
          dragging.current = false;
        }, 50);
      },
      onPanResponderTerminate: () => {
        snap(offset.current);
        dragging.current = false;
      },
    }),
  ).current;

  return (
    <View style={{ marginTop: spacing.m }}>
      {/* The revealed action, behind the sliding card. */}
      <Pressable
        onPress={props.onDelete}
        style={[styles.deleteAction, { backgroundColor: colors.primary }]}
      >
        <Text style={{ fontSize: 18 }}>🗑</Text>
        <Text style={{ color: colors.onPrimary, fontWeight: "700", fontSize: 13 }}>Delete</Text>
      </Pressable>
      <Animated.View
        style={[
          { transform: [{ translateX }] },
          // Web: keep a horizontal drag a drag — no text selection ghost,
          // and tell touch browsers vertical panning stays native.
          Platform.OS === "web"
            ? ({ userSelect: "none", touchAction: "pan-y" } as object)
            : null,
        ]}
        {...pan.panHandlers}
      >
        <Pressable
          disabled={props.pressDisabled}
          onPress={() => {
            if (dragging.current) return; // a swipe, not a tap
            if (Date.now() - lastInnerPress < 400) return; // pencil/tick tap
            if (offset.current !== 0) {
              snap(0); // tap on an open row just closes it
              return;
            }
            props.onPress();
          }}
        >
          {props.children}
        </Pressable>
      </Animated.View>
    </View>
  );
}

function MenuRow(props: {
  summary: MenuSummary;
  isCurrent: boolean;
  editing: boolean;
  onEditStart: () => void;
  onEditEnd: () => void;
  onRenamed: (next: MenuSummary) => void;
}) {
  const { colors } = useTheme();
  const m = props.summary;
  const { editing } = props;
  const [draft, setDraft] = useState(m.name ?? "");
  const inputRef = useRef<TextInput>(null);

  // autoFocus is unreliable on react-native-web — without focus, clicking
  // away never blurs, onBlur never fires and the edit looks dead. Focus
  // explicitly once the input is mounted.
  useEffect(() => {
    if (editing) setTimeout(() => inputRef.current?.focus(), 50);
  }, [editing]);

  function commit() {
    props.onEditEnd();
    const name = draft.trim() || null;
    if (name === (m.name ?? null)) return;
    const previous = m;
    props.onRenamed({ ...m, name }); // optimistic
    renameMenu(m.id, name)
      .then(props.onRenamed)
      .catch(() => {
        // Failures must be visible, not a silently reverted name.
        props.onRenamed(previous);
        notify("Couldn't rename the menu — are you signed in and online?");
      });
  }

  const language = m.language ? LANGUAGE_LABELS[m.language] ?? m.language : null;
  const detail = [
    `${m.scan_count} ${m.scan_count === 1 ? "scan" : "scans"}`,
    `${m.item_count} dishes`,
    language,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card>
      <View style={styles.row}>
        <View style={{ flex: 1 }}>
          {editing ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.s }}>
              <TextInput
                ref={inputRef}
                value={draft}
                onChangeText={setDraft}
                placeholder="Restaurant name"
                placeholderTextColor={colors.textMuted}
                autoFocus
                onBlur={commit}
                onSubmitEditing={commit}
                style={[
                  styles.nameInput,
                  { color: colors.text, borderColor: colors.border, flex: 1 },
                ]}
              />
              {/* Explicit save — committing must not depend on blur firing. */}
              <Pressable
                hitSlop={10}
                onPressIn={markInnerPress}
                onPress={() => {
                  markInnerPress();
                  commit();
                }}
              >
                <Text style={{ color: colors.success, fontSize: 17, fontWeight: "700" }}>✓</Text>
              </Pressable>
            </View>
          ) : (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.s }}>
              <Text style={{ color: colors.text, fontSize: 17, fontWeight: "700" }}>
                {m.name ?? "Untitled menu"}
              </Text>
              <Pressable
                hitSlop={14}
                onPressIn={markInnerPress}
                onPress={() => {
                  markInnerPress();
                  setDraft(m.name ?? "");
                  props.onEditStart();
                }}
              >
                <Text style={{ fontSize: 14, opacity: 0.5 }}>✎</Text>
              </Pressable>
            </View>
          )}
          <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 2 }}>{detail}</Text>
        </View>
        {m.status === "processing" ? (
          <View style={[styles.pill, { backgroundColor: colors.warnBg }]}>
            <Text style={{ color: colors.warnText, fontSize: 12 }}>resolving…</Text>
          </View>
        ) : (
          <Text style={{ color: colors.textMuted, fontSize: 13 }}>
            {props.isCurrent ? "today" : fmtDate(m.created_at)}
          </Text>
        )}
      </View>
    </Card>
  );
}

export default function MenusScreen(props: {
  localMenu?: Menu | null; // latest scan this session (the logged-out "current menu")
  onOpenMenu: (menu: Menu) => void;
}) {
  const { colors } = useTheme();
  const { isSignedIn } = useAuth();
  const [menus, setMenus] = useState<MenuSummary[] | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState(false);

  const currentId = props.localMenu?.id ?? null;

  const load = useCallback(async () => {
    try {
      if (!isSignedIn) {
        // No server history when logged out — just the current menu, if any.
        setMenus(currentId ? [await summaryOf(currentId)] : []);
        return;
      }
      const history = await listMenus();
      if (!currentId) {
        setMenus(history);
        return;
      }
      // Current menu first, then the rest. If it isn't in the history (it
      // was scanned before signing in -> anonymous), fetch it by id.
      const current =
        history.find((m) => m.id === currentId) ?? (await summaryOf(currentId));
      setMenus([current, ...history.filter((m) => m.id !== currentId)]);
    } catch {
      setError(true);
    }
  }, [isSignedIn, currentId]);

  useEffect(() => {
    load();
  }, [load]);

  async function open(summary: MenuSummary) {
    try {
      props.onOpenMenu(await getMenu(summary.id));
    } catch {
      setError(true);
    }
  }

  function remove(summary: MenuSummary) {
    // Optimistic: drop the row now, restore on failure.
    setMenus((list) => (list ?? []).filter((m) => m.id !== summary.id));
    deleteMenu(summary.id).catch(() => {
      notify("Couldn't delete the menu — are you signed in and online?");
      load();
    });
  }

  function replace(next: MenuSummary) {
    setMenus((list) => (list ?? []).map((m) => (m.id === next.id ? next : m)));
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ padding: spacing.xl, paddingTop: 70, paddingBottom: 120 }}
    >
      <Text style={[styles.title, { color: colors.text }]}>Menus</Text>

      {error ? (
        <Text style={{ color: colors.danger, marginTop: spacing.xl }}>
          couldn't load history — is the backend running?
        </Text>
      ) : null}

      {!isSignedIn && menus !== null ? (
        <Text style={{ color: colors.textMuted, marginTop: spacing.m, fontSize: 13 }}>
          Sign in on the Profile tab to keep your scans across sessions.
        </Text>
      ) : null}

      {menus?.length === 0 ? (
        <Text style={{ color: colors.textMuted, marginTop: spacing.xl }}>
          No menus yet — scan your first one in the Scan tab.
        </Text>
      ) : null}

      {menus?.map((m) => (
        <SwipeableRow
          key={m.id}
          onPress={() => open(m)}
          onDelete={() => remove(m)}
          // While renaming, row taps must reach the TextInput, not navigate.
          pressDisabled={editingId === m.id}
        >
          <MenuRow
            summary={m}
            isCurrent={m.id === currentId}
            editing={editingId === m.id}
            onEditStart={() => setEditingId(m.id)}
            onEditEnd={() => setEditingId(null)}
            onRenamed={replace}
          />
        </SwipeableRow>
      ))}
    </ScrollView>
  );
}

/** Fresh one-row summary of a menu the server won't list (anonymous scan). */
async function summaryOf(id: string): Promise<MenuSummary> {
  const m = await getMenu(id);
  return {
    id: m.id,
    name: m.name,
    status: m.status,
    created_at: m.created_at,
    item_count: m.items.length,
    scan_count: 1, // MenuOut doesn't carry pages; a fresh local scan is one
    language: m.language,
  };
}

const styles = StyleSheet.create({
  title: { fontSize: 30, fontWeight: "800" },
  row: { flexDirection: "row", alignItems: "flex-start", gap: spacing.m },
  pill: {
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  nameInput: {
    fontSize: 17,
    fontWeight: "700",
    borderBottomWidth: 1,
    paddingVertical: 2,
  },
  deleteAction: {
    position: "absolute",
    top: 0,
    bottom: 0,
    right: 0,
    width: DELETE_WIDTH,
    borderTopRightRadius: radius.l,
    borderBottomRightRadius: radius.l,
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
  },
});
