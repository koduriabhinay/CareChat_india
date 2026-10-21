"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApp, useGuard } from "@/lib/app";
import { useI18n, type TKey } from "@/lib/i18n";
import { btnPrimary, card, ErrorBox, PageTitle, Shell, Spinner } from "@/components/ui";

export default function Consent() {
  const { t, lang } = useI18n();
  const { refreshMe } = useApp();
  const { me } = useGuard({ consent: false });
  const router = useRouter();
  const [checks, setChecks] = useState({ processing: false, terms: false, adult: false, history: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!me) return <Shell><Spinner /></Shell>;

  const items: { key: keyof typeof checks; label: TKey; required: boolean; show: boolean }[] = [
    { key: "processing", label: "consent_processing", required: true, show: true },
    { key: "terms", label: "consent_terms", required: true, show: true },
    { key: "adult", label: "consent_adult", required: true, show: true },
    { key: "history", label: "consent_history", required: false, show: !me.guest },
  ];
  const ready = checks.processing && checks.terms && checks.adult;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/consents", "POST", { ...checks, language: lang });
      await refreshMe();
      router.push("/home/");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Shell>
      <PageTitle sub={t("consent_sub")}>{t("consent_title")}</PageTitle>
      <div className={`${card} space-y-4`}>
        <p className="text-sm">
          {t("consent_read_first")}{" "}
          <Link href="/privacy/" className="text-teal-800 underline dark:text-teal-300">{t("privacy_notice")}</Link>{" · "}
          <Link href="/terms/" className="text-teal-800 underline dark:text-teal-300">{t("terms")}</Link>
        </p>
        {items.filter((i) => i.show).map((i) => (
          <label key={i.key} className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 h-5 w-5 shrink-0 accent-teal-700"
              checked={checks[i.key]}
              onChange={(e) => setChecks({ ...checks, [i.key]: e.target.checked })}
            />
            <span className="text-sm">
              {t(i.label)}{" "}
              <span className="text-xs text-slate-500">({i.required ? t("required") : t("optional")})</span>
            </span>
          </label>
        ))}
        {me.guest && <p className="text-xs text-slate-600 dark:text-slate-400">{t("guest_history_note")}</p>}
        <p className="text-xs text-slate-500">{t("notice_version", { version: me.notice_version })}</p>
        <button className={`${btnPrimary} w-full`} disabled={!ready || busy} onClick={submit}>
          {t("agree_continue")}
        </button>
        <ErrorBox message={error} />
      </div>
    </Shell>
  );
}
