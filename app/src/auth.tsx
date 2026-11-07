import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";

import { api, Me, setToken, setUnauthorizedHandler, tokenStore } from "./api";

interface Auth {
  me: Me | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  setMe: (me: Me) => void;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const signOut = useCallback(async () => {
    setToken(null);
    await tokenStore.clear();
    setMe(null);
  }, []);

  const start = useCallback(async (token: string) => {
    setToken(token);
    await tokenStore.set(token);
    setMe(await api<Me>("/me"));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => void signOut());
    (async () => {
      const saved = await tokenStore.get();
      if (saved) await start(saved).catch(signOut);
      setReady(true);
    })();
  }, [signOut, start]);

  const value: Auth = {
    me,
    ready,
    signIn: async (email, password) => start((await api<{ token: string }>("/auth/login", "POST", { email, password })).token),
    signUp: async (email, password, name) =>
      start((await api<{ token: string }>("/auth/register", "POST", { email, password, name })).token),
    signOut,
    refresh: async () => setMe(await api<Me>("/me")),
    setMe,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside AuthProvider");
  return auth;
}

export const nicheLabel = (n: number) => (n >= 0.5 ? "Niche" : "Normal");
