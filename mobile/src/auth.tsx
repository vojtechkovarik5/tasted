// Auth state — STUB that mimics Clerk's surface so screens are written
// against the final shape today.
//
// SWAPPING IN REAL CLERK (@clerk/clerk-expo):
//   1. npx expo install @clerk/clerk-expo expo-secure-store
//   2. In App.tsx replace <AuthProvider> with <ClerkProvider publishableKey=...
//      tokenCache={tokenCache}>
//   3. Replace this hook with Clerk's useAuth()/useUser(), and signIn() with
//      useSSO({ strategy: "oauth_apple" | "oauth_google" })
//   4. api.ts attaches `Authorization: Bearer ${await getToken()}`
//
// Until then, signIn() instantly "logs in" a fake user so the whole
// logged-in/logged-out flow is testable.

import { createContext, useContext, useState } from "react";

import { setAuthToken } from "./api";

export type OAuthStrategy = "oauth_apple" | "oauth_google";

export type AuthUser = {
  id: string;
  name: string;
  email: string;
  initials: string;
};

type AuthState = {
  isSignedIn: boolean;
  user: AuthUser | null;
  signIn: (strategy: OAuthStrategy) => Promise<void>;
  signInWithEmail: (email: string) => Promise<void>;
  signOut: () => void;
};

const AuthContext = createContext<AuthState>({
  isSignedIn: false,
  user: null,
  signIn: async () => {},
  signInWithEmail: async () => {},
  signOut: () => {},
});

/** Initials from a display name or email local part ("jan.novak" -> "JN"). */
function initialsOf(nameOrEmail: string): string {
  const base = nameOrEmail.split("@")[0].replace(/[._-]+/g, " ").trim();
  const parts = base.split(/\s+/).filter(Boolean);
  const letters = (parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "");
  return (letters || base.slice(0, 2)).toUpperCase();
}

export function AuthProvider(props: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);

  const signIn = async (strategy: OAuthStrategy) => {
    // TODO(clerk): real OAuth flow. Fake user for now — the backend's fake
    // auth trusts the bearer string as the identity, so sending the stub id
    // gives this "account" real per-user history/prefs on the server.
    setUser({
      id: "user_stub",
      name: strategy === "oauth_apple" ? "Jana Nováková" : "Jana N. (Google)",
      email: "jana@example.com",
      initials: "JN",
    });
    setAuthToken("user_stub"); // with real Clerk: await getToken()
  };

  // Email magic-code path (Clerk's email-code strategy). The stub logs in
  // immediately; real Clerk would prepare + verify a code first.
  const signInWithEmail = async (email: string) => {
    const local = email.split("@")[0].replace(/[._-]+/g, " ").trim();
    const name = local.replace(/\b\w/g, (c) => c.toUpperCase()) || "You";
    setUser({ id: "user_stub", name, email, initials: initialsOf(email) });
    setAuthToken("user_stub");
  };

  const signOut = () => {
    setUser(null);
    setAuthToken(null);
  };

  return (
    <AuthContext.Provider
      value={{ isSignedIn: user !== null, user, signIn, signInWithEmail, signOut }}
    >
      {props.children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
