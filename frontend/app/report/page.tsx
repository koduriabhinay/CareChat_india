"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, type Profile, type ReportOut } from "@/lib/api";
import { useApp, useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import Chat from "@/components/Chat";
import ValuesTable from "@/components/ValuesTable";
import { btnDanger, btnPrimary, btnSecondary, card, EmergencyBox, ErrorBox, input, PageTitle, Shell, SpeakButton, Spinner } from "@/components/ui";

function ReportView() {
  const { t, lang } = useI18n();
  const { health } = useApp();
  const { me, allowed } = useGuard();
  const id = useSearchParams().get("id") ?? "";
  const router = useRouter();
  const [report, setReport] = useState<ReportOut | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [moveTo, setMoveTo] = useState("");

  const load = useCallback(() => api<ReportOut>(`/api/reports/${id}`).then(setReport).catch((e) => setError(e.message)), [id]);

  useEffect(() => {
    if (!allowed) return;
    load();
    api<Profile[]>("/api/profiles").then(setProfiles).catch(() => {});
  }, [allowed, load]);

  useEffect(() => {
    if (report?.status !== "reading") return;
    const timer = setTimeout(load, 2000);
    return () => clearTimeout(timer);
  }, [report, load]);

  if (!allowed || !me) return <Shell><Spinner /></Shell>;
  if (error && !report) return <Shell><ErrorBox message={error} /><Link href="/home/" className={`${btnSecondary} mt-3`}>{t("back_home")}</Link></Shell>;
  if (!report) return <Shell><Spinner /></Shell>;

  const owner = profiles.find((p) => p.id === report.profile_id);
  const suggested = report.suggested_profile_id && report.suggested_profile_id !== report.profile_id
    ? profiles.find((p) => p.id === report.suggested_profile_id) : null;

  async function move(profileId: string) {
    try {
      setReport(await api<ReportOut>(`/api/reports/${id}/profile`, "POST", { profile_id: profileId }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!confirm(t("confirm_delete_report"))) return;
    try {
      await api(`/api/reports/${id}`, "DELETE");
      router.push("/home/");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (report.status === "reading") {
    return (
      <Shell>
        <PageTitle>{t("reading_report")}</PageTitle>
        <div className={card}><Spinner label={t("reading_report_help")} /></div>
      </Shell>
    );
  }

  if (report.status === "failed") {
    return (
      <Shell>
        <PageTitle>{t("report_failed")}</PageTitle>
        <ErrorBox message={report.error} />
        <div className="mt-3 flex gap-2">
          <Link href={`/upload/?profile=${report.profile_id}`} className={btnPrimary}>{t("try_again")}</Link>
          <button className={btnSecondary} onClick={remove}>{t("delete_report")}</button>
        </div>
      </Shell>
    );
  }

  const s = report.summary;
  const summaryText = s ? [s.overall, ...s.flagged.map((f) => `${f.test_name}: ${f.meaning}`)].join("\n") : "";
  return (
    <Shell>
      <PageTitle sub={[owner?.display_name, report.report_date].filter(Boolean).join(" · ")}>
        {report.report_type ?? t("lab_report")}
      </PageTitle>
      <div className="space-y-4">
        {report.critical && report.critical_message && (
          <EmergencyBox message={report.critical_message} call={health?.emergency_number ?? "112"} />
        )}

        {(report.mismatch?.length ?? 0) > 0 && (
          <div className={`${card} border-amber-300 dark:border-amber-800`}>
            <p className="text-sm font-medium">
              {t("mismatch_warning", {
                name: owner?.display_name ?? "",
                what: report.mismatch!.map((m) => t(m === "age" ? "mismatch_age" : "mismatch_sex")).join(", "),
              })}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <select className={`${input} w-auto`} value={moveTo} onChange={(e) => setMoveTo(e.target.value)}>
                <option value="">{t("whose_report")}</option>
                {profiles.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
              </select>
              <button className={btnSecondary} disabled={!moveTo} onClick={() => move(moveTo)}>{t("move_report")}</button>
            </div>
          </div>
        )}

        {suggested && (
          <div className={`${card} flex flex-wrap items-center gap-2`}>
            <p className="text-sm">{t("looks_like_report_of", { name: suggested.display_name })}</p>
            <button className={btnSecondary} onClick={() => move(suggested.id)}>{t("move_to", { name: suggested.display_name })}</button>
          </div>
        )}

        <section className={`${card} space-y-3`}>
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">{t("summary_title")}</h2>
            <SpeakButton text={summaryText} lang={report.language ?? lang} />
          </div>
          {s ? (
            <>
              <p className="leading-relaxed">{s.overall}</p>
              {s.flagged.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold">{t("what_flagged_mean")}</h3>
                  <ul className="mt-1 space-y-2">
                    {s.flagged.map((f, i) => (
                      <li key={i} className="text-sm"><span className="font-medium">{f.test_name}:</span> {f.meaning}</li>
                    ))}
                  </ul>
                </div>
              )}
              {s.doctor_questions.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold">{t("ask_your_doctor")}</h3>
                  <ul className="mt-1 list-disc space-y-1 ps-5 text-sm">
                    {s.doctor_questions.map((q, i) => <li key={i}>{q}</li>)}
                  </ul>
                </div>
              )}
              {s.general_tips.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold">{t("general_tips")}</h3>
                  <ul className="mt-1 list-disc space-y-1 ps-5 text-sm">
                    {s.general_tips.map((q, i) => <li key={i}>{q}</li>)}
                  </ul>
                </div>
              )}
              {(report.sources?.length ?? 0) > 0 && (
                <ol className="space-y-0.5 border-t border-slate-200 pt-2 text-xs dark:border-slate-700">
                  {report.sources!.map((src) => (
                    <li key={src.index}>[{src.index}] <a className="underline" href={src.url} target="_blank" rel="noreferrer">{src.title}</a></li>
                  ))}
                </ol>
              )}
            </>
          ) : (
            <p className="text-sm text-slate-600 dark:text-slate-400">{t("summary_unavailable")}</p>
          )}
        </section>

        <section className={card}>
          <h2 className="mb-2 font-semibold">{t("your_values")}</h2>
          <ValuesTable rows={report.rows ?? []} />
          {(report.other_findings?.length ?? 0) > 0 && (
            <div className="mt-3">
              <h3 className="text-sm font-semibold">{t("other_notes")}</h3>
              <ul className="mt-1 list-disc ps-5 text-sm">{report.other_findings!.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </div>
          )}
          <p className="mt-3 text-xs text-slate-600 dark:text-slate-400">{t("values_copied_note")}</p>
        </section>

        <section className={card}>
          <h2 className="mb-3 font-semibold">{t("ask_about_report")}</h2>
          <Chat reportId={report.id} profileId={report.profile_id} historyEnabled={me.history_enabled}
                suggestions={[t("suggest_explain_simply"), t("suggest_food")]} />
        </section>

        <div className="flex flex-wrap gap-2">
          <Link href={`/print/?id=${report.id}`} className={btnSecondary}>{t("doctor_pdf")}</Link>
          <Link href={`/trends/?profile=${report.profile_id}`} className={btnSecondary}>{t("reports_and_trends")}</Link>
          <button className={btnDanger} onClick={remove}>{t("delete_report")}</button>
        </div>
        {report.expires_at && <p className="text-xs text-slate-600 dark:text-slate-400">{t("report_expires_note")}</p>}
        <ErrorBox message={error} />
      </div>
    </Shell>
  );
}

export default function Page() {
  return <Suspense><ReportView /></Suspense>;
}
