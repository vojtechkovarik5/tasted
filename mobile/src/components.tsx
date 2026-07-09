// Small reusable UI pieces. All colors come from useTheme() — no hex here.

import { useEffect, useRef } from "react";
import { Animated, Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";

import { radius, spacing, useTheme } from "./theme";

/** Section heading with an optional right-aligned caption. */
export function SectionHeader(props: { title: string; caption?: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.sectionRow}>
      <Text style={[styles.sectionTitle, { color: colors.text }]}>{props.title}</Text>
      {props.caption ? (
        <Text style={{ color: colors.textMuted, fontSize: 12 }}>{props.caption}</Text>
      ) : null}
    </View>
  );
}

/** Toggleable pill chip (Profile: watch-out list, macros). */
export function Chip(props: {
  label: string;
  active?: boolean;
  dashed?: boolean;
  onPress?: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={props.onPress}
      style={{
        paddingHorizontal: spacing.l,
        paddingVertical: spacing.s + 2,
        borderRadius: radius.pill,
        backgroundColor: props.active ? colors.chipActiveBg : colors.chipBg,
        borderWidth: 1,
        borderColor: props.active ? colors.chipActiveBg : colors.border,
        borderStyle: props.dashed ? "dashed" : "solid",
      }}
    >
      <Text
        style={{
          color: props.active ? colors.chipActiveText : colors.text,
          fontWeight: props.active ? "600" : "400",
        }}
      >
        {props.label}
        {props.active ? " ✓" : ""}
      </Text>
    </Pressable>
  );
}

/** Small circular button — back arrow, vote arrows, steppers. */
export function CircleBtn(props: {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
  size?: number;
}) {
  const { colors } = useTheme();
  const size = props.size ?? 36;
  return (
    <Pressable
      onPress={props.onPress}
      disabled={props.disabled}
      hitSlop={8}
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.surface,
        alignItems: "center",
        justifyContent: "center",
        opacity: props.disabled ? 0.4 : 1,
      }}
    >
      <Text style={{ color: colors.text, fontSize: size * 0.45 }}>{props.label}</Text>
    </Pressable>
  );
}

/** Horizontal probability bar (0..1). */
export function Bar(props: { probability: number; color?: string }) {
  const { colors } = useTheme();
  return (
    <View
      style={{
        flex: 1,
        height: 6,
        borderRadius: 3,
        backgroundColor: colors.barTrack,
        overflow: "hidden",
      }}
    >
      <View
        style={{
          width: `${Math.round(props.probability * 100)}%`,
          height: "100%",
          borderRadius: 3,
          backgroundColor: props.color ?? colors.barNeutral,
        }}
      />
    </View>
  );
}

/** Full-width terracotta CTA ("Ask staff about this dish"). */
export function PrimaryButton(props: { title: string; onPress?: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={props.onPress}
      style={{
        backgroundColor: colors.primary,
        borderRadius: radius.l,
        paddingVertical: spacing.l,
        alignItems: "center",
      }}
    >
      <Text style={{ color: colors.onPrimary, fontSize: 16, fontWeight: "700" }}>
        {props.title}
      </Text>
    </Pressable>
  );
}

/** Pulsing grey block — building block for loading skeletons. */
export function Skeleton(props: { style?: ViewStyle }) {
  const { colors } = useTheme();
  const opacity = useRef(new Animated.Value(0.35)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.9, duration: 600, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.35, duration: 600, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);
  return (
    <Animated.View
      style={[
        { backgroundColor: colors.barTrack, borderRadius: radius.s, opacity },
        props.style,
      ]}
    />
  );
}

/**
 * Partially-fillable icon meter — e.g. 3.17 of 5 chilis.
 * Two stacked rows of the same icons: a faded base row, and a full-color row
 * clipped to `level / max` of the width, so fractional levels show as a
 * partially colored icon.
 */
export function IconMeter(props: {
  level: number; // 0..max, fractional
  max?: number;
  icon: string; // "🌶️" — or any single glyph
  iconSize?: number;
  fadedOpacity?: number;
  color?: string; // for text glyphs like "€"
}) {
  const { colors } = useTheme();
  const max = props.max ?? 5;
  const size = props.iconSize ?? 20;
  const slot = size + 2;
  const width = slot * max;
  const pct = Math.max(0, Math.min(1, props.level / max));

  const row = (opacity: number) => (
    <View style={{ flexDirection: "row", width }}>
      {Array.from({ length: max }, (_, i) => (
        <Text
          key={i}
          style={{
            width: slot,
            fontSize: size * 0.85,
            textAlign: "center",
            opacity,
            color: props.color ?? colors.text,
            fontWeight: "700",
          }}
        >
          {props.icon}
        </Text>
      ))}
    </View>
  );

  return (
    <View style={{ width, height: size + 4, justifyContent: "center" }}>
      {row(props.fadedOpacity ?? 0.22)}
      {/* color layer, clipped at the fractional fill width */}
      <View
        style={{
          position: "absolute",
          left: 0,
          width: pct * width,
          overflow: "hidden",
        }}
      >
        {row(1)}
      </View>
    </View>
  );
}

/** Card container used across screens. */
export function Card(props: { children: React.ReactNode; style?: ViewStyle }) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: colors.surface,
          borderRadius: radius.m,
          borderWidth: 1,
          borderColor: colors.border,
          padding: spacing.l,
        },
        props.style,
      ]}
    >
      {props.children}
    </View>
  );
}

const styles = StyleSheet.create({
  sectionRow: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
    marginTop: spacing.xxl,
    marginBottom: spacing.m,
  },
  sectionTitle: { fontSize: 18, fontWeight: "700" },
});
