"use client";

import type { Row } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { StatusChip } from "@/components/ui";

export default function ValuesTable({ rows }: { rows: Row[] }) {
  const { t } = useI18n();
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-start text-xs text-slate-600 dark:border-slate-700 dark:text-slate-400">
            <th className="py-2 pe-2 text-start font-medium">{t("col_test")}</th>
            <th className="py-2 pe-2 text-start font-medium">{t("col_value")}</th>
            <th className="py-2 pe-2 text-start font-medium">{t("col_range")}</th>
            <th className="py-2 text-start font-medium">{t("col_status")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-b border-slate-100 dark:border-slate-800 ${r.critical ? "bg-red-50 dark:bg-red-950/40" : ""}`}>
              <td className="py-2 pe-2">{r.test_name}</td>
              <td className="py-2 pe-2 font-medium" dir="ltr">{r.value}{r.unit ? ` ${r.unit}` : ""}</td>
              <td className="py-2 pe-2" dir={r.reference_range ? "ltr" : undefined}>
                {r.reference_range ?? <span className="text-xs text-slate-500">{t("range_not_given")}</span>}
              </td>
              <td className="py-2"><StatusChip status={r.critical ? "critical" : r.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
