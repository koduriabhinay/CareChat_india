"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, downloadCsv, type Profile, type ReportOut, type Trends } from "@/lib/api";
import { useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import TrendChart from "@/components/TrendChart";
import { btnPrimary, btnSecondary, card, ErrorBox, PageTitle, Shell, Spinner, StatusChip } from "@/components/ui";

function TrendsView() {
  const { t } = useI18n();
  const { me, allowed } = useGuard();
  const profileId = useSearchParams().get("profile") ?? "";
  const [profile, setProfile] = useState<Profile | null>(null);
  const [trends, setTrends] = useState<Trends | null>(null);
  const [reports, setReports] = useState<ReportOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!allowed || !profileId) return;
    api<Profile>(`/api/profiles/${profileId}`).then(setProfile).catch((e) => setError(e.message));
    api<Trends>(`/api/profiles/${profileId}/trends`).then(setTrends).catch((e) => setError(e.message));
    api<ReportOut[]>(`/api/reports?profile_id=${profileId}`).then(setReports).catch(() => {});
  }, [allowed, profileId]);

  if (!allowed || !me) return <Shell><Spinner /></Shell>;
  if (error) return <Shell><ErrorBox message={error} /></Shell>;
  if (!trends || !profile) return <Shell><Spinner /></Shell>;

  const charts = trends.series.filter((s) => s.points.length >= 2);
  const big = trends.since_last_visit.filter((s) => s.change?.big);
  return (
    <Shell>
      <PageTitle sub={profile.display_name}>{t("reports_and_trends")}</PageTitle>
      <div className="space-y-4">
        {!trends.history_enabled && (
          <div className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
            {me.guest ? t("trends_need_account") : t("trends_need_history")}{" "}
            <Link href={me.guest ? "/signin/" : "/settings/"} className="font-medium underline">
              {me.guest ? t("sign_in") : t("turn_on_history")}
            </Link>
          </div>
        )}

        {trends.since_last_visit.length > 0 && (
          <section className={card}>
            <h2 className="font-semibold">{t("since_last_visit")}</h2>
            {big.length > 0 && (
              <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-100">
                {t("show_doctor_soon")}
              </p>
            )}
            <ul className="mt-2 divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {trends.since_last_visit.map((s) => (
                <li key={s.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className={s.change!.big ? "font-medium" : ""}>{s.test_name}</span>
                  <span dir="ltr">
                    {s.change!.from} → {s.change!.to} {s.unit}
                    {s.change!.percent != null && (
                      <span className="ms-2 text-xs text-slate-600 dark:text-slate-400">
                        ({s.change!.percent > 0 ? "+" : ""}{s.change!.percent}%)
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">{t("change_note")}</p>
          </section>
        )}

        {charts.map((s) => (
          <section key={s.key} className={card}>
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-semibold">{s.test_name} <span className="text-xs font-normal text-slate-500">({s.unit})</span></h2>
              <StatusChip status={s.points[s.points.length - 1].status} />
            </div>
            <TrendChart series={s} />
            <details className="text-xs">
              <summary className="cursor-pointer text-slate-600 dark:text-slate-400">{t("show_as_table")}</summary>
              <table className="mt-1 w-full" dir="ltr">
                <tbody>
                  {s.points.map((p) => (
                    <tr key={p.report_id}><td className="py-0.5">{p.date}</td><td>{p.value} {s.unit}</td><td>{p.reference_range ?? ""}</td></tr>
                  ))}
                </tbody>
              </table>
            </details>
          </section>
        ))}
        {charts.length === 0 && <p className="text-sm text-slate-600 dark:text-slate-400">{t("trends_need_two")}</p>}

        <section className={card}>
          <h2 className="mb-2 font-semibold">{t("all_reports")}</h2>
          {reports.length === 0 ? (
            <p className="text-sm text-slate-600 dark:text-slate-400">{t("no_reports_yet")}</p>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
              {reports.map((r) => (
                <li key={r.id} className="py-2">
                  <Link href={`/report/?id=${r.id}`} className="flex justify-between gap-2 underline-offset-2 hover:underline">
                    <span>{r.report_type ?? t("lab_report")} {r.report_date && `· ${r.report_date}`}</span>
                    <span className="text-xs text-slate-600 dark:text-slate-400">
                      {r.status === "ready" ? (r.critical ? t("status_critical") : r.flagged ? t("values_to_look_at", { count: r.flagged }) : t("all_in_range")) : t(`report_status_${r.status}`)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <div className="flex flex-wrap gap-2">
          <Link href={`/upload/?profile=${profileId}`} className={btnPrimary}>{t("upload_report")}</Link>
          <button className={btnSecondary} onClick={() => downloadCsv(profileId).catch((e) => setError(e.message))}>{t("download_csv")}</button>
        </div>
      </div>
    </Shell>
  );
}

export default function Page() {
  return <Suspense><TrendsView /></Suspense>;
}
