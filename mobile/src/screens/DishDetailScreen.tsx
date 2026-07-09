// Canonical dish page (design 3b) — ONE page per dish FAMILY (thousands of
// menu variants collapse into facets; combos are one family too). Everything
// here is general knowledge about the dish, stored in the DB translated to
// the user's language (English fallback): photos, name + pronunciation +
// aliases, origin/category line, description, common ingredients %, common
// allergens %, diet fit %, average macros per 100 g, diner voting
// (spice/price), common variants (the menu item's matched facet highlighted)
// and similar dishes. The MENU ITEM (design 3a) stays the source of truth
// for what's on your plate — hence the disclaimer and "Back to menu item".
//
// Voting: one vote per user per meter. The displayed level does NOT move on
// tap — votes are folded in by periodic recalculation server-side — the
// pressed arrow just fills in ("you voted") and pressing the other arrow
// changes the vote. GET /dishes/{id}/votes restores the marks on open.

import * as ImagePicker from "expo-image-picker";
import { useEffect, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { getMyVotes, MenuItem, MyVotes, resolveUrl, sendVote, uploadDishPhoto } from "../api";
import { useAuth } from "../auth";
import { CircleBtn, IconMeter, PrimaryButton } from "../components";
import { usePrefs, watchedAllergens, watchedDietary, watchedIngredients } from "../prefs";
import { radius, spacing, useTheme } from "../theme";

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** Label + vote arrows around a fractional icon meter. The arrow matching
 *  the user's standing vote renders filled. */
function LevelRow(props: {
  label: string;
  level: number;
  icon: string;
  color?: string;
  myVote: "up" | "down" | null;
  onVote: (dir: "up" | "down") => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.levelRow, { backgroundColor: colors.surface }]}>
      <Text style={[styles.levelLabel, { color: colors.text }]}>{props.label}</Text>
      <CircleBtn
        label="←"
        active={props.myVote === "down"}
        onPress={() => props.onVote("down")}
      />
      <View style={{ flex: 1, alignItems: "center" }}>
        <IconMeter level={props.level} icon={props.icon} color={props.color} />
      </View>
      <CircleBtn label="→" active={props.myVote === "up"} onPress={() => props.onVote("up")} />
    </View>
  );
}

/** A wrap of "name pct%" chips (ingredients / allergens / diet fit). */
function PercentChips(props: {
  rows: { name: string; probability: number; label: string | null }[];
  tracked: Set<string>;
  tone: "neutral" | "danger" | "diet";
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.chipWrap, { backgroundColor: colors.surface }]}>
      {props.rows.map((row) => {
        const pct = Math.round(row.probability * 100);
        const isTracked = props.tracked.has(row.name);
        let fg = colors.text;
        let bg = colors.surfaceAlt;
        if (props.tone === "danger") {
          fg = colors.danger;
          bg = isTracked || row.probability >= 0.5 ? colors.dangerBg : colors.surfaceAlt;
        } else if (props.tone === "diet") {
          if (row.probability >= 0.5 && (row.name === "meat" || row.name === "fried")) {
            // High share of meat/fried isn't a "fit" — keep it neutral-warn.
            fg = colors.text;
            bg = colors.surfaceAlt;
          } else if (row.probability >= 0.3) {
            fg = colors.success;
            bg = colors.successBg;
          }
        }
        if (isTracked && props.tone !== "danger") {
          fg = colors.warnText;
          bg = colors.warnBg;
        }
        return (
          <View key={row.name} style={[styles.pctChip, { backgroundColor: bg }]}>
            <Text style={{ color: fg, fontSize: 13, fontWeight: "600" }}>
              {cap(row.label ?? row.name.replace(/-/g, " "))}{" "}
              <Text style={{ opacity: 0.7, fontWeight: "500" }}>{pct}%</Text>
            </Text>
          </View>
        );
      })}
    </View>
  );
}

function SectionTitle(props: { children: string; right?: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.sectionHeader}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>{props.children}</Text>
      {props.right ? (
        <Text style={{ color: colors.textMuted, fontSize: 12 }}>{props.right}</Text>
      ) : null}
    </View>
  );
}

