"use client";

// App text in 11 languages. English is the source; other files are translations
// and fall back to English for any missing key.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import en from "@/locales/en.json";
import hi from "@/locales/hi.json";
import bn from "@/locales/bn.json";
import te from "@/locales/te.json";
import mr from "@/locales/mr.json";
import ta from "@/locales/ta.json";
import ur from "@/locales/ur.json";
import gu from "@/locales/gu.json";
import kn from "@/locales/kn.json";
import or from "@/locales/or.json";
import ml from "@/locales/ml.json";

export type Messages = Record<string, string>;
export type TKey = keyof typeof en;

const ALL: Record<string, Messages> = { en, hi, bn, te, mr, ta, ur, gu, kn, or, ml };

export const LANGUAGES: { code: string; name: string; native: string }[] = [
  { code: "en", name: "English", native: "English" },
  { code: "hi", name: "Hindi", native: "हिन्दी" },
  { code: "bn", name: "Bengali", native: "বাংলা" },
  { code: "te", name: "Telugu", native: "తెలుగు" },
  { code: "mr", name: "Marathi", native: "मराठी" },
  { code: "ta", name: "Tamil", native: "தமிழ்" },
  { code: "ur", name: "Urdu", native: "اردو" },
  { code: "gu", name: "Gujarati", native: "ગુજરાતી" },
  { code: "kn", name: "Kannada", native: "ಕನ್ನಡ" },
  { code: "or", name: "Odia", native: "ଓଡ଼ିଆ" },
  { code: "ml", name: "Malayalam", native: "മലയാളം" },
];

// For the browser's speech features.
export const SPEECH_LOCALE: Record<string, string> = {
  en: "en-IN", hi: "hi-IN", bn: "bn-IN", te: "te-IN", mr: "mr-IN", ta: "ta-IN", ur: "ur-IN", gu: "gu-IN",
  kn: "kn-IN", or: "or-IN", ml: "ml-IN",
};

const LANG_KEY = "carechat.lang";

interface I18n {
  lang: string;
  setLang: (code: string) => void;
  t: (key: TKey, vars?: Record<string, string | number>) => string;
}

const Ctx = createContext<I18n | null>(null);

export function storedLang(): string {
  try {
    const v = localStorage.getItem(LANG_KEY);
    if (v && ALL[v]) return v;
  } catch {
    /* ignore */
  }
  return "en";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState("en");

  useEffect(() => {
    setLangState(storedLang());
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ur" ? "rtl" : "ltr";
  }, [lang]);

  const setLang = useCallback((code: string) => {
    if (!ALL[code]) return;
    setLangState(code);
    try {
      localStorage.setItem(LANG_KEY, code);
    } catch {
      /* ignore */
    }
  }, []);

  const t = useCallback(
    (key: TKey, vars?: Record<string, string | number>) => {
      let text = ALL[lang]?.[key] || (en as Messages)[key] || key;
      if (vars) for (const [k, v] of Object.entries(vars)) text = text.split(`{${k}}`).join(String(v));
      return text;
    },
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
