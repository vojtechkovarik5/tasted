// Scan tab: photograph a menu (several pages allowed) and send it off.
//
// Flow:
//   snap pages with the live camera (or pick them from the gallery)
//   -> optional title -> postMenu(uris, title) -> onScanned(menu)
//   MenuScreen then polls GET /menus/{id} while items resolve.
//
// History lives on the Menus tab — deliberately not duplicated here.

import { CameraView, useCameraPermissions } from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import { useRef, useState } from "react";
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { Menu, postMenu } from "../api";
import { PrimaryButton } from "../components";
import { radius, spacing, useTheme } from "../theme";

/** One corner bracket of the viewfinder frame. */
function Corner(props: { position: "tl" | "tr" | "bl" | "br"; color: string }) {
  const edge = { borderColor: props.color, position: "absolute" as const, width: 26, height: 26 };
  const offsets = {
    tl: { top: 14, left: 14, borderTopWidth: 3, borderLeftWidth: 3, borderTopLeftRadius: 8 },
    tr: { top: 14, right: 14, borderTopWidth: 3, borderRightWidth: 3, borderTopRightRadius: 8 },
    bl: { bottom: 14, left: 14, borderBottomWidth: 3, borderLeftWidth: 3, borderBottomLeftRadius: 8 },
    br: { bottom: 14, right: 14, borderBottomWidth: 3, borderRightWidth: 3, borderBottomRightRadius: 8 },
  };
  return <View style={[edge, offsets[props.position]]} />;
}

export default function ScanScreen(props: { onScanned: (menu: Menu) => void }) {
  const { colors } = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [title, setTitle] = useState("");
  const [pages, setPages] = useState<string[]>([]); // local photo uris, in menu order
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function snapPage() {
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) return;
    }
    const photo = await cameraRef.current?.takePictureAsync();
    if (photo?.uri) setPages((p) => [...p, photo.uri]);
  }

  async function pickFromGallery() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsMultipleSelection: true,
      quality: 0.8,
    });
    if (!result.canceled) {
      setPages((p) => [...p, ...result.assets.map((a) => a.uri)]);
    }
  }

  async function scan() {
    setScanning(true);
    setError(null);
    try {
      const menu = await postMenu(pages, title.trim() || undefined);
      setPages([]);
      setTitle("");
      props.onScanned(menu);
    } catch {
      setError("Scan failed — check your connection and try again.");
    } finally {
      setScanning(false);
    }
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <Text style={[styles.title, { color: colors.text }]}>Tasted</Text>
      <Text style={{ color: colors.textMuted, marginTop: 4 }}>
        Snap every page of the menu, then scan once
      </Text>

      <TextInput
        value={title}
        onChangeText={setTitle}
        placeholder="Title (e.g. restaurant name) — optional"
        placeholderTextColor={colors.textMuted}
        style={[
          styles.titleInput,
          { backgroundColor: colors.surface, borderColor: colors.border, color: colors.text },
        ]}
      />

      {/* Viewfinder — live camera once permission is granted, placeholder before */}
      <View style={[styles.viewfinder, { backgroundColor: colors.surfaceAlt, borderColor: colors.border }]}>
        {permission?.granted ? (
          <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="back" />
        ) : (
          <Pressable style={styles.placeholder} onPress={requestPermission}>
            <Text style={{ color: colors.textMuted }}>🖼️</Text>
            <Text style={{ color: colors.textMuted, marginTop: spacing.s }}>
              menu photo (live camera)
            </Text>
            <Text
              onPress={pickFromGallery}
              style={{ color: colors.textMuted, marginTop: 2, textDecorationLine: "underline" }}
            >
              or browse files
            </Text>
          </Pressable>
        )}
        <Corner position="tl" color={colors.surface} />
        <Corner position="tr" color={colors.surface} />
        <Corner position="bl" color={colors.surface} />
        <Corner position="br" color={colors.surface} />
      </View>

      {/* Captured pages: thumbnails + a dashed "add" tile */}
      <View style={styles.pagesRow}>
        {pages.map((uri, i) => (
          <Pressable key={`${uri}-${i}`} onLongPress={() => setPages((p) => p.filter((_, j) => j !== i))}>
            <Image source={{ uri }} style={[styles.thumb, { borderColor: colors.border }]} />
            <Text style={[styles.thumbLabel, { color: colors.onPrimary, backgroundColor: colors.text }]}>
              p.{i + 1}
            </Text>
          </Pressable>
        ))}
        <Pressable
          onPress={pickFromGallery}
          style={[styles.thumb, styles.addTile, { borderColor: colors.textMuted }]}
        >
          <Text style={{ color: colors.textMuted, fontSize: 20 }}>+</Text>
        </Pressable>
        <Text style={{ color: colors.textMuted, fontSize: 12, marginLeft: "auto" }}>
          {pages.length === 0
            ? "no pages yet"
            : `${pages.length} page${pages.length > 1 ? "s" : ""} · hold to remove`}
        </Text>
      </View>

      {/* Gallery | shutter (History lives on the Menus tab) */}
      <View style={styles.controls}>
        <Text onPress={pickFromGallery} style={[styles.controlLabel, { color: colors.textMuted }]}>
          Gallery
        </Text>
        <Pressable
          onPress={snapPage}
          style={[styles.shutterOuter, { borderColor: colors.text }]}
        >
          <View style={[styles.shutterInner, { backgroundColor: colors.text }]} />
        </Pressable>
        <View style={styles.controlLabel} />
      </View>

      {error ? (
        <Text style={{ color: colors.danger, textAlign: "center", marginBottom: spacing.s }}>
          {error}
        </Text>
      ) : null}

      <PrimaryButton
        title={
          scanning
            ? "Scanning…"
            : pages.length === 0
              ? "Snap a page to start"
              : `Scan ${pages.length} page${pages.length > 1 ? "s" : ""} →`
        }
        onPress={pages.length === 0 || scanning ? undefined : scan}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: spacing.xl, paddingTop: 70, paddingBottom: 120 },
  title: { fontSize: 30, fontWeight: "800" },
  titleInput: {
    marginTop: spacing.l,
    borderWidth: 1,
    borderRadius: radius.m,
    paddingHorizontal: spacing.l,
    paddingVertical: spacing.m,
    fontSize: 15,
  },
  viewfinder: {
    flex: 1,
    marginTop: spacing.l,
    borderRadius: radius.l,
    borderWidth: 1,
    overflow: "hidden",
  },
  placeholder: { flex: 1, alignItems: "center", justifyContent: "center" },
  pagesRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.s,
    marginTop: spacing.m,
    minHeight: 56,
  },
  thumb: { width: 44, height: 56, borderRadius: radius.s, borderWidth: 1 },
  thumbLabel: {
    position: "absolute",
    bottom: 4,
    left: 4,
    fontSize: 10,
    fontWeight: "700",
    paddingHorizontal: 4,
    borderRadius: 4,
    overflow: "hidden",
  },
  addTile: {
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "transparent",
  },
  controls: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginVertical: spacing.m,
    paddingHorizontal: spacing.xl,
  },
  controlLabel: { width: 60, textAlign: "center", fontSize: 15 },
  shutterOuter: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: 3,
    alignItems: "center",
    justifyContent: "center",
  },
  shutterInner: { width: 50, height: 50, borderRadius: 25 },
});
