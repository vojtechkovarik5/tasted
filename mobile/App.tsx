// App root: theme + auth providers and a deliberately tiny "navigator".
//
// Tabs:    Scan (new scan) | Menus (history) | Profile
// Stack:   MenuScreen (one menu's items) and DishDetailScreen push over the
//          tabs via plain React state — no navigation library yet. If the
//          app grows, the standard upgrade is expo-router.
//
// Dark mode later: pass darkColors below (e.g. based on useColorScheme()).

import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { Menu, MenuItem } from "./src/api";
import { AuthProvider } from "./src/auth";
import DishDetailScreen from "./src/screens/DishDetailScreen";
import MenuScreen from "./src/screens/MenuScreen";
import MenusScreen from "./src/screens/MenusScreen";
import ProfileScreen from "./src/screens/ProfileScreen";
import ScanScreen from "./src/screens/ScanScreen";
import { lightColors, ThemeProvider, useTheme } from "./src/theme";

type Tab = "scan" | "menus" | "profile";

function TabBar(props: { tab: Tab; onChange: (t: Tab) => void }) {
  const { colors } = useTheme();
  const tabs: { key: Tab; label: string }[] = [
    { key: "scan", label: "📷 Scan" },
    { key: "menus", label: "🧾 Menus" },
    { key: "profile", label: "👤 Profile" },
  ];
  return (
    <View
      style={[styles.tabbar, { backgroundColor: colors.surface, borderTopColor: colors.border }]}
    >
      {tabs.map((t) => (
        <Pressable key={t.key} style={styles.tab} onPress={() => props.onChange(t.key)}>
          <Text
            style={{
              color: props.tab === t.key ? colors.text : colors.textMuted,
              fontWeight: props.tab === t.key ? "700" : "400",
            }}
          >
            {t.label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

function Root() {
  const [tab, setTab] = useState<Tab>("scan");
  // Mini stack: an open menu, and optionally an open dish on top of it.
  const [openMenu, setOpenMenu] = useState<Menu | null>(null);
  const [openItem, setOpenItem] = useState<MenuItem | null>(null);
  // Logged-out users have no server-side history — their latest scan is the
  // "current menu", kept here so the Menus tab can still show it.
  const [lastScanned, setLastScanned] = useState<Menu | null>(null);

  if (openItem) {
    return <DishDetailScreen item={openItem} onBack={() => setOpenItem(null)} />;
  }

  if (openMenu) {
    return (
      <MenuScreen menu={openMenu} onOpenItem={setOpenItem} onBack={() => setOpenMenu(null)} />
    );
  }

  return (
    <View style={{ flex: 1 }}>
      {tab === "scan" ? (
        // Fresh scan: open the menu and land on the Menus tab underneath,
        // so "back" from the result goes to history, not the scan button.
        <ScanScreen
          onScanned={(menu) => {
            setLastScanned(menu);
            setOpenMenu(menu);
            setTab("menus");
          }}
        />
      ) : tab === "menus" ? (
        <MenusScreen localMenu={lastScanned} onOpenMenu={setOpenMenu} />
      ) : (
        <ProfileScreen />
      )}
      <TabBar tab={tab} onChange={setTab} />
    </View>
  );
}

export default function App() {
  return (
    <ThemeProvider value={{ colors: lightColors, mode: "light" }}>
      {/* AuthProvider is a Clerk-shaped stub — swap for ClerkProvider later (src/auth.tsx) */}
      <AuthProvider>
        <StatusBar style="dark" />
        <Root />
      </AuthProvider>
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  tabbar: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: "row",
    borderTopWidth: 1,
    paddingBottom: 28, // home-indicator area
    paddingTop: 10,
  },
  tab: { flex: 1, alignItems: "center", paddingVertical: 6 },
});
