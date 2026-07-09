// One menu's items (opened right after a scan, or from history).
//
// The listing mirrors the printed menu: items grouped under the menu's own
// section headers, original names/descriptions first with the user's
// translations underneath — plus the user's warnings (watched restrictions),
// tracked macros, spice and converted prices on every card.
//
// Implements the async pattern: "ready" items render as full cards, "pending"
// ones as skeletons. While the menu is still "processing" this screen polls
// GET /menus/{id} (pollMenu) and re-renders on every update, so cards flip
// to ready as the backend pipeline resolves them.

import { useEffect, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Menu, MenuItem, pollMenu, Preferences, resolveUrl } from "../api";
import { Card, CircleBtn, IconMeter, Skeleton } from "../components";
import { fmtMoney } from "../money";
import { usePrefs, watchedAllergens, watchedDietary } from "../prefs";
import { radius, spacing, useTheme } from "../theme";
import AskStaffSheet from "./AskStaffSheet";

const THUMB = 64;

function fmtPrice(item: MenuItem): { main: string | null; approx: string | null } {
  const mp = item.menu_price;
  const ap = item.approx_price;
  return {
    main: mp ? fmtMoney(mp) : null,
    // Approximation — whole numbers read faster across the table.
    approx: ap ? `≈ ${fmtMoney({ amount: Math.round(ap.amount), currency: ap.currency })}` : null,
  };
}

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/** Small colored tag on a list card ("Gluten 99%", "× Vegetarian", "🌶 3.2"). */
function Tag(props: { label: string; fg: string; bg: string }) {
  return (
    <View style={[styles.tag, { backgroundColor: props.bg }]}>
      <Text style={{ color: props.fg, fontSize: 11, fontWeight: "600" }}>{props.label}</Text>
    </View>
  );
}

/** Badges for a ready dish: every watched restriction, tracked macros,
 *  spice (always) and the regional note when the menu area has one. */
function ItemTags(props: { item: MenuItem; prefs: Preferences }) {
  const { colors } = useTheme();
  const { prefs } = props;
  const info = props.item.dish!.info;
  const tags: { label: string; fg: string; bg: string }[] = [];

  // Watched restrictions show on EVERY card — a safe card saying "Gluten 2%"
  // is as much information as a risky one saying "Gluten 99%".
  for (const key of watchedAllergens(prefs)) {
    const found = info.allergens.find((a) => a.name === key);
    if (!found) {
      tags.push({ label: `${cap(key)} —`, fg: colors.textMuted, bg: colors.surfaceAlt });
    } else if (found.probability >= 0.5) {
      tags.push({
        label: `${cap(key)} ${Math.round(found.probability * 100)}%`,
        fg: colors.danger,
        bg: colors.dangerBg,
      });
    } else {
      tags.push({
        label: `${cap(key)} ${Math.round(found.probability * 100)}%`,
        fg: colors.success,
        bg: colors.successBg,
      });
    }
  }
  for (const key of watchedDietary(prefs)) {
    const found = info.dietary.find((d) => d.name === key);
    if (!found) {
      tags.push({ label: `${cap(key)} —`, fg: colors.textMuted, bg: colors.surfaceAlt });
    } else if (found.probability < 0.5) {
      tags.push({ label: `× ${cap(key)}`, fg: colors.danger, bg: colors.dangerBg });
    } else {
      tags.push({ label: `✓ ${cap(key)}`, fg: colors.success, bg: colors.successBg });
    }
  }

  // Tracked macros (Profile -> "Macros I track"); skipped when none tracked.
  const m = info.macros;
  if (m) {
    const labels: Record<string, string | null> = {
      kcal: m.kcal != null ? `${Math.round(m.kcal)} kcal` : null,
      protein: m.protein_g != null ? `P ${Math.round(m.protein_g)}g` : null,
      fat: m.fat_g != null ? `F ${Math.round(m.fat_g)}g` : null,
      carbs: m.carbs_g != null ? `C ${Math.round(m.carbs_g)}g` : null,
    };
    for (const key of prefs.macros) {
      const label = labels[key];
      if (label) tags.push({ label, fg: colors.text, bg: colors.surfaceAlt });
    }
  }

  // Regional note when the dish is a local specialty.
  if (props.item.regional_note) {
    tags.push({ label: "★ regional", fg: colors.warnText, bg: colors.warnBg });
  }

  return (
    <>
      {tags.length > 0 ? (
        <View style={styles.tagRow}>
          {tags.map((t) => (
            <Tag key={t.label} {...t} />
          ))}
        </View>
      ) : null}
      {/* Spice + price level on every card — same 1-5 overlay meters as the
          detail screen, just smaller. Price level is the AI's "how pricy is
          this dish usually" estimate (info.price_level), not the menu price. */}
      <View style={styles.meterRow}>
        <IconMeter level={info.spice_level} icon="🌶️" iconSize={13} />
        {info.price_level != null ? (
          <IconMeter level={info.price_level} icon="€" iconSize={13} color={colors.text} />
        ) : null}
      </View>
    </>
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
        styles.thumbPlaceholder,
        { backgroundColor: colors.surfaceAlt, borderColor: colors.border },
      ]}
    >
      <Text style={{ fontSize: 22, opacity: 0.5 }}>🍽</Text>
    </View>
  );
}

