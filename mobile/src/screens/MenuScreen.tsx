// One menu's items (opened right after a scan, or from history).
//
// Two worlds, one link (design 3a): the card is FAITHFUL TO THE MENU —
// original + translated name, the printed description, the printed
// "Contains"/"Allergens" lines and the printed price (with a conversion to
// the user's currency). Below that sits the OPTIONAL canonical-dish match:
// family name + confidence + "About the dish ›", with tags driven by what
// the user tracks in settings (Regional always; allergens, ingredients,
// diet fit and macros only when tracked; spice/price level when > 0.5).
// A ready item with no match shows "dish stays as written".
//
// Implements the async pattern: "ready" items render as full cards, "pending"
// ones as skeletons. While the menu is still "processing" this screen polls
// GET /menus/{id} (pollMenu) and re-renders on every update, so cards flip
// to ready as the backend pipeline resolves them.

import { useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Menu, MenuItem, pollMenu, Preferences } from "../api";
import { Card, CircleBtn, IconMeter, Skeleton } from "../components";
import { currencySymbol, fmtMoney } from "../money";
import {
  usePrefs,
  watchedAllergens,
  watchedDietary,
  watchedIngredients,
} from "../prefs";
import { radius, spacing, useTheme } from "../theme";
import AskStaffSheet from "./AskStaffSheet";

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

/** The match card's tag row — everything here is about the MATCHED FAMILY,
 *  filtered by what the user tracks: Regional always (when present), watched
 *  allergens, tracked ingredients, tracked diet fit, tracked macros. */
function MatchTags(props: { item: MenuItem; prefs: Preferences }) {
  const { colors } = useTheme();
  const { prefs, item } = props;
  const info = item.dish!.info;
  const tags: { label: string; fg: string; bg: string }[] = [];

  const display = (row: { name: string; label: string | null }) =>
    cap(row.label ?? row.name.replace(/-/g, " "));

  // Regional — every time when present.
  if (item.regional_note) {
    tags.push({ label: "★ Regional", fg: colors.warnText, bg: colors.warnBg });
  }
  // Watched allergens: warn when likely present, reassure when checked-safe.
  for (const key of watchedAllergens(prefs)) {
    const found = info.allergens.find((a) => a.name === key);
    if (!found) continue;
    if (found.probability >= 0.5) {
      tags.push({ label: `⚠ ${display(found)}`, fg: colors.danger, bg: colors.dangerBg });
    } else {
      tags.push({
        label: `${display(found)} ${Math.round(found.probability * 100)}%`,
        fg: colors.success,
        bg: colors.successBg,
      });
    }
  }
  // Tracked ingredients likely in the typical dish.
  for (const key of watchedIngredients(prefs)) {
    const found = info.ingredients.find((i) => i.name === key);
    if (found && found.probability >= 0.5) {
      tags.push({ label: display(found), fg: colors.text, bg: colors.surfaceAlt });
    }
  }
  // Tracked diet fit: share of versions fitting the diet.
  for (const key of watchedDietary(prefs)) {
    const found = info.dietary.find((d) => d.name === key);
    if (!found) continue;
    const pct = Math.round(found.probability * 100);
    if (found.probability >= 0.5) {
      tags.push({ label: `✓ ${display(found)} ${pct}%`, fg: colors.success, bg: colors.successBg });
    } else {
      tags.push({ label: `× ${display(found)} ${pct}%`, fg: colors.danger, bg: colors.dangerBg });
    }
  }
  // Tracked macros (whole-dish average per 100 g).
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

  const showSpice = info.spice_level > 0.5;
  const showPriceLevel = info.price_level != null && info.price_level > 0.5;
  if (tags.length === 0 && !showSpice && !showPriceLevel) return null;
  return (
    <View style={styles.tagRow}>
      {tags.map((t) => (
        <Tag key={t.label} {...t} />
      ))}
      {/* Spice + price level, only when meaningful (> 0.5): 1-5 repeated
          icons, price level counted in the menu's own currency symbol. */}
      {showSpice ? (
        <View style={[styles.tag, styles.meterTag, { backgroundColor: colors.surface }]}>
          <IconMeter level={info.spice_level} icon="🌶️" iconSize={12} />
        </View>
      ) : null}
      {showPriceLevel ? (
        <View style={[styles.tag, styles.meterTag, { backgroundColor: colors.surface }]}>
          <IconMeter
            level={info.price_level!}
            icon={currencySymbol(props.item.menu_price?.currency)}
            iconSize={12}
            color={colors.text}
          />
        </View>
      ) : null}
    </View>
  );
}

/** The optional canonical-dish block under the printed lines: matched family
 *  + confidence + "About the dish ›", or the explicit no-match state. */
