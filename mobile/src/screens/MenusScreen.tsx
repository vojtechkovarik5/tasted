// Menus tab: the user's scan history.
//
// GET /menus is user-scoped on the backend (resolved from the auth header —
// deliberately NOT a ?user_id= query param, which anyone could spoof).
//
// The list always leads with this session's scan (`localMenu`), refetched by
// id so its status/item count are live. Signed in, the rest of the server
// history follows (deduped); logged out there is no server history — that
// one current menu is all there is.

import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { getMenu, listMenus, Menu, MenuSummary } from "../api";
import { useAuth } from "../auth";
import { Card } from "../components";
import { radius, spacing, useTheme } from "../theme";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString();
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
  };
}

export default function MenusScreen(props: {
  localMenu?: Menu | null; // latest scan this session (the logged-out "current menu")
  onOpenMenu: (menu: Menu) => void;
}) {
  const { colors } = useTheme();
  const { isSignedIn } = useAuth();
  const [menus, setMenus] = useState<MenuSummary[] | null>(null);
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

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ padding: spacing.xl, paddingTop: 70, paddingBottom: 120 }}
    >
      <Text style={[styles.title, { color: colors.text }]}>Menus</Text>
      <Text style={{ color: colors.textMuted, marginTop: 4 }}>your scan history</Text>

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
        <Pressable key={m.id} onPress={() => open(m)}>
          <Card style={{ marginTop: spacing.m }}>
            <View style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: 17, fontWeight: "700" }}>
                  {m.name ?? "Untitled menu"}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 2 }}>
                  {m.id === currentId ? "current" : fmtDate(m.created_at)} · {m.item_count} dishes
                </Text>
              </View>
              {m.status === "processing" ? (
                <View style={[styles.pill, { backgroundColor: colors.warnBg }]}>
                  <Text style={{ color: colors.warnText, fontSize: 12 }}>resolving…</Text>
                </View>
              ) : (
                <Text style={{ color: colors.textMuted }}>›</Text>
              )}
            </View>
          </Card>
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 30, fontWeight: "800" },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.m },
  pill: {
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
});
