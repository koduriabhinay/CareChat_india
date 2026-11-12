"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, downloadCsv, type Me } from "@/lib/api";
import { useApp, useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import { btnDanger, btnPrimary, btnSecondary, card, ErrorBox, input, LanguageSelect, PageTitle, Shell, Spinner } from "@/components/ui";

export default function Settings() {
  const { t, lang } = useI18n();
  const { refreshMe, signOut } = useApp();
  const { me, allowed } = useGuard({ consent: false });
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);

  // Keep the account's language in step with the picker, for emails.
  useEffect(() => {
    if (allowed && me && me.ui_language !== lang) api("/api/me", "PATCH", { ui_language: lang }).then(() => refreshMe()).catch(() => {});
  }, [allowed, me, lang, refreshMe]);

  if (!allowed || !me) return <Shell><Spinner /></Shell>;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refreshMe();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const setHistory = (enabled: boolean) => {
    if (!enabled && !confirm(t("history_off_confirm"))) return;
    run(() => api<Me>("/api/me/history", "POST", { enabled, language: lang }));
  };

  return (
    <Shell>
      <PageTitle>{t("nav_settings")}</PageTitle>
      <div className="space-y-4">
        <section className={`${card} space-y-2`}>
          <h2 className="font-semibold">{t("account")}</h2>
          <p className="text-sm">{me.guest ? t("guest_account") : t("signed_in_as", { email: me.email ?? me.phone ?? "" })}</p>
          <div className="flex flex-wrap gap-2">
            {me.guest && <Link href="/signin/" className={btnPrimary}>{t("sign_in_to_keep")}</Link>}
            <button className={btnSecondary} onClick={() => { signOut(); router.push("/"); }}>{t("sign_out")}</button>
          </div>
        </section>

        <section className={`${card} space-y-2`}>
          <h2 className="font-semibold">{t("language")}</h2>
          <LanguageSelect className="w-full py-2" />
          <p className="text-xs text-slate-600 dark:text-slate-400">{t("language_help")}</p>
        </section>

        {!me.guest && (
          <section className={`${card} space-y-2`}>
            <h2 className="font-semibold">{t("history_title")}</h2>
            <p className="text-sm">{me.history_enabled ? t("history_on_text") : t("history_off_text")}</p>
            <button className={me.history_enabled ? btnSecondary : btnPrimary} disabled={busy}
                    onClick={() => setHistory(!me.history_enabled)}>
              {me.history_enabled ? t("turn_off_history") : t("turn_on_history")}
            </button>
          </section>
        )}

        {!me.guest && (
          <section className={card}>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-5 w-5 accent-teal-700" checked={me.reminder_emails}
                     onChange={(e) => run(() => api("/api/me", "PATCH", { reminder_emails: e.target.checked }))} />
              {t("reminder_emails_setting")}
            </label>
          </section>
        )}

        <section className={`${card} space-y-2`}>
          <h2 className="font-semibold">{t("your_data")}</h2>
          <button className={btnSecondary} onClick={() => downloadCsv().catch((e) => setError(e.message))}>{t("download_csv")}</button>
          <p className="text-xs text-slate-600 dark:text-slate-400">{t("usage_today", {
            reports: me.usage_today.reports, rcap: me.daily_caps.reports, questions: me.usage_today.questions, qcap: me.daily_caps.questions,
          })}</p>
        </section>

        <section className={`${card} space-y-2 border-red-200 dark:border-red-900`}>
          <h2 className="font-semibold text-red-800 dark:text-red-300">{t("delete_everything")}</h2>
          <p className="text-sm">{t("delete_everything_text")}</p>
          <label className="block text-sm" htmlFor="confirm">{t("type_delete_to_confirm")}</label>
          <input id="confirm" className={input} value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          <button className={btnDanger} disabled={busy || confirmText.trim().toUpperCase() !== "DELETE"}
                  onClick={() => run(async () => { await api("/api/me", "DELETE"); signOut(); router.push("/"); })}>
            {t("delete_everything")}
          </button>
        </section>
        <ErrorBox message={error} />
      </div>
    </Shell>
  );
}