/** Name + translation + printed description — same for pending and ready
 *  cards, since extraction lands before enrichment. */
function PrintedLines(props: { item: MenuItem; numberOfLines?: number }) {
  const { colors } = useTheme();
  const { item } = props;
  const description = item.menu_description_translated ?? item.menu_description;
  return (
    <>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "700" }}>
        {item.menu_number ? (
          <Text style={{ color: colors.textMuted }}>{item.menu_number}. </Text>
        ) : null}
        {item.original_name}
      </Text>
      {item.translated_name ? (
        <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 1 }}>
          {item.translated_name}
        </Text>
      ) : null}
      {description ? (
        <Text
          style={{ color: colors.textMuted, marginTop: 2 }}
          numberOfLines={props.numberOfLines ?? 2}
        >
          {description}
        </Text>
      ) : null}
    </>
  );
}

/** Right-hand price column — printed price + the user-currency conversion. */
function PriceCol(props: { item: MenuItem }) {
  const { colors } = useTheme();
  const price = fmtPrice(props.item);
  if (!price.main) return null;
  return (
    <View style={{ alignItems: "flex-end" }}>
      <Text style={{ color: colors.text, fontWeight: "700" }}>{price.main}</Text>
      {price.approx ? (
        <Text style={{ color: colors.textMuted, fontSize: 12 }}>{price.approx}</Text>
      ) : null}
    </View>
  );
}

/** Skeleton card while the AI is still identifying a dish. The printed
 *  fields (name, translation, description, price) are already extracted. */
function PendingCard(props: { item: MenuItem }) {
  const { colors } = useTheme();
  return (
    <Card style={{ marginTop: spacing.m }}>
      <View style={styles.cardRow}>
        <Skeleton style={{ width: THUMB, height: THUMB, borderRadius: radius.s }} />
        <View style={{ flex: 1, gap: 2 }}>
          <PrintedLines item={props.item} />
          <Skeleton style={{ height: 12, width: "55%", marginTop: spacing.s }} />
        </View>
        <PriceCol item={props.item} />
      </View>
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: spacing.s }}>
        {props.item.status === "failed" ? "couldn't identify this one" : "identifying dish…"}
      </Text>
    </Card>
  );
}

