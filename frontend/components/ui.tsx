"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Status } from "@/lib/api";
import { useApp } from "@/lib/app";
import { LANGUAGES, SPEECH_LOCALE, useI18n, type TKey } from "@/lib/i18n";

export const btn =
  "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition disabled:opacity-50";
export const btnPrimary = `${btn} bg-teal-700 text-white hover:bg-teal-800 dark:bg-teal-600 dark:hover:bg-teal-500`;
export const btnSecondary = `${btn} border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800`;
export const btnDanger = `${btn} bg-red-700 text-white hover:bg-red-800`;
export const input =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base dark:border-slate-700 dark:bg-slate-900";
export const card = "rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900";

export function LanguageSelect({ className = "" }: { className?: string }) {
  const { lang, setLang, t } = useI18n();
  return (
    <select
      aria-label={t("language")}
      value={lang}
      onChange={(e) => setLang(e.target.value)}
      className={`rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 ${className}`}
    >
      {LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.native}
        </option>
      ))}
    </select>
  );
}

export function Shell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  const { t } = useI18n();
  const { me, health } = useApp();
  const [open, setOpen] = useState(false);
  const links: { href: string; label: TKey; show: boolean }[] = [
    { href: "/home/", label: "nav_home", show: !!me },
    { href: "/ask/", label: "nav_ask", show: !!me },
    { href: "/reminders/", label: "nav_reminders", show: !!me && !me.guest },
    { href: "/settings/", label: "nav_settings", show: !!me },
    { href: "/admin/", label: "nav_admin", show: me?.role === "admin" },
  ];
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 print:hidden">
        <div className={`mx-auto flex items-center gap-3 px-4 py-2.5 ${wide ? "max-w-6xl" : "max-w-3xl"}`}>
          <Link href={me ? "/home/" : "/"} className="flex items-center gap-2 font-semibold text-teal-800 dark:text-teal-300">
            <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-teal-700 text-white">+</span>
            CareChat
          </Link>
          <nav className="ms-auto hidden items-center gap-1 sm:flex">
            {links.filter((l) => l.show).map((l) => (
              <Link key={l.href} href={l.href} className="rounded-lg px-2.5 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                {t(l.label)}
              </Link>
            ))}
          </nav>
          <LanguageSelect className="ms-auto sm:ms-0" />
          {me && (
            <button className="rounded-lg p-1.5 sm:hidden" aria-label={t("menu")} onClick={() => setOpen(!open)}>
              ☰
            </button>
          )}
        </div>
        {open && (
          <nav className="flex flex-col border-t border-slate-200 px-4 py-2 sm:hidden dark:border-slate-800">
            {links.filter((l) => l.show).map((l) => (
              <Link key={l.href} href={l.href} className="py-2" onClick={() => setOpen(false)}>
                {t(l.label)}
              </Link>
            ))}
          </nav>
        )}
      </header>
      <main className={`mx-auto w-full flex-1 px-4 py-5 ${wide ? "max-w-6xl" : "max-w-3xl"}`}>{children}</main>
      <footer className="border-t border-slate-200 px-4 py-4 text-xs text-slate-600 dark:border-slate-800 dark:text-slate-400 print:hidden">
        <div className="mx-auto max-w-3xl space-y-2">
          <p>{health?.disclaimer ?? t("disclaimer_fallback")}</p>
          <p className="font-medium text-red-700 dark:text-red-400">
            {t("footer_emergency", { number: health?.emergency_number ?? "112", crisis: health?.crisis_number ?? "14416" })}
          </p>
          <p className="flex gap-3">
            <Link href="/privacy/" className="underline">{t("privacy_notice")}</Link>
            <Link href="/terms/" className="underline">{t("terms")}</Link>
          </p>
        </div>
      </footer>
    </div>
  );
}

const STATUS_STYLE: Record<Status, string> = {
  normal: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  low: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-300",
  high: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-300",
  abnormal: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-300",
  critical: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  no_range: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  see_report: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

export function StatusChip({ status }: { status: Status }) {
  const { t } = useI18n();
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status]}`}>
      {t(`status_${status}` as TKey)}
    </span>
  );
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
      {message}
    </p>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-teal-700 border-t-transparent" />
      {label}
    </div>
  );
}

export function EmergencyBox({ message, call }: { message: string; call: string }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="rounded-xl border-2 border-red-600 bg-red-50 p-4 text-red-900 dark:bg-red-950 dark:text-red-100">
      <p className="whitespace-pre-line font-medium">{message}</p>
      <a href={`tel:${call}`} className={`${btnDanger} mt-3`}>
        {t("call_number", { number: call })}
      </a>
    </div>
  );
}

/** Reads text aloud with the browser's own voice, if it has one for this language. */
export function SpeakButton({ text, lang }: { text: string; lang: string }) {
  const { t } = useI18n();
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(false);
  useEffect(() => setSupported(typeof window !== "undefined" && "speechSynthesis" in window), []);
  useEffect(() => () => { if (supported) window.speechSynthesis.cancel(); }, [supported]);
  if (!supported || !text) return null;
  function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(text.replace(/\[\d+\]/g, "").replace(/[*#_`]/g, ""));
    u.lang = SPEECH_LOCALE[lang] ?? "en-IN";
    const voice = synth.getVoices().find((v) => v.lang.toLowerCase().startsWith(u.lang.slice(0, 2)));
    if (voice) u.voice = voice;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.cancel();
    synth.speak(u);
    setSpeaking(true);
  }
  return (
    <button type="button" onClick={toggle} className="text-xs text-teal-800 underline dark:text-teal-300">
      {speaking ? t("stop_reading") : t("read_aloud")}
    </button>
  );
}

export function PageTitle({ children, sub }: { children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="mb-4">
      <h1 className="text-xl font-semibold">{children}</h1>
      {sub && <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{sub}</p>}
    </div>
  );
}
