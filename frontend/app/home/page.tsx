"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Profile, type Reminder, type ReportOut } from "@/lib/api";
import { useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import DueReminders from "@/components/DueReminders";
import { btnPrimary, btnSecondary, card, ErrorBox, PageTitle, Shell, Spinner } from "@/components/ui";

export default function Home() {
  const { t } = useI18n();
  const { me, allowed } = useGuard();
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [reading, setReading] = useState<ReportOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reminders, setReminders] = useState<Reminder[]>([]);

  useEffect(() => {
    if (!allowed) return;
    api<Profile[]>("/api/profiles").then(setProfiles).catch((e) => setError(e.message));
    if (!me?.guest) api<Reminder[]>("/api/reminders").then(setReminders).catch(() => {});
    api<ReportOut[]>("/api/reports").then((r) => setReading(r.filter((x) => x.status === "reading"))).catch(() => {});
  }, [allowed, me?.guest]);

  if (!allowed || !me) return <Shell><Spinner /></Shell>;

  const flaggedPeople = (profiles ?? []).filter((p) => p.latest_report && (p.latest_report.flagged > 0 || p.latest_report.critical));
  const hasSelf = (profiles ?? []).some((p) => p.is_self);

  return (
    <Shell>
      <PageTitle sub={t("home_sub")}>{t("home_title")}</PageTitle>
      {me.guest && (
        <div className="mb-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
          {t("guest_banner")}{" "}
          <Link href="/signin/" className="font-medium underline">{t("sign_in")}</Link>
        </div>
      )}
      <ErrorBox message={error} />
      {reminders.length > 0 && <div className="mb-4"><DueReminders items={reminders} /></div>}
      {reading.length > 0 && (
        <div className={`${card} mb-4`}>
          {reading.map((r) => (
            <Link key={r.id} href={`/report/?id=${r.id}`} className="block">
              <Spinner label={t("report_still_reading")} />
            </Link>
          ))}
        </div>
      )}
      {flaggedPeople.length > 0 && (
        <section className={`${card} mb-4 border-amber-300 dark:border-amber-800`}>
          <h2 className="font-semibold">{t("family_attention")}</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {flaggedPeople.map((p) => (
              <li key={p.id}>
                <Link href={`/report/?id=${p.latest_report!.id}`} className="underline">
                  {p.display_name}
                </Link>
                {": "}
                {p.latest_report!.critical ? (
                  <span className="font-medium text-red-700 dark:text-red-400">{t("has_urgent_value")}</span>
                ) : (
                  t("values_to_look_at", { count: p.latest_report!.flagged })
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {profiles === null ? (
        <Spinner />
      ) : profiles.length === 0 ? (
        <div className={`${card} text-center`}>
          <p>{t("add_yourself_first")}</p>
          <Link href="/profile/?relation=self" className={`${btnPrimary} mt-3`}>{t("add_my_details")}</Link>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {profiles.map((p) => (
            <article key={p.id} className={card}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="font-semibold">{p.display_name}</h2>
                  <p className="text-xs text-slate-600 dark:text-slate-400">
                    {p.is_self ? t("relation_self") : p.relation}
                    {p.age != null && ` · ${t("age_years", { age: p.age })}`}
                  </p>
                </div>
                {p.latest_report?.critical && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">{t("status_critical")}</span>
                )}
              </div>
              <p className="mt-2 text-sm">
                {p.latest_report ? (
                  <Link href={`/report/?id=${p.latest_report.id}`} className="underline">
                    {p.latest_report.report_type ?? t("lab_report")}
                    {p.latest_report.report_date && ` (${p.latest_report.report_date})`}
                    {": "}
                    {p.latest_report.flagged > 0 ? t("values_to_look_at", { count: p.latest_report.flagged }) : t("all_in_range")}
                  </Link>
                ) : (
                  <span className="text-slate-600 dark:text-slate-400">{t("no_reports_yet")}</span>
                )}
              </p>
              {p.health_form_due && (
                <Link href={`/profile/?id=${p.id}`} className="mt-2 block text-xs text-teal-800 underline dark:text-teal-300">
                  {t("health_form_due")}
                </Link>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <Link href={`/upload/?profile=${p.id}`} className={btnPrimary}>{t("upload_report")}</Link>
                <Link href={`/trends/?profile=${p.id}`} className={btnSecondary}>{t("reports_and_trends")}</Link>
                <Link href={`/profile/?id=${p.id}`} className={btnSecondary}>{t("health_details")}</Link>
              </div>
            </article>
          ))}
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {profiles && profiles.length > 0 && (
          <Link href={hasSelf ? "/profile/?relation=family" : "/profile/?relation=self"} className={btnSecondary}>
            {hasSelf ? t("add_family_member") : t("add_my_details")}
          </Link>
        )}
        <Link href="/ask/" className={btnSecondary}>{t("ask_general_question")}</Link>
      </div>
    </Shell>
  );
}
