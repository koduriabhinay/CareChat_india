"use client";

import { useRef, useState } from "react";
import { deleteReport, uploadReport, type Flag, type Report } from "@/lib/api";

const FLAG_STYLES: Record<Flag, { label: string; className: string }> = {
  normal: { label: "Normal", className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300" },
  low: { label: "Low", className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" },
  high: { label: "High", className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" },
  abnormal: { label: "Abnormal", className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" },
  critical: { label: "Critical", className: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300" },
  not_flagged: { label: "No flag", className: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400" },
};

interface Props {
  reportId: string | null;
  report: Report | null;
  onLoaded: (reportId: string, report: Report) => void;
  onCleared: () => void;
  disabled: boolean;
}

export default function ReportPanel({ reportId, report, onLoaded, onCleared, disabled }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const { report_id, report } = await uploadReport(file);
      onLoaded(report_id, report);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleRemove() {
    if (!reportId) return;
    setBusy(true);
    try {
      await deleteReport(reportId);
      onCleared();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't remove the report.");
    } finally {
      setBusy(false);
    }
  }

  if (!report) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
        <p className="text-sm font-medium">Have a lab report?</p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Upload the PDF and CareChat will explain each result in plain language.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={busy || disabled}
            className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-800 disabled:opacity-50"
          >
            {busy ? "Reading report…" : "Upload PDF"}
          </button>
          <span className="text-xs text-slate-500">PDF up to 10 MB. Synthetic or your own report.</span>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        {error && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{error}</p>}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">{report.report_type ?? "Your report"}</p>
          {report.report_date && <p className="text-xs text-slate-500">{report.report_date}</p>}
        </div>
        <button
          type="button"
          onClick={handleRemove}
          disabled={busy}
          className="text-xs text-slate-500 underline hover:text-slate-800 dark:hover:text-slate-200"
        >
          Remove report
        </button>
      </div>
      {report.results.length > 0 && (
        <div className="mt-3 max-h-64 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <th className="py-1 pr-2 font-medium">Test</th>
                <th className="py-1 pr-2 font-medium">Result</th>
                <th className="py-1 pr-2 font-medium">Range on report</th>
                <th className="py-1 font-medium">Flag</th>
              </tr>
            </thead>
            <tbody>
              {report.results.map((r, i) => (
                <tr key={`${r.test_name}-${i}`} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1.5 pr-2">{r.test_name}</td>
                  <td className="py-1.5 pr-2 font-medium">
                    {r.value} {r.unit}
                  </td>
                  <td className="py-1.5 pr-2 text-slate-600 dark:text-slate-400">{r.reference_range ?? "–"}</td>
                  <td className="py-1.5">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${FLAG_STYLES[r.flag].className}`}>
                      {FLAG_STYLES[r.flag].label}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {report.other_findings.length > 0 && (
        <ul className="mt-3 list-disc pl-5 text-sm text-slate-700 dark:text-slate-300">
          {report.other_findings.map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      )}
      {error && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{error}</p>}
    </div>
  );
}
