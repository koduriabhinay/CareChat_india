"use client";

import { useState } from "react";
import type { Reminder } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const DUE_KEY = "carechat.reminders.shown";

/** In-app reminders: anything due today that hasn't been shown yet. */
export default function DueReminders({ items }: { items: Reminder[] }) {
  const { t } = useI18n();
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const hhmm = now.toTimeString().slice(0, 5);
  const due = items.filter((r) => {
    if (r.schedule.time > hhmm) return false;
    if (r.schedule.type === "daily") return true;
    if (r.schedule.type === "once") return r.schedule.date === today;
    return r.schedule.day === now.getDate();
  });
  const [shown, setShown] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(DUE_KEY) ?? "[]");
    } catch {
      return [];
    }
  });
  const fresh = due.filter((r) => !shown.includes(`${r.id}:${today}`));
  if (!fresh.length) return null;
  return (
    <section className="rounded-xl bg-teal-50 p-3 text-sm dark:bg-teal-950">
      <h2 className="font-semibold">{t("due_today")}</h2>
      <ul className="mt-1 list-disc ps-5">{fresh.map((r) => <li key={r.id}>{r.title} ({r.schedule.time})</li>)}</ul>
      <button className="mt-2 text-xs underline" onClick={() => {
        const next = [...shown, ...fresh.map((r) => `${r.id}:${today}`)].slice(-200);
        setShown(next);
        try {
          localStorage.setItem(DUE_KEY, JSON.stringify(next));
        } catch { /* ignore */ }
      }}>{t("mark_done")}</button>
    </section>
  );
}