function ItemCard(props: {
  item: MenuItem;
  prefs: Preferences;
  onOpen: (item: MenuItem) => void;
  onAsk: (item: MenuItem) => void;
}) {
  const { colors } = useTheme();
  const { item } = props;

  if (item.status !== "ready" || !item.dish) return <PendingCard item={item} />;

  return (
    <Pressable onPress={() => props.onOpen(item)}>
      <Card style={{ marginTop: spacing.m }}>
        <View style={styles.cardRow}>
          <Thumb item={item} />
          <View style={{ flex: 1 }}>
            <PrintedLines item={item} />
            <ItemTags item={item} prefs={props.prefs} />
          </View>
          <View style={{ alignItems: "flex-end", gap: spacing.s }}>
            <PriceCol item={item} />
            <Pressable
              // stopPropagation: on web the click would bubble to the card's
              // Pressable and ALSO open the dish detail over the sheet.
              onPress={(e) => {
                e?.stopPropagation?.();
                props.onAsk(item);
              }}
              hitSlop={8}
              style={[styles.askBtn, { borderColor: colors.border }]}
            >
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: "600" }}>
                🗣️ Ask
              </Text>
            </Pressable>
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

/** The menu's own sections, in print order; ungrouped items lead. */
function groupItems(items: MenuItem[]): { group: MenuItem | null; items: MenuItem[] }[] {
  const sections: { key: string; group: MenuItem | null; items: MenuItem[] }[] = [];
  const byKey = new Map<string, { items: MenuItem[] }>();
  for (const item of items) {
    const key = item.group_name ?? "";
    let section = byKey.get(key);
    if (!section) {
      section = { items: [] };
      byKey.set(key, section);
      sections.push({ key, group: item.group_name ? item : null, items: section.items });
    }
    section.items.push(item);
  }
  return sections;
}

export default function MenuScreen(props: {
  menu: Menu;
  onOpenItem: (item: MenuItem) => void;
  onBack: () => void;
}) {
  const { colors } = useTheme();
  const prefs = usePrefs();
  const [menu, setMenu] = useState<Menu>(props.menu);
  const [askItem, setAskItem] = useState<MenuItem | null>(null);

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

  const sections = groupItems(menu.items);

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView
        style={{ flex: 1 }}
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

        {sections.map((section) => (
          <View key={section.group?.group_name ?? "__ungrouped__"}>
            {section.group ? (
              <View style={styles.groupHeader}>
                <Text style={[styles.groupTitle, { color: colors.text }]}>
                  {section.group.group_name}
                </Text>
                {section.group.group_name_translated &&
                section.group.group_name_translated !== section.group.group_name ? (
                  <Text style={{ color: colors.textMuted, fontSize: 13 }}>
                    {section.group.group_name_translated}
                  </Text>
                ) : null}
              </View>
            ) : null}
            {section.items.map((item) => (
              <ItemCard
                key={item.id}
                item={item}
                prefs={prefs}
                onOpen={props.onOpenItem}
                onAsk={setAskItem}
              />
            ))}
          </View>
        ))}
      </ScrollView>

      {askItem ? (
        <AskStaffSheet
          item={askItem}
          menuLanguage={menu.language}
          onClose={() => setAskItem(null)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.m },
  title: { fontSize: 22, fontWeight: "800" },
  groupHeader: {
    flexDirection: "row",
    alignItems: "baseline",
    gap: spacing.m,
    marginTop: spacing.xl,
  },
  groupTitle: { fontSize: 18, fontWeight: "800" },
  cardRow: { flexDirection: "row", gap: spacing.m, alignItems: "flex-start" },
  thumb: { width: THUMB, height: THUMB, borderRadius: radius.s },
  thumbPlaceholder: {
    width: THUMB,
    height: THUMB,
    borderRadius: radius.s,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderStyle: "dashed",
  },
  tagRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs + 2, marginTop: spacing.s },
  meterRow: { flexDirection: "row", alignItems: "center", gap: spacing.l, marginTop: spacing.s },
  tag: {
    paddingHorizontal: spacing.s,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  askBtn: {
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.m,
    paddingVertical: 4,
  },
  statusPill: {
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
});
