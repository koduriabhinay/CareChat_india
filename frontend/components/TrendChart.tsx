"use client";

import { useState } from "react";
import type { Series } from "@/lib/api";

function parseRange(text: string | null): [number | null, number | null] | null {
  if (!text) return null;
  const nums = (text.match(/\d+(?:\.\d+)?/g) ?? []).map(Number);
  if (nums.length >= 2 && /[-–]|to/.test(text)) return [nums[0], nums[1]];
  if (nums.length === 1 && /</.test(text)) return [null, nums[0]];
  if (nums.length === 1 && />/.test(text)) return [nums[0], null];
  return null;
}

/** One test over time: a 2px line, 8px points, the report's own normal range as a pale band. */
export default function TrendChart({ series }: { series: Series }) {
  const [hover, setHover] = useState<number | null>(null);
  const pts = series.points;
  const W = 600, H = 200, L = 44, R = 16, T = 14, B = 30;
  const range = parseRange(pts[pts.length - 1]?.reference_range ?? null);
  const values = pts.map((p) => p.value);
  if (range?.[0] != null) values.push(range[0]);
  if (range?.[1] != null) values.push(range[1]);
  let lo = Math.min(...values), hi = Math.max(...values);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12;
  lo -= pad; hi += pad;
  const x = (i: number) => (pts.length === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (pts.length - 1));
  const y = (v: number) => T + ((hi - v) * (H - T - B)) / (hi - lo);
  const ticks = [lo + pad, (lo + hi) / 2, hi - pad];
  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1));
  const active = hover ?? pts.length - 1;

  return (
    <figure className="relative" dir="ltr">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img"
           aria-label={`${series.test_name}: ${pts.map((p) => `${p.date} ${p.value} ${series.unit}`).join(", ")}`}>
        {range && (
          <rect x={L} width={W - L - R}
                y={y(range[1] ?? hi)} height={y(range[0] ?? lo) - y(range[1] ?? hi)}
                className="fill-emerald-500/10" />
        )}
        {ticks.map((v, i) => (
          <g key={i}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="stroke-slate-200 dark:stroke-slate-800" strokeWidth={1} />
            <text x={L - 6} y={y(v) + 4} textAnchor="end" className="fill-slate-500 text-[11px]">{fmt(v)}</text>
          </g>
        ))}
        {pts.map((p, i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor="middle" className="fill-slate-500 text-[11px]">{p.date}</text>
        ))}
        <polyline fill="none" strokeWidth={2} strokeLinejoin="round" className="stroke-teal-700 dark:stroke-teal-400"
                  points={pts.map((p, i) => `${x(i)},${y(p.value)}`).join(" ")} />
        {pts.map((p, i) => (
          <g key={i}>
            <circle cx={x(i)} cy={y(p.value)} r={i === active ? 6 : 4} strokeWidth={2}
                    className={`stroke-white dark:stroke-slate-900 ${p.status === "normal" ? "fill-teal-700 dark:fill-teal-400" : "fill-amber-600"}`} />
            <rect x={x(i) - 20} y={T} width={40} height={H - T - B} fill="transparent"
                  onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => setHover(i)} />
          </g>
        ))}
        <text x={Math.min(Math.max(x(active), L + 30), W - R - 30)} y={Math.max(y(pts[active].value) - 12, 12)}
              textAnchor="middle" className="fill-slate-900 text-[12px] font-semibold dark:fill-slate-100">
          {pts[active].value} {series.unit}
        </text>
      </svg>
    </figure>
  );
}