export default function DishDetailScreen(props: {
  item: MenuItem;
  menuLanguage?: string | null;
  onBack: () => void;
  onOpenQuestions?: () => void;
}) {
  const { colors } = useTheme();
  const prefs = usePrefs();
  const { isSignedIn } = useAuth();
  const { item } = props;
  const dish = item.dish!; // screen is only opened for matched items
  const info = dish.info;
  const photo = dish.photos[0];

  // Photo upload: goes to POST /dishes/{id}/photo, stored immediately but
  // hidden from responses until moderation flips it to active — so the UI
  // acknowledges the submission instead of showing the new photo.
  const [photoNote, setPhotoNote] = useState<string | null>(null);
  async function addPhoto() {
    if (!isSignedIn) {
      setPhotoNote("sign in on the Profile tab to add photos");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.8,
    });
    if (result.canceled || !result.assets[0]?.uri) return;
    setPhotoNote("uploading…");
    try {
      await uploadDishPhoto(dish.id, result.assets[0].uri);
      setPhotoNote("✓ photo submitted — it appears once reviewed");
    } catch {
      setPhotoNote("upload failed — please try again");
    }
  }

  // My standing votes — drives the filled-arrow "you voted" state. Signed-out
  // users get no marks (the fetch 401s silently) and their votes are dropped
  // server-side the same way.
  const [myVotes, setMyVotes] = useState<MyVotes>({ spice: null, price: null });
  useEffect(() => {
    getMyVotes(dish.id).then(setMyVotes).catch(() => {});
  }, [dish.id]);

  function voteLevel(target: "spice" | "price", dir: "up" | "down") {
    if (myVotes[target] === dir) return; // already voted this way — no-op
    setMyVotes((v) => ({ ...v, [target]: dir })); // mark the arrow, not the meter
    sendVote(dish.id, target, dir).catch(() => {}); // fire-and-forget
  }

  // Origin line: "🇹🇭 Thailand · stir-fried rice-noodle dish · national dish"
  const originLine = [info.origin, info.category, info.national_dish ? "national dish" : null]
    .filter(Boolean)
    .join(" · ");

  const ingredients = [...info.ingredients].sort((a, b) => b.probability - a.probability);
  const allergens = [...info.allergens].sort((a, b) => b.probability - a.probability);

  return (
    <View style={{ flex: 1, backgroundColor: colors.background }}>
      <ScrollView contentContainerStyle={{ paddingBottom: 170 }}>
        {/* ── Photo header: real image when available, drop zone otherwise ── */}
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
              <Text style={{ color: colors.textMuted }}>
                {dish.canonical_name.toLowerCase()} photo
              </Text>
              <Pressable onPress={addPhoto}>
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
            onPress={addPhoto}
            style={[styles.addPhotoBtn, { backgroundColor: colors.surface }]}
          >
            <Text style={{ color: colors.text }}>+ Add photo</Text>
          </Pressable>
          {photoNote ? (
            <View style={[styles.photoNote, { backgroundColor: colors.chipActiveBg }]}>
              <Text style={{ color: colors.chipActiveText, fontSize: 12 }}>{photoNote}</Text>
            </View>
          ) : null}
        </View>

        <View style={{ paddingHorizontal: spacing.xl }}>
          {/* ── Name + pronunciation ── */}
          <View style={styles.nameRow}>
            <Text style={[styles.name, { color: colors.text }]}>{dish.canonical_name}</Text>
            {info.pronunciation ? (
              <View style={[styles.pronPill, { backgroundColor: colors.surfaceAlt }]}>
                <Text style={{ color: colors.text, fontSize: 13 }}>
                  [{info.pronunciation}]
                </Text>
              </View>
            ) : null}
          </View>
          {info.native_name || info.aliases.length > 0 ? (
            <Text style={{ color: colors.textMuted, marginTop: 2 }}>
              {[info.native_name, ...info.aliases].filter(Boolean).join(" · ")}
            </Text>
          ) : null}
          {originLine ? (
            <Text style={{ color: colors.text, marginTop: 2, fontSize: 13 }}>{originLine}</Text>
          ) : null}

          {/* ── Description (stored translated; English fallback) ── */}
          <Text style={[styles.description, { color: colors.text }]}>{info.description}</Text>

          {/* ── Common ingredients ── */}
          {ingredients.length > 0 ? (
            <>
              <SectionTitle>Common ingredients</SectionTitle>
              <PercentChips
                rows={ingredients}
                tracked={watchedIngredients(prefs)}
                tone="neutral"
              />
            </>
          ) : null}

          {/* ── Common allergens ── */}
          {allergens.length > 0 ? (
            <>
              <SectionTitle>Common allergens</SectionTitle>
              <PercentChips
                rows={allergens}
                tracked={watchedAllergens(prefs)}
                tone="danger"
              />
            </>
          ) : null}

          {/* ── Diet fit (share of versions worldwide) ── */}
          {info.dietary.length > 0 ? (
            <>
              <SectionTitle>Diet fit</SectionTitle>
              <PercentChips
                rows={info.dietary}
                tracked={watchedDietary(prefs)}
                tone="diet"
              />
            </>
          ) : null}

          {/* ── Average macros per 100 g ── */}
          {info.macros ? (
            <>
              <SectionTitle>Average macros · per 100 g</SectionTitle>
              <View style={[styles.macrosRow, { backgroundColor: colors.surface }]}>
                {(
                  [
                    ["kcal", info.macros.kcal, "", "~"],
                    ["protein", info.macros.protein_g, "g", ""],
                    ["fat", info.macros.fat_g, "g", ""],
                    ["carbs", info.macros.carbs_g, "g", ""],
                  ] as const
                ).map(([label, value, unit, prefix]) =>
                  value != null ? (
                    <View key={label} style={{ alignItems: "center" }}>
                      <Text style={{ color: colors.text, fontWeight: "700", fontSize: 16 }}>
                        {prefix}
                        {Math.round(value)}
                        {unit}
                      </Text>
                      <Text style={{ color: colors.textMuted, fontSize: 11 }}>
                        {label.toUpperCase()}
                      </Text>
                    </View>
                  ) : null,
                )}
              </View>
            </>
          ) : null}

          {/* ── How diners rate it (votable) ── */}
          <SectionTitle right="vote ←→">How diners rate it</SectionTitle>
          <LevelRow
            label="Spice"
            level={info.spice_level}
            icon="🌶️"
            myVote={myVotes.spice}
            onVote={(d) => voteLevel("spice", d)}
          />
          <LevelRow
            label="Price level"
            level={info.price_level ?? 0}
            // Always "$" — currency codes without a symbol (QAR) would
            // render as stacked letters in the meter.
            icon="$"
            color={colors.text}
            myVote={myVotes.price}
            onVote={(d) => voteLevel("price", d)}
          />

          {/* ── Common variants (facets, matched one highlighted) ── */}
          {dish.variants.length > 0 ? (
            <>
              <SectionTitle>Common variants</SectionTitle>
              <View style={styles.variantWrap}>
                {dish.variants.map((v) => {
                  const matched = v.key === item.matched_variant_key;
                  return (
                    <View
                      key={v.key}
                      style={[
                        styles.variantChip,
                        {
                          borderColor: matched ? colors.text : colors.border,
                          borderWidth: matched ? 2 : 1,
                          backgroundColor: colors.surface,
                        },
                      ]}
                    >
                      <Text
                        style={{
                          color: colors.text,
                          fontWeight: matched ? "700" : "500",
                          fontSize: 13,
                        }}
                      >
                        {v.name}
                      </Text>
                    </View>
                  );
                })}
              </View>
            </>
          ) : null}

          {/* ── Similar dishes ── */}
          {info.similar.length > 0 ? (
            <>
              <SectionTitle>Similar dishes</SectionTitle>
              <View style={styles.variantWrap}>
                {info.similar.map((name) => (
                  <View
                    key={name}
                    style={[styles.variantChip, { backgroundColor: "#ffffff" }]}
                  >
                    <Text style={{ color: colors.text, fontSize: 13 }}>{name}</Text>
                  </View>
                ))}
              </View>
            </>
          ) : null}

        </View>
      </ScrollView>
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
  photoNote: {
    position: "absolute",
    bottom: spacing.l,
    left: spacing.l,
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.s,
    borderRadius: radius.pill,
  },
  nameRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.m,
    marginTop: spacing.xl,
  },
  name: { fontSize: 28, fontWeight: "800", flexShrink: 1 },
  pronPill: {
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  description: { fontSize: 16, lineHeight: 23, marginTop: spacing.m },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "baseline",
    marginTop: spacing.xxl,
    marginBottom: spacing.s,
  },
  sectionTitle: { fontSize: 18, fontWeight: "700" },
  chipWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.s,
    borderRadius: radius.m,
    padding: spacing.m,
  },
  pctChip: {
    paddingHorizontal: spacing.m,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  macrosRow: {
    flexDirection: "row",
    justifyContent: "space-around",
    borderRadius: radius.m,
    padding: spacing.l,
  },
  levelRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.m,
    padding: spacing.m,
    borderRadius: radius.m,
    marginTop: spacing.s,
  },
  levelLabel: { width: 84, fontSize: 15 },
  variantWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.s },
  variantChip: {
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.s,
    borderRadius: radius.pill,
  },
  disclaimer: {
    borderRadius: radius.m,
    padding: spacing.l,
    marginTop: spacing.xxl,
  },
  cta: {
    position: "absolute",
    left: spacing.xl,
    right: spacing.xl,
    // Clear of the tab bar App.tsx overlays on every screen — at the old
    // `spacing.xl + 8` the button rendered UNDERNEATH it, untappable.
    bottom: 96,
  },
});
