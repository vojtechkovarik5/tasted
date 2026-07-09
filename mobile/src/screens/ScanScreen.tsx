// Scan tab (design 1a/1h): photograph a menu (several pages allowed) and
// send it off.
//
// Flow:
//   snap pages with the live camera (or pick them from the phone gallery)
//   -> postMenu(uris) -> onScanned(menu)
//   MenuScreen then polls GET /menus/{id} while items resolve.
//
// Captured pages stack up left of the shutter; tapping the stack opens the
// scan gallery (design 1g) — a bottom sheet to review & remove pages before
// uploading. With no pages yet, that slot is a dashed "+" tile that opens
// the phone gallery directly and "Scan" is disabled.
// History lives on the Menus tab — deliberately not duplicated here.

import { CameraView, useCameraPermissions } from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import { useRef, useState } from "react";
import {
  FlatList,
  Image,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { Menu, postMenu } from "../api";
import { CircleBtn } from "../components";
import { radius, spacing, useTheme } from "../theme";

const THUMB = { width: 44, height: 56 }; // stack slot tile, left of the shutter

// The gallery grid ends with an "add more" tile (same cell, dashed).
const ADD_TILE = "__add__";

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

/** The captured pages as a little stack with a count badge (opens 1g). */
function PageStack(props: { pages: string[]; onPress: () => void }) {
  const { colors } = useTheme();
  const top = props.pages[props.pages.length - 1];
  return (
    <Pressable onPress={props.onPress} hitSlop={8} style={[THUMB, { alignSelf: "flex-start" }]}>
      {props.pages.length > 1 ? (
        <View
          style={[
            THUMB,
            styles.stackBehind,
            { backgroundColor: colors.surfaceAlt, borderColor: colors.border },
          ]}
        />
      ) : null}
      <Image source={{ uri: top }} style={[THUMB, styles.tile, { borderColor: colors.border }]} />
      <View style={[styles.countBadge, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={{ color: colors.text, fontSize: 11, fontWeight: "700" }}>
          {props.pages.length}
        </Text>
      </View>
    </Pressable>
  );
}

/** Scan gallery (design 1g): review & remove pages before uploading. */
function ScanGallerySheet(props: {
  pages: string[];
  onRemove: (index: number) => void;
  onAdd: () => void;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Modal transparent animationType="slide" visible onRequestClose={props.onClose}>
      <View style={[styles.backdrop, { backgroundColor: colors.overlay }]}>
        <Pressable style={{ flex: 1 }} onPress={props.onClose} />
        <View style={[styles.sheet, { backgroundColor: colors.background }]}>
          <View style={[styles.grabber, { backgroundColor: colors.border }]} />
          <View style={styles.sheetHeader}>
            <Text style={[styles.sheetTitle, { color: colors.text }]}>
              Scan gallery · {props.pages.length}
            </Text>
            <CircleBtn label="×" size={36} onPress={props.onClose} />
          </View>
          <FlatList
            data={[...props.pages, ADD_TILE]}
            numColumns={2}
            keyExtractor={(item, i) => (item === ADD_TILE ? ADD_TILE : `${item}-${i}`)}
            columnWrapperStyle={{ gap: spacing.l }}
            // Horizontal slack so the corner badges overhang without being
            // clipped at the list frame; the negative margin keeps the grid
            // aligned with the header.
            style={{ marginHorizontal: -spacing.s }}
            contentContainerStyle={{
              gap: spacing.l,
              paddingTop: spacing.s,
              paddingBottom: spacing.xl,
              paddingHorizontal: spacing.s,
            }}
            renderItem={({ item, index }) =>
              item === ADD_TILE ? (
                <Pressable
                  onPress={props.onAdd}
                  style={[
                    styles.cell,
                    styles.addCell,
                    // Same look as the empty stack slot next to the shutter.
                    { borderColor: colors.textMuted, backgroundColor: colors.surfaceAlt },
                  ]}
                >
                  <View>
                    <Text style={{ color: colors.text, fontSize: 36 }}>+</Text>
                  </View>
                </Pressable>
              ) : (
                <View style={styles.cell}>
                  <Image
                    source={{ uri: item }}
                    style={[styles.cellPhoto, { backgroundColor: colors.surfaceAlt, borderColor: colors.border }]}
                  />
                  <Text style={[styles.cellLabel, { color: colors.textMuted }]}>
                    page {index + 1}
                  </Text>
                  <Pressable
                    onPress={() => props.onRemove(index)}
                    hitSlop={8}
                    style={[styles.removeBadge, { backgroundColor: colors.danger }]}
                  >
                    <Text style={{ color: colors.onPrimary, fontSize: 13, fontWeight: "700" }}>×</Text>
                  </Pressable>
                </View>
              )
            }
          />
        </View>
      </View>
    </Modal>
  );
}

export default function ScanScreen(props: { onScanned: (menu: Menu) => void }) {
  const { colors } = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [pages, setPages] = useState<string[]>([]); // local photo uris, in menu order
  const [galleryOpen, setGalleryOpen] = useState(false); // the 1g sheet
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

  function removePage(i: number) {
    const next = pages.filter((_, j) => j !== i);
    setPages(next);
    if (next.length === 0) setGalleryOpen(false); // nothing left to review
  }

  async function scan() {
    setScanning(true);
    setError(null);
    try {
      const menu = await postMenu(pages);
      setPages([]);
      props.onScanned(menu);
    } catch {
      setError("Scan failed — check your connection and try again.");
    } finally {
      setScanning(false);
    }
  }

  const canScan = pages.length > 0 && !scanning;

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
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

      {error ? (
        <Text style={{ color: colors.danger, textAlign: "center", marginTop: spacing.s }}>
          {error}
        </Text>
      ) : null}

      {/* Page stack (or "+" when empty) | shutter | Scan */}
      <View style={styles.controls}>
        <View style={styles.controlSlot}>
          {pages.length > 0 ? (
            <PageStack pages={pages} onPress={() => setGalleryOpen(true)} />
          ) : (
            <Pressable
              onPress={pickFromGallery}
              style={[THUMB, styles.tile, styles.addTile, { borderColor: colors.textMuted }]}
            >
              <Text style={{ color: colors.textMuted, fontSize: 20 }}>+</Text>
            </Pressable>
          )}
        </View>
        <Pressable onPress={snapPage} style={[styles.shutterOuter, { borderColor: colors.text }]}>
          <View style={[styles.shutterInner, { backgroundColor: colors.text }]} />
        </Pressable>
        <View style={[styles.controlSlot, { alignItems: "flex-end" }]}>
          <Pressable
            onPress={canScan ? scan : undefined}
            style={[
              styles.scanPill,
              { backgroundColor: canScan ? colors.chipActiveBg : colors.surfaceAlt },
            ]}
          >
            <Text
              style={{
                color: canScan ? colors.chipActiveText : colors.textMuted,
                fontSize: 15,
                fontWeight: "700",
              }}
            >
              {scanning ? "Scanning…" : "Scan"}
            </Text>
          </Pressable>
        </View>
      </View>

      {galleryOpen ? (
        <ScanGallerySheet
          pages={pages}
          onRemove={removePage}
          onAdd={pickFromGallery}
          onClose={() => setGalleryOpen(false)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: spacing.xl, paddingTop: 54, paddingBottom: 96 },
  viewfinder: {
    flex: 1,
    borderRadius: radius.l,
    borderWidth: 1,
    overflow: "hidden",
  },
  placeholder: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
  },
  controls: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.l,
    minHeight: THUMB.height + 10, // room for the stack's count badge
  },
  controlSlot: { flex: 1, justifyContent: "center" },
  tile: { borderRadius: radius.s, borderWidth: 1 },
  addTile: {
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "transparent",
  },
  // The sheet of paper peeking out behind the top thumbnail.
  stackBehind: {
    position: "absolute",
    top: -4,
    left: 6,
    borderRadius: radius.s,
    borderWidth: 1,
  },
  stackLabel: {
    position: "absolute",
    bottom: 4,
    left: 4,
    fontSize: 10,
    fontWeight: "700",
    paddingHorizontal: 4,
    borderRadius: 4,
    overflow: "hidden",
  },
  countBadge: {
    position: "absolute",
    top: -8,
    right: -8,
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  shutterOuter: {
    width: 64,
    height: 64,
    borderRadius: 32,
    borderWidth: 3,
    alignItems: "center",
    justifyContent: "center",
  },
  shutterInner: { width: 50, height: 50, borderRadius: 25 },
  scanPill: {
    paddingHorizontal: spacing.xl + 4,
    paddingVertical: spacing.m,
    borderRadius: radius.pill,
  },
  // ── Scan gallery sheet (1g) ──
  backdrop: { flex: 1, justifyContent: "flex-end" },
  sheet: {
    height: "74%",
    borderTopLeftRadius: radius.l,
    borderTopRightRadius: radius.l,
    padding: spacing.xl,
    paddingTop: spacing.m,
  },
  grabber: {
    alignSelf: "center",
    width: 44,
    height: 5,
    borderRadius: radius.pill,
    marginBottom: spacing.m,
  },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.m,
  },
  sheetTitle: { fontSize: 22, fontWeight: "800" },
  // maxWidth keeps a lone cell in the last grid row at column width.
  cell: { flex: 1, maxWidth: "48.5%" },
  cellPhoto: {
    width: "100%",
    aspectRatio: 0.78,
    borderRadius: radius.m,
    borderWidth: 1,
  },
  cellLabel: {
    position: "absolute",
    bottom: spacing.m,
    alignSelf: "center",
    fontSize: 12,
  },
  addCell: {
    aspectRatio: 0.78,
    borderRadius: radius.m,
    borderWidth: 1,
    borderStyle: "dashed",
    alignItems: "center",
    justifyContent: "center",
  },
  addCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  removeBadge: {
    position: "absolute",
    top: -8,
    right: -8,
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
});
