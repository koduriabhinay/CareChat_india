"use client";

import { useEffect, useState } from "react";
import { api, type Profile, type Reminder } from "@/lib/api";
import { useGuard } from "@/lib/app";
import { useI18n, type TKey } from "@/lib/i18n";
import DueReminders from "@/components/DueReminders";
import { btnPrimary, card, ErrorBox, input, PageTitle, Shell, Spinner } from "@/components/ui";

export default function Reminders() {
  const { t } = useI18n();
  const { me, allowed } = useGuard({ consent: true, member: true });
  const [items, setItems] = useState<Reminder[] | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [form, setForm] = useState({ title: "", kind: "medicine", profile_id: "", type: "daily", time: "09:00", date: "", day: "1", email: true });
  const [error, setError] = useState<string | null>(null);

  const load = () => api<Reminder[]>("/api/reminders").then(setItems).catch((e) => setError(e.message));
  useEffect(() => {
    if (!allowed) return;
    load();
    api<Profile[]>("/api/profiles").then(setProfiles).catch(() => {});
  }, [allowed]);

  if (!allowed || !me) return <Shell><Spinner /></Shell>;

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/api/reminders", "POST", {
        title: form.title, kind: form.kind, profile_id: form.profile_id || null, email: form.email,
        schedule: { type: form.type, time: form.time, date: form.type === "once" ? form.date : null, day: form.type === "monthly" ? Number(form.day) : null },
      });
      setForm({ ...form, title: "" });
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(id: string) {
    await api(`/api/reminders/${id}`, "DELETE").catch((e) => setError(e.message));
    load();
  }

  const when = (r: Reminder) =>
    r.schedule.type === "daily" ? t("every_day_at", { time: r.schedule.time })
      : r.schedule.type === "monthly" ? t("every_month_on", { day: r.schedule.day ?? 1, time: r.schedule.time })
        : t("once_on", { date: r.schedule.date ?? "", time: r.schedule.time });
  const label = "mb-1 block text-sm font-medium";
  return (
    <Shell>
      <PageTitle sub={t("reminders_sub")}>{t("nav_reminders")}</PageTitle>
      <div className="space-y-4">
        <DueReminders items={items ?? []} />
        <section className={card}>
          {items === null ? <Spinner /> : items.length === 0 ? (
            <p className="text-sm text-slate-600 dark:text-slate-400">{t("no_reminders")}</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {items.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span>
                    <span className="font-medium">{r.title}</span>
                    <span className="block text-xs text-slate-600 dark:text-slate-400">
                      {when(r)}{r.profile_id && ` · ${profiles.find((p) => p.id === r.profile_id)?.display_name ?? ""}`}{r.email && ` · ${t("by_email")}`}
                    </span>
                  </span>
                  <button className="text-xs text-red-700 underline" onClick={() => remove(r.id)}>{t("delete")}</button>
                </li>
              ))}
            </ul>
          )}
        </section>
        <form onSubmit={add} className={`${card} space-y-3`}>
          <h2 className="font-semibold">{t("add_reminder")}</h2>
          <div>
            <label className={label} htmlFor="title">{t("reminder_what")}</label>
            <input id="title" required maxLength={120} className={input} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                   placeholder={t("reminder_placeholder")} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={label} htmlFor="kind">{t("reminder_kind")}</label>
              <select id="kind" className={input} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {["medicine", "test", "other"].map((k) => <option key={k} value={k}>{t(`kind_${k}` as TKey)}</option>)}
              </select>
            </div>
            <div>
              <label className={label} htmlFor="rp">{t("for_whom")}</label>
              <select id="rp" className={input} value={form.profile_id} onChange={(e) => setForm({ ...form, profile_id: e.target.value })}>
                <option value="">-</option>
                {profiles.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
              </select>
            </div>
            <div>
              <label className={label} htmlFor="type">{t("how_often")}</label>
              <select id="type" className={input} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                <option value="daily">{t("daily")}</option>
                <option value="monthly">{t("monthly")}</option>
                <option value="once">{t("once")}</option>
              </select>
            </div>
            <div>
              <label className={label} htmlFor="time">{t("time_ist")}</label>
              <input id="time" type="time" required className={input} value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} />
            </div>
            {form.type === "once" && (
              <div>
                <label className={label} htmlFor="date">{t("date")}</label>
                <input id="date" type="date" required className={input} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
              </div>
            )}
            {form.type === "monthly" && (
              <div>
                <label className={label} htmlFor="day">{t("day_of_month")}</label>
                <input id="day" type="number" min={1} max={28} className={input} value={form.day} onChange={(e) => setForm({ ...form, day: e.target.value })} />
              </div>
            )}
          </div>
          {me.email ? (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-5 w-5 accent-teal-700" checked={form.email} onChange={(e) => setForm({ ...form, email: e.target.checked })} />
              {t("email_me", { email: me.email })}
            </label>
          ) : (
            <p className="text-xs text-slate-600 dark:text-slate-400">{t("reminders_in_app_only")}</p>
          )}
          <p className="text-xs text-slate-600 dark:text-slate-400">{t("reminder_safety_note")}</p>
          <ErrorBox message={error} />
          <button className={btnPrimary}>{t("add_reminder")}</button>
        </form>
      </div>
    </Shell>
  );
}

