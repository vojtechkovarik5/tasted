// Dish detail (design 1c): photo header, name + price, description,
// regional-specialty banner, spice / price-level meters, "Watch out for"
// rows with inline voting, and the "Ask staff" CTA (opens the ask-staff
// bottom sheet, design 2a — see AskStaffSheet).
//
// Voting is optimistic: arrows nudge the local value slightly (a vote is one
// voice, not a whole step) and fire the API call in the background — the
// server reconciles the aggregate on the next fetch.

import { useState } from "react";
import { Alert, Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { MenuItem, resolveUrl, sendVote } from "../api";
import { Bar, CircleBtn, IconMeter, PrimaryButton } from "../components";
import { isWatched, WATCHED_DIETARY } from "../prefs";
import { radius, spacing, useTheme } from "../theme";
import AskStaffSheet from "./AskStaffSheet";

const VOTE_NUDGE = 0.25; // optimistic local shift per vote

function fmtMoney(amount: number, currency: string): string {
  const symbol = currency === "EUR" ? "€" : currency === "CZK" ? "Kč" : currency;
  return currency === "EUR" ? `${symbol}${amount.toFixed(2)}` : `${Math.round(amount)} ${symbol}`;
}

/** Label + vote arrows around a fractional icon meter. */
function LevelRow(props: {
  label: string;
  level: number;
  icon: string;
  color?: string;
  onVote: (dir: "up" | "down") => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.levelRow}>
      <Text style={[styles.levelLabel, { color: colors.text }]}>{props.label}</Text>
      <CircleBtn label="←" onPress={() => props.onVote("down")} />
      <View style={{ flex: 1, alignItems: "center" }}>
        <IconMeter level={props.level} icon={props.icon} color={props.color} />
        <Text style={{ color: colors.textMuted, fontSize: 11 }}>
          {props.level.toFixed(1)} / 5
        </Text>
      </View>
      <CircleBtn label="→" onPress={() => props.onVote("up")} />
    </View>
  );
}