function MatchCard(props: {
  item: MenuItem;
  prefs: Preferences;
  onOpen: (item: MenuItem) => void;
}) {
  const { colors } = useTheme();
  const { item } = props;

  if (!item.dish) {
    // Ready but unmatched — a normal state, the menu stays the truth.
    return (
      <View style={[styles.noMatch, { borderColor: colors.border }]}>
        <Text style={{ color: colors.textMuted, fontSize: 13 }}>
          ✦ No confident match — dish stays as written
        </Text>
      </View>
    );
  }
  return (
    <Pressable onPress={() => props.onOpen(item)}>
      <View style={[styles.match, { backgroundColor: colors.surfaceAlt }]}>
        <View style={styles.matchHeader}>
          <Text style={{ color: colors.text, fontWeight: "700", flexShrink: 1 }}>
            ✦ {item.dish.canonical_name}
            {item.match_confidence != null ? (
              <Text style={{ color: colors.textMuted, fontWeight: "400" }}>
                {" "}
                · {item.match_confidence}%
              </Text>
            ) : null}
          </Text>
          <Text style={{ color: colors.warnText, fontWeight: "700", fontSize: 13 }}>
            About the dish ›
          </Text>
        </View>
        <MatchTags item={item} prefs={props.prefs} />
      </View>
    </Pressable>
  );
}

/** The printed lines — faithful to the menu: original name (muted, with the
 *  printed number), the user-language name in bold, the quoted description,
 *  and the printed Contains/Allergens rows. Same for pending and ready
 *  cards, since extraction lands before enrichment. */
function PrintedLines(props: { item: MenuItem; prefs: Preferences; numberOfLines?: number }) {
  const { colors } = useTheme();
  const { item, prefs } = props;
  const description = item.menu_description_translated ?? item.menu_description;
  const trackedIngredients = watchedIngredients(prefs);
  const trackedAllergens = watchedAllergens(prefs);
  return (
    <>
      <Text style={{ color: colors.textMuted, fontSize: 13 }}>
        {item.menu_number ? `${item.menu_number}. ` : ""}
        {item.original_name}
      </Text>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "700", marginTop: 1 }}>
        {item.translated_name ?? item.original_name}
      </Text>
      {description ? (
        <Text
          style={{ color: colors.textMuted, marginTop: 2, fontStyle: "italic" }}
          numberOfLines={props.numberOfLines ?? 2}
        >
          „{description}“
        </Text>
      ) : null}
      {item.menu_ingredients.length > 0 ? (
        <Text style={{ color: colors.text, fontSize: 13, marginTop: 4 }}>
          <Text style={{ fontWeight: "700" }}>Contains: </Text>
          {item.menu_ingredients.map((ing, i) => (
            <Text
              key={`${ing.key ?? ing.name}-${i}`}
              style={
                ing.key && trackedIngredients.has(ing.key)
                  ? { fontWeight: "700", color: colors.warnText }
                  : undefined
              }
            >
              {i > 0 ? " · " : ""}
              {ing.name}
            </Text>
          ))}
        </Text>
      ) : null}
      {item.menu_allergens.length > 0 ? (
        <Text style={{ color: colors.danger, fontSize: 13, marginTop: 2 }}>
          <Text style={{ fontWeight: "700" }}>Allergens: </Text>
          {item.menu_allergens.map((a, i) => (
            <Text
              key={`${a.key ?? a.name}-${i}`}
              style={
                a.key && trackedAllergens.has(a.key) ? { fontWeight: "800" } : undefined
              }
            >
              {i > 0 ? " · " : ""}
              {a.name}
            </Text>
          ))}
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

/** Skeleton card while the AI is still resolving the match. The printed
 *  fields (names, description, contains/allergens, price) already landed. */
function PendingCard(props: { item: MenuItem; prefs: Preferences }) {
  const { colors } = useTheme();
  return (
    <Card style={{ marginTop: spacing.m }}>
      <View style={styles.cardRow}>
        <View style={{ flex: 1, gap: 2 }}>
          <PrintedLines item={props.item} prefs={props.prefs} />
        </View>
        <PriceCol item={props.item} />
      </View>
      {props.item.status === "failed" ? (
        <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: spacing.s }}>
          couldn't process this one
        </Text>
      ) : (
        <Skeleton style={{ height: 44, borderRadius: radius.m, marginTop: spacing.m }} />
      )}
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

  if (item.status !== "ready") return <PendingCard item={item} prefs={props.prefs} />;

  return (
    <Card style={{ marginTop: spacing.m }}>
      <View style={styles.cardRow}>
        <View style={{ flex: 1 }}>
          <PrintedLines item={item} prefs={props.prefs} />
        </View>
        <View style={{ alignItems: "flex-end", gap: spacing.s }}>
          <PriceCol item={item} />
          <Pressable
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
      {/* The optional link into the canonical world. */}
      <MatchCard item={item} prefs={props.prefs} onOpen={props.onOpen} />
    </Card>
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
  tagRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs + 2, marginTop: spacing.s },
  tag: {
    paddingHorizontal: spacing.s,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  meterTag: { paddingVertical: 2 },
  match: {
    borderRadius: radius.m,
    padding: spacing.m,
    marginTop: spacing.m,
  },
  matchHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.m,
  },
  noMatch: {
    borderWidth: 1,
    borderStyle: "dashed",
    borderRadius: radius.m,
    padding: spacing.m,
    marginTop: spacing.m,
    alignItems: "center",
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
