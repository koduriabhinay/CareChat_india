"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken, type Health, type Me } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface AppState {
  health: Health | null;
  me: Me | null;
  loading: boolean;
  refreshMe: () => Promise<Me | null>;
  signIn: (token: string) => Promise<Me | null>;
  signOut: () => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const { lang, setLang } = useI18n();
  const [health, setHealth] = useState<Health | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      return null;
    }
    try {
      const m = await api<Me>("/api/me");
      setMe(m);
      return m;
    } catch {
      setMe(null);
      return null;
    }
  }, []);

  useEffect(() => {
    refreshMe().finally(() => setLoading(false));
  }, [refreshMe]);

  useEffect(() => {
    api<Health>(`/api/health?language=${lang}`).then(setHealth).catch(() => setHealth(null));
  }, [lang]);

  const signIn = useCallback(
    async (token: string) => {
      setToken(token);
      const m = await refreshMe();
      if (m && m.ui_language && m.ui_language !== "en") setLang(m.ui_language);
      return m;
    },
    [refreshMe, setLang],
  );

  const signOut = useCallback(() => {
    setToken(null);
    setMe(null);
    try {
      sessionStorage.clear();
    } catch {
      /* ignore */
    }
  }, []);

  return <Ctx.Provider value={{ health, me, loading, refreshMe, signIn, signOut }}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}

/** Sends people who aren't signed in (or haven't consented) to the right screen. */
export function useGuard(opts: { consent?: boolean; member?: boolean; admin?: boolean } = { consent: true }) {
  const { me, loading } = useApp();
  const router = useRouter();
  const ready = !loading && !!me;
  useEffect(() => {
    if (loading) return;
    if (!me) router.replace("/");
    else if (opts.consent !== false && me.needs_consent) router.replace("/consent/");
    else if (opts.member && me.guest) router.replace("/signin/");
    else if (opts.admin && me.role !== "admin") router.replace("/home/");
  }, [loading, me, router, opts.consent, opts.member, opts.admin]);
  const allowed =
    ready &&
    !(opts.consent !== false && me!.needs_consent) &&
    !(opts.member && me!.guest) &&
    !(opts.admin && me!.role !== "admin");
  return { me, allowed };
}