export default function DishDetailScreen(props: {
  item: MenuItem;
  menuLanguage?: string | null; // Menu.language, for the ask-staff sheet
  onBack: () => void;
  onOpenQuestions?: () => void;
}) {
  const { colors } = useTheme();
  const { item } = props;
  const dish = item.dish!; // screen is only opened for ready items
  const info = dish.info;
  const photo = dish.photos[0];

  // Optimistic local copies of the votable values.
  const [spice, setSpice] = useState(info.spice_level);
  const [price, setPrice] = useState(info.price_level ?? 0);
  const [askOpen, setAskOpen] = useState(false);

  function voteLevel(target: "spice" | "price", dir: "up" | "down") {
    const delta = dir === "up" ? VOTE_NUDGE : -VOTE_NUDGE;
    if (target === "spice") setSpice((s) => Math.max(0, Math.min(5, s + delta)));
    else setPrice((p) => Math.max(0, Math.min(5, p + delta)));
    sendVote(dish.id, target, dir).catch(() => {}); // fire-and-forget
  }

  // "Watch out for" rows: user's watched entries first (design: "yours first").
  const rows = [
    ...info.allergens.map((a) => ({ kind: "allergen" as const, ...a })),
    ...info.dietary.map((d) => ({ kind: "dietary" as const, ...d })),
  ].sort((a, b) => Number(isWatched(b.name)) - Number(isWatched(a.name)));

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView contentContainerStyle={{ paddingBottom: 120 }}>
        {/* ── Photo header: real image when available, placeholder otherwise ── */}
        <View
          style={[
            styles.photoBox,
            { backgroundColor: colors.surfaceAlt, borderColor: colors.border },
          ]}
        >
          {photo ? (
            <Image
              source={{ uri: resolveUrl(photo.url) }}
              style={StyleSheet.absoluteFill}
              resizeMode="cover"
            />
          ) : (
            <>
              <Text style={{ color: colors.textMuted }}>{dish.canonical_name} photo</Text>
              <Pressable onPress={() => Alert.alert("TODO", "photo upload")}>
                <Text style={{ color: colors.textMuted, textDecorationLine: "underline" }}>
                  or browse files
                </Text>
              </Pressable>
            </>
          )}
          <View style={styles.photoTopRow}>
            <CircleBtn label="‹" size={44} onPress={props.onBack} />
            <View style={[styles.pagerPill, { backgroundColor: colors.chipActiveBg }]}>
              <Text style={{ color: colors.chipActiveText, fontSize: 12 }}>
                {dish.photos.length > 0
                  ? `1 of ${dish.photos.length} · swipe ←→`
                  : "no photos yet"}
              </Text>
            </View>
          </View>
          <Pressable
            onPress={() => Alert.alert("TODO", "photo upload")}
            style={[styles.addPhotoBtn, { backgroundColor: colors.surface }]}
          >
            <Text style={{ color: colors.text }}>+ Add photo</Text>
          </Pressable>
        </View>

        <View style={{ paddingHorizontal: spacing.xl }}>
          {/* ── Name + price ── */}
          <View style={styles.nameRow}>
            <Text style={[styles.name, { color: colors.text }]}>{dish.canonical_name}</Text>
            {item.menu_price ? (
              <View style={{ alignItems: "flex-end" }}>
                <Text style={[styles.price, { color: colors.text }]}>
                  {fmtMoney(item.menu_price.amount, item.menu_price.currency)}
                </Text>
                {item.approx_price ? (
                  <Text style={{ color: colors.textMuted, fontSize: 13 }}>
                    ≈ {fmtMoney(item.approx_price.amount, item.approx_price.currency)}
                  </Text>
                ) : null}
              </View>
            ) : null}
          </View>
          {info.aliases.length > 0 ? (
            <Text style={{ color: colors.textMuted, marginTop: 2 }}>
              Also: {info.aliases.join(" · ")}
            </Text>
          ) : null}

          {/* ── Description (rich version; lists use info.summary) ── */}
          <Text style={[styles.description, { color: colors.text }]}>{info.description}</Text>
          <Pressable onPress={() => Alert.alert("TODO", "suggest edit form")}>
            <Text style={{ color: colors.text, textDecorationLine: "underline", marginTop: 4 }}>
              Suggest edit
            </Text>
          </Pressable>

          {/* ── Regional specialty banner ── */}
          {item.regional_note ? (
            <View style={[styles.banner, { backgroundColor: colors.warnBg }]}>
              <Text style={{ color: colors.warnText }}>★ {item.regional_note}</Text>
            </View>
          ) : null}

          {/* ── Spice + price level meters (fractional fill) ── */}
          <LevelRow
            label="Spice"
            level={spice}
            icon="🌶️"
            onVote={(d) => voteLevel("spice", d)}
          />
          <LevelRow
            label="Price level"
            level={price}
            icon="€"
            color={colors.text}
            onVote={(d) => voteLevel("price", d)}
          />

          {/* ── Watch out for (informational — not votable) ── */}
          <View style={styles.watchHeader}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Watch out for</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>yours first</Text>
          </View>

          {rows.map((row) => {
            const watched = isWatched(row.name);
            const isDietary = row.kind === "dietary";
            // Dietary rows show a conflict when the diet is watched but the
            // probability of satisfying it is low ("Vegetarian x 2%").
            const conflict = isDietary && WATCHED_DIETARY.has(row.name) && row.probability < 0.5;
            const labelColor = watched
              ? isDietary
                ? colors.success
                : colors.danger
              : colors.text;
            const rowBg = watched
              ? isDietary
                ? colors.successBg
                : colors.dangerBg
              : "transparent";
            const barColor = watched
              ? isDietary
                ? colors.success
                : colors.danger
              : colors.barNeutral;
            return (
              <View
                key={`${row.kind}:${row.name}`}
                style={[styles.watchRow, { backgroundColor: rowBg }]}
              >
                <Text style={[styles.watchLabel, { color: labelColor }]}>
                  {row.name[0].toUpperCase() + row.name.slice(1)}
                </Text>
                <Bar probability={row.probability} color={barColor} />
                <Text style={[styles.pct, { color: conflict ? colors.danger : colors.text }]}>
                  {conflict ? "× " : ""}
                  {Math.round(row.probability * 100)}%
                </Text>
              </View>
            );
          })}
        </View>
      </ScrollView>

      {/* ── Sticky CTA ── */}
      <View style={styles.cta}>
        <PrimaryButton title="🗣️ Ask staff about this dish" onPress={() => setAskOpen(true)} />
      </View>

      {askOpen ? (
        <AskStaffSheet
          item={item}
          menuLanguage={props.menuLanguage}
          onClose={() => setAskOpen(false)}
          onEditQuestions={props.onOpenQuestions}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  photoBox: {
    height: 280,
    borderBottomWidth: 1,
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    overflow: "hidden",
  },
  photoTopRow: {
    position: "absolute",
    top: 56,
    left: spacing.l,
    right: spacing.l,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  pagerPill: {
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.s,
    borderRadius: radius.pill,
  },
  addPhotoBtn: {
    position: "absolute",
    bottom: spacing.l,
    right: spacing.l,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.s,
    borderRadius: radius.pill,
  },
  nameRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginTop: spacing.xl,
  },
  name: { fontSize: 28, fontWeight: "800", flexShrink: 1 },
  price: { fontSize: 22, fontWeight: "700" },
  description: { fontSize: 16, lineHeight: 23, marginTop: spacing.m },
  banner: {
    borderRadius: radius.m,
    padding: spacing.l,
    marginTop: spacing.l,
  },
  levelRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    marginTop: spacing.xl,
  },
  levelLabel: { width: 84, fontSize: 15 },
  watchHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginTop: spacing.xxl,
    marginBottom: spacing.s,
  },
  sectionTitle: { fontSize: 18, fontWeight: "700" },
  watchRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    paddingVertical: spacing.m,
    paddingHorizontal: spacing.s,
    borderRadius: radius.m,
    marginTop: spacing.xs,
  },
  watchLabel: { width: 84, fontSize: 15, fontWeight: "600" },
  pct: { width: 52, textAlign: "right", fontWeight: "600" },
  cta: {
    position: "absolute",
    left: spacing.xl,
    right: spacing.xl,
    bottom: spacing.xl + 8,
  },
});
