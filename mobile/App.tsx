// App root: theme + auth providers and a deliberately tiny "navigator".
//
// Tabs:    Scan (new scan) | Menus (history) | Profile
// Stack:   MenuScreen, DishDetailScreen and MyQuestionsScreen push over the
//          tabs via plain React state — no navigation library yet. If the
//          app grows, the standard upgrade is expo-router.
//
// The tab bar stays visible on every screen. The highlighted tab reflects
// where the user is, stacked screens included: My questions belongs to
// Profile, an open menu or dish to Menus. Tapping any tab pops the stack.
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
import MyQuestionsScreen from "./src/screens/MyQuestionsScreen";
import ProfileScreen from "./src/screens/ProfileScreen";
import ScanScreen from "./src/screens/ScanScreen";
import { lightColors, radius, ThemeProvider, useTheme } from "./src/theme";

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
      {tabs.map((t) => {
        const active = props.tab === t.key;
        return (
          <Pressable key={t.key} style={styles.tab} onPress={() => props.onChange(t.key)}>
            <View style={[styles.tabPill, active && { borderColor: colors.text }]}>
              <Text
                style={{
                  color: active ? colors.text : colors.textMuted,
                  fontWeight: active ? "700" : "400",
                }}
              >
                {t.label}
              </Text>
            </View>
          </Pressable>
        );
      })}
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
  // My questions (from Settings) pushes over the tabs like the menu stack.
  const [openQuestions, setOpenQuestions] = useState(false);

  // The tab to highlight while a stacked screen is open: questions are a
  // Profile thing, menus and dishes a Menus thing.
  const activeTab: Tab = openQuestions ? "profile" : openItem || openMenu ? "menus" : tab;

  function switchTab(t: Tab) {
    setOpenQuestions(false);
    setOpenItem(null);
    setOpenMenu(null);
    setTab(t);
  }

  let screen;
  if (openQuestions) {
    screen = <MyQuestionsScreen onBack={() => setOpenQuestions(false)} />;
  } else if (openItem) {
    screen = (
      <DishDetailScreen
        item={openItem}
        // Dishes are always opened from a menu; its language (read off the
        // photo during extraction) is the ask-staff translation target.
        menuLanguage={openMenu?.language}
        onBack={() => setOpenItem(null)}
        // "edit in Settings ›" on the ask-staff sheet jumps to My questions.
        onOpenQuestions={() => setOpenQuestions(true)}
      />
    );
  } else if (openMenu) {
    screen = (
      <MenuScreen menu={openMenu} onOpenItem={setOpenItem} onBack={() => setOpenMenu(null)} />
    );
  } else if (tab === "scan") {
    // Fresh scan: open the menu and land on the Menus tab underneath,
    // so "back" from the result goes to history, not the scan button.
    screen = (
      <ScanScreen
        onScanned={(menu) => {
          setLastScanned(menu);
          setOpenMenu(menu);
          setTab("menus");
        }}
      />
    );
  } else if (tab === "menus") {
    screen = <MenusScreen localMenu={lastScanned} onOpenMenu={setOpenMenu} />;
  } else {
    screen = (
      <ProfileScreen
        onSkip={() => setTab("scan")}
        onOpenQuestions={() => setOpenQuestions(true)}
      />
    );
  }

  return (
    <View style={{ flex: 1 }}>
      {screen}
      <TabBar tab={activeTab} onChange={switchTab} />
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
  tab: { flex: 1, alignItems: "center" },
  tabPill: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: "transparent",
  },
});
