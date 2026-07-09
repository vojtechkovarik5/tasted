// One menu's items (opened right after a scan, or from history).
//
// Implements the async pattern: "ready" items render as full cards, "pending"
// ones as skeletons. While the menu is still "processing" this screen polls
// GET /menus/{id} (pollMenu) and re-renders on every update, so cards flip
// to ready as the backend pipeline resolves them.

import { useEffect, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Menu, MenuItem, pollMenu, resolveUrl } from "../api";
import { Card, CircleBtn, Skeleton } from "../components";
import { isWatched, WATCHED_DIETARY } from "../prefs";
import { radius, spacing, useTheme } from "../theme";

const THUMB = 64;

function fmtPrice(item: MenuItem): { main: string | null; approx: string | null } {
  const mp = item.menu_price;
  const ap = item.approx_price;
  return {
    main: mp ? `€${mp.amount.toFixed(2)}` : null,
    approx: ap ? `≈ ${Math.round(ap.amount)} ${ap.currency === "CZK" ? "Kč" : ap.currency}` : null,
  };
}

/** Small colored tag on a list card ("Gluten 99%", "× Vegetarian", "🌶 3.2"). */
function Tag(props: { label: string; fg: string; bg: string }) {
  return (
    <View style={[styles.tag, { backgroundColor: props.bg }]}>
      <Text style={{ color: props.fg, fontSize: 11, fontWeight: "600" }}>{props.label}</Text>
    </View>
  );
}

/** Badges for a ready dish: watched restrictions first, then spice. */
function ItemTags(props: { item: MenuItem }) {
  const { colors } = useTheme();
  const info = props.item.dish!.info;
  const tags: { label: string; fg: string; bg: string }[] = [];

  for (const a of info.allergens) {
    if (isWatched(a.name) && a.probability >= 0.5) {
      const name = a.name[0].toUpperCase() + a.name.slice(1);
      tags.push({
        label: `${name} ${Math.round(a.probability * 100)}%`,
        fg: colors.danger,
        bg: colors.dangerBg,
      });
    }
  }
  for (const d of info.dietary) {
    if (WATCHED_DIETARY.has(d.name) && d.probability < 0.5) {
      const name = d.name[0].toUpperCase() + d.name.slice(1);
      tags.push({ label: `× ${name}`, fg: colors.success, bg: colors.successBg });
    }
  }
  if (info.spice_level >= 0.5) {
    tags.push({
      label: `🌶 ${info.spice_level.toFixed(1)}`,
      fg: colors.text,
      bg: colors.surfaceAlt,
    });
  }
  if (tags.length === 0) return null;
  return (
    <View style={styles.tagRow}>
      {tags.map((t) => (
        <Tag key={t.label} {...t} />
      ))}
    </View>
  );
}

/** Photo thumbnail, placeholder when the dish has no photos yet. */
function Thumb(props: { item: MenuItem }) {
  const { colors } = useTheme();
  const photo = props.item.dish?.photos[0];
  if (photo) {
    return (
      <Image
        source={{ uri: resolveUrl(photo.url) }}
        style={[styles.thumb, { backgroundColor: colors.surfaceAlt }]}
      />
    );
  }
  return (
    <View
      style={[
        styles.thumb,
        styles.thumbPlaceholder,
        { backgroundColor: colors.surfaceAlt, borderColor: colors.border },
      ]}
    >
      <Text style={{ fontSize: 22, opacity: 0.5 }}>🍽</Text>
    </View>
  );
}

/** Skeleton card while the AI is still identifying a dish. */
function PendingCard(props: { item: MenuItem }) {
  const { colors } = useTheme();
  return (
    <Card style={{ marginTop: spacing.m }}>
      <View style={styles.cardRow}>
        <Skeleton style={{ width: THUMB, height: THUMB, borderRadius: radius.s }} />
        <View style={{ flex: 1, gap: spacing.s }}>
          <Text style={{ color: colors.text, fontSize: 16, fontWeight: "600" }}>
            {props.item.original_name}
          </Text>
          <Skeleton style={{ height: 12, width: "90%" }} />
          <Skeleton style={{ height: 12, width: "55%" }} />
        </View>
      </View>
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: spacing.s }}>
        {props.item.status === "failed" ? "couldn't identify this one" : "identifying dish…"}
      </Text>
    </Card>
  );
}

function ItemCard(props: { item: MenuItem; onOpen: (item: MenuItem) => void }) {
  const { colors } = useTheme();
  const { item } = props;

  if (item.status !== "ready" || !item.dish) return <PendingCard item={item} />;

  const price = fmtPrice(item);
  return (
    <Pressable onPress={() => props.onOpen(item)}>
      <Card style={{ marginTop: spacing.m }}>
        <View style={styles.cardRow}>
          <Thumb item={item} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: "700" }}>
              {item.dish.canonical_name}
            </Text>
            {item.dish.info.summary ? (
              <Text style={{ color: colors.textMuted, marginTop: 2 }} numberOfLines={1}>
                {item.dish.info.summary}
              </Text>
            ) : null}
            <ItemTags item={item} />
          </View>
          <View style={{ alignItems: "flex-end" }}>
            {price.main ? (
              <Text style={{ color: colors.text, fontWeight: "700" }}>{price.main}</Text>
            ) : null}
            {price.approx ? (
              <Text style={{ color: colors.textMuted, fontSize: 12 }}>{price.approx}</Text>
            ) : null}
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

export default function MenuScreen(props: {
  menu: Menu;
  onOpenItem: (item: MenuItem) => void;
  onBack: () => void;
}) {
  const { colors } = useTheme();
  const [menu, setMenu] = useState<Menu>(props.menu);

  // Poll while the backend pipeline is resolving items; every intermediate
  // response re-renders, so cards flip pending -> ready one by one.
  useEffect(() => {
    setMenu(props.menu);
    if (props.menu.status !== "processing") return;
    let live = true;
    pollMenu(props.menu.id, (m) => {
      if (live) setMenu(m);
    }).catch(() => {
      // Poll timeout/network error: keep whatever state we have; pending
      // cards stay as skeletons and the user can reopen from history.
    });
    return () => {
      live = false;
    };
  }, [props.menu]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.background }}
      contentContainerStyle={{ padding: spacing.xl, paddingTop: 60, paddingBottom: 120 }}
    >
      <View style={styles.headerRow}>
        <CircleBtn label="‹" size={44} onPress={props.onBack} />
        <View style={{ flex: 1 }}>
          <Text style={[styles.title, { color: colors.text }]} numberOfLines={1}>
            {menu.name ?? "Menu"}
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 13 }}>
            {menu.items.length} items
          </Text>
        </View>
        {menu.status === "processing" ? (
          <View style={[styles.statusPill, { backgroundColor: colors.warnBg }]}>
            <Text style={{ color: colors.warnText, fontSize: 12 }}>resolving…</Text>
          </View>
        ) : null}
      </View>

      {menu.items.map((item) => (
        <ItemCard key={item.id} item={item} onOpen={props.onOpenItem} />
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.m },
  title: { fontSize: 22, fontWeight: "800" },
  cardRow: { flexDirection: "row", gap: spacing.m, alignItems: "flex-start" },
  thumb: { width: THUMB, height: THUMB, borderRadius: radius.s },
  thumbPlaceholder: {
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderStyle: "dashed",
  },
  tagRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs + 2, marginTop: spacing.s },
  tag: {
    paddingHorizontal: spacing.s,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  statusPill: {
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
});
