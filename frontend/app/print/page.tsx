"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type Profile, type ReportOut, type Trends } from "@/lib/api";
import { useApp, useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import ValuesTable from "@/components/ValuesTable";
import { btnPrimary, ErrorBox, Spinner } from "@/components/ui";

/** A one-page summary to show the doctor; "Save as PDF" in the print dialog makes the PDF. */
function PrintView() {
  const { t } = useI18n();
  const { health } = useApp();
  const { allowed } = useGuard();
  const id = useSearchParams().get("id") ?? "";
  const [report, setReport] = useState<ReportOut | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [trends, setTrends] = useState<Trends | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!allowed) return;
    api<ReportOut>(`/api/reports/${id}`).then((r) => {
      setReport(r);
      api<Profile>(`/api/profiles/${r.profile_id}`).then(setProfile).catch(() => {});
      api<Trends>(`/api/profiles/${r.profile_id}/trends`).then(setTrends).catch(() => {});
    }).catch((e) => setError(e.message));
  }, [allowed, id]);

  if (error) return <main className="p-6"><ErrorBox message={error} /></main>;
  if (!report || !allowed) return <main className="p-6"><Spinner /></main>;

  const facts: [string, string | null][] = profile ? [
    [t("display_name"), profile.display_name],
    [t("age"), profile.age != null ? String(profile.age) : null],
    [t("sex"), profile.sex ? t(`sex_${profile.sex}`) : null],
    [t("conditions"), profile.conditions.join(", ") || null],
    [t("medicines"), profile.medicines.join(", ") || null],
    [t("diet_type"), profile.diet_type ? t(`diet_${profile.diet_type}` as "diet_jain") : null],
    ["BMI", profile.bmi ? String(profile.bmi.value) : null],
  ] : [];

  return (
    <main className="mx-auto max-w-3xl bg-white p-6 text-slate-900 print:p-0">
      <div className="mb-4 flex items-center justify-between print:hidden">
        <p className="text-sm text-slate-600">{t("print_help")}</p>
        <button className={btnPrimary} onClick={() => window.print()}>{t("print_save_pdf")}</button>
      </div>
      <h1 className="text-xl font-semibold">{t("doctor_summary_title")}</h1>
      <p className="text-sm text-slate-600">
        {report.report_type ?? t("lab_report")} {report.report_date && `· ${report.report_date}`} · {t("made_with_carechat")}
      </p>
      {facts.length > 0 && (
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {facts.filter(([, v]) => v).map(([k, v]) => (
            <div key={k} className="flex gap-2"><dt className="font-medium">{k}:</dt><dd>{v}</dd></div>
          ))}
        </dl>
      )}
      <h2 className="mt-5 font-semibold">{t("your_values")}</h2>
      <ValuesTable rows={report.rows ?? []} />
      {trends && trends.since_last_visit.length > 0 && (
        <>
          <h2 className="mt-5 font-semibold">{t("since_last_visit")}</h2>
          <ul className="mt-1 text-sm">
            {trends.since_last_visit.map((s) => (
              <li key={s.key}>{s.test_name}: {s.change!.from} → {s.change!.to} {s.unit}</li>
            ))}
          </ul>
        </>
      )}
      {report.summary && report.summary.doctor_questions.length > 0 && (
        <>
          <h2 className="mt-5 font-semibold">{t("questions_for_doctor")}</h2>
          <ul className="mt-1 list-disc ps-5 text-sm">{report.summary.doctor_questions.map((q, i) => <li key={i}>{q}</li>)}</ul>
        </>
      )}
      <p className="mt-6 border-t border-slate-200 pt-2 text-xs text-slate-600">{health?.disclaimer}</p>
    </main>
  );
}

export default function Page() {
  return <Suspense><PrintView /></Suspense>;
}
