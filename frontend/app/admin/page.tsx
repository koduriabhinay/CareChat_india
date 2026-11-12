"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import { card, ErrorBox, PageTitle, Shell, Spinner } from "@/components/ui";

interface Day {
  day: string;
  events: Record<string, number>;
  cost: number;
  tokens: Record<string, number>;
  active: number;
  latency_p95: number | null;
}
interface Metrics {
  days: Day[];
  today: { total?: number; by_role?: Record<string, number>; by_language?: Record<string, number> };
  month_spend_usd: number;
  monthly_budget_usd: number;
  daily_caps: { reports: number; questions: number };
  queue: { reports_reading: number };
}
interface Feedback { id: string; rating: string; comment: string; question: string; answer: string; language: string; at: string }
interface Audit { at: string; actor: string; actor_role: string; action: string; target: string }

function Tile({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className={card}>
      <p className="text-xs text-slate-600 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{sub}</p>}
    </div>
  );
}

/** Single-series daily bars with a hover readout. */
function DailyBars({ days, value, format }: { days: Day[]; value: (d: Day) => number; format: (n: number) => string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 140, B = 20, T = 18;
  const max = Math.max(...days.map(value), 0) || 1;
  const bw = Math.min(48, (W - 8) / Math.max(days.length, 1));
  const active = hover ?? days.length - 1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={days.map((d) => `${d.day}: ${format(value(d))}`).join(", ")}>
      <line x1={0} x2={W} y1={H - B} y2={H - B} className="stroke-slate-300 dark:stroke-slate-700" />
      {days.map((d, i) => {
        const h = ((H - B - T) * value(d)) / max;
        return (
          <g key={d.day} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={i * bw + 4} y={T} width={bw} height={H - B - T} fill="transparent" />
            <rect x={i * bw + 5} y={H - B - h} width={Math.max(bw - 2, 2)} height={h} rx={Math.min(4, bw / 3)}
                  className={i === active ? "fill-teal-700 dark:fill-teal-400" : "fill-teal-600/60 dark:fill-teal-500/60"} />
          </g>
        );
      })}
      {days[active] && (
        <text x={Math.min(Math.max(active * bw + bw / 2, 60), W - 60)} y={12} textAnchor="middle" className="fill-slate-900 text-[12px] dark:fill-slate-100">
          {days[active].day}: {format(value(days[active]))}
        </text>
      )}
      {days.length > 0 && (
        <>
          <text x={4} y={H - 4} className="fill-slate-500 text-[11px]">{days[0].day}</text>
          <text x={W - 4} y={H - 4} textAnchor="end" className="fill-slate-500 text-[11px]">{days[days.length - 1].day}</text>
        </>
      )}
    </svg>
  );
}

export default function Admin() {
  const { t } = useI18n();
  const { allowed } = useGuard({ consent: false, admin: true });
  const [m, setM] = useState<Metrics | null>(null);
  const [consents, setConsents] = useState<{ days: Record<string, string | number>[] } | null>(null);
  const [feedback, setFeedback] = useState<Feedback[] | null>(null);
  const [audit, setAudit] = useState<Audit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!allowed) return;
    api<Metrics>("/api/admin/metrics").then(setM).catch((e) => setError(e.message));
    api<{ days: Record<string, string | number>[] }>("/api/admin/consents").then(setConsents).catch(() => {});
    api<Audit[]>("/api/admin/audit").then(setAudit).catch(() => {});
  }, [allowed]);

  if (!allowed) return <Shell><Spinner /></Shell>;
  if (error) return <Shell wide><ErrorBox message={error} /></Shell>;
  if (!m) return <Shell wide><Spinner /></Shell>;

  const ev = (d: Day, k: string) => d.events[k] ?? 0;
  const sum = (k: string) => m.days.reduce((a, d) => a + ev(d, k), 0);
  const pct = m.monthly_budget_usd ? Math.min(100, (m.month_spend_usd / m.monthly_budget_usd) * 100) : 0;
  const up = sum("feedback_up"), down = sum("feedback_down");
  const fmtObj = (o?: Record<string, number>) => Object.entries(o ?? {}).map(([k, v]) => `${k} ${v}`).join(" · ") || "-";

  return (
    <Shell wide>
      <PageTitle sub={t("admin_sub")}>{t("nav_admin")}</PageTitle>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Tile label={t("active_today")} value={m.today.total ?? 0} sub={fmtObj(m.today.by_role)} />
          <Tile label={t("month_spend")} value={`$${m.month_spend_usd.toFixed(2)}`} sub={t("of_budget", { budget: m.monthly_budget_usd })} />
          <Tile label={t("reading_now")} value={m.queue.reports_reading} />
          <Tile label={t("feedback_30d")} value={`👍 ${up} · 👎 ${down}`} />
        </div>
        <div className={card}>
          <p className="text-sm">{t("budget_used", { pct: pct.toFixed(0) })}</p>
          <div className="mt-2 h-2 rounded-full bg-slate-200 dark:bg-slate-800">
            <div className={`h-2 rounded-full ${pct >= 80 ? "bg-red-600" : "bg-teal-700"}`} style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            {t("per_user_caps", { reports: m.daily_caps.reports, questions: m.daily_caps.questions })} · {t("languages_today")}: {fmtObj(m.today.by_language)}
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          <section className={card}>
            <h2 className="text-sm font-semibold">{t("reports_per_day")}</h2>
            <DailyBars days={m.days} value={(d) => ev(d, "reports_uploaded")} format={(n) => String(n)} />
          </section>
          <section className={card}>
            <h2 className="text-sm font-semibold">{t("cost_per_day")}</h2>
            <DailyBars days={m.days} value={(d) => d.cost} format={(n) => `$${n.toFixed(2)}`} />
          </section>
        </div>

        <section className={`${card} overflow-x-auto`}>
          <h2 className="mb-2 text-sm font-semibold">{t("daily_table")}</h2>
          <table className="w-full text-xs tabular-nums">
            <thead>
              <tr className="text-start text-slate-600 dark:text-slate-400">
                {["day", "active", "reports", "failed", "critical", "chats", "emergency", "self_harm", "unavailable", "fb_up", "fb_down", "errors", "tokens_in", "tokens_out", "cost", "p95_s"].map((h) => (
                  <th key={h} className="px-1 py-1 text-start font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...m.days].reverse().map((d) => (
                <tr key={d.day} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-1 py-1">{d.day}</td>
                  <td className="px-1">{d.active}</td>
                  <td className="px-1">{ev(d, "reports_uploaded")}</td>
                  <td className="px-1">{ev(d, "report_failed")}</td>
                  <td className="px-1">{ev(d, "report_critical")}</td>
                  <td className="px-1">{ev(d, "chats")}</td>
                  <td className="px-1">{ev(d, "safety_emergency")}</td>
                  <td className="px-1">{ev(d, "safety_self_harm")}</td>
                  <td className="px-1">{ev(d, "safety_unavailable")}</td>
                  <td className="px-1">{ev(d, "feedback_up")}</td>
                  <td className="px-1">{ev(d, "feedback_down")}</td>
                  <td className="px-1">{ev(d, "errors") + ev(d, "job_errors")}</td>
                  <td className="px-1">{(d.tokens.input ?? 0) + (d.tokens.cache_read ?? 0) + (d.tokens.cache_write ?? 0)}</td>
                  <td className="px-1">{d.tokens.output ?? 0}</td>
                  <td className="px-1">${d.cost.toFixed(3)}</td>
                  <td className="px-1">{d.latency_p95 != null ? d.latency_p95.toFixed(1) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className={`${card} overflow-x-auto`}>
          <h2 className="mb-2 text-sm font-semibold">{t("consents_per_day")}</h2>
          {consents && consents.days.length ? (
            <table className="w-full text-xs tabular-nums">
              <tbody>
                {consents.days.map((d) => (
                  <tr key={String(d.day)} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="px-1 py-1">{d.day}</td>
                    <td className="px-1">{Object.entries(d).filter(([k]) => k !== "day").map(([k, v]) => `${k}: ${v}`).join(" · ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-xs">-</p>}
        </section>

        <section className={card}>
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{t("feedback_sample")}</h2>
            {!feedback && (
              <button className="text-xs underline" onClick={() => api<Feedback[]>("/api/admin/feedback").then(setFeedback).catch((e) => setError(e.message))}>
                {t("load_feedback")}
              </button>
            )}
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400">{t("feedback_sample_note")}</p>
          {feedback && (
            <ul className="mt-2 space-y-2 text-xs">
              {feedback.map((f) => (
                <li key={f.id} className="rounded-lg border border-slate-200 p-2 dark:border-slate-800">
                  <p>{f.rating === "up" ? "👍" : "👎"} {f.language} · {f.at?.slice(0, 16)}</p>
                  {f.comment && <p className="font-medium">{f.comment}</p>}
                  <p className="mt-1 text-slate-600 dark:text-slate-400">Q: {f.question}</p>
                  <details><summary className="cursor-pointer">A</summary><p className="whitespace-pre-line">{f.answer}</p></details>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={`${card} overflow-x-auto`}>
          <h2 className="mb-2 text-sm font-semibold">{t("audit_log")}</h2>
          <table className="w-full text-xs">
            <tbody>
              {(audit ?? []).slice(0, 100).map((a, i) => (
                <tr key={i} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-1 py-1">{a.at?.slice(0, 16)}</td><td className="px-1">{a.actor}</td>
                  <td className="px-1">{a.actor_role}</td><td className="px-1">{a.action}</td><td className="px-1">{a.target}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </Shell>
  );
}
