"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api, uploadReport, type Profile } from "@/lib/api";
import { useGuard } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import { BLUR_THRESHOLD, loadImage, rotate, sharpness, toJpeg } from "@/lib/image";
import { btnPrimary, btnSecondary, card, ErrorBox, input, PageTitle, Shell, Spinner } from "@/components/ui";

type Box = { x: number; y: number; w: number; h: number };

function BlackOut({ base, boxes, setBoxes }: { base: HTMLCanvasElement; boxes: Box[]; setBoxes: (b: Box[]) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<Box | null>(null);

  useEffect(() => {
    const c = ref.current!;
    c.width = base.width;
    c.height = base.height;
    const ctx = c.getContext("2d")!;
    ctx.drawImage(base, 0, 0);
    ctx.fillStyle = "#000";
    for (const b of [...boxes, ...(draft ? [draft] : [])]) ctx.fillRect(b.x, b.y, b.w, b.h);
  }, [base, boxes, draft]);

  const point = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return { x: ((e.clientX - r.left) * base.width) / r.width, y: ((e.clientY - r.top) * base.height) / r.height };
  };
  const box = (a: { x: number; y: number }, b: { x: number; y: number }): Box => ({
    x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y),
  });

  return (
    <canvas
      ref={ref}
      className="w-full touch-none rounded-lg border border-slate-300 dark:border-slate-700"
      onPointerDown={(e) => {
        (e.target as HTMLElement).setPointerCapture(e.pointerId);
        start.current = point(e);
      }}
      onPointerMove={(e) => start.current && setDraft(box(start.current, point(e)))}
      onPointerUp={(e) => {
        if (start.current) {
          const b = box(start.current, point(e));
          if (b.w > 4 && b.h > 4) setBoxes([...boxes, b]);
        }
        start.current = null;
        setDraft(null);
      }}
    />
  );
}

function Upload() {
  const { t, lang } = useI18n();
  const { allowed, me } = useGuard();
  const params = useSearchParams();
  const router = useRouter();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState(params.get("profile") ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [photo, setPhoto] = useState<HTMLCanvasElement | null>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [blurry, setBlurry] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!allowed) return;
    api<Profile[]>("/api/profiles").then((ps) => {
      setProfiles(ps);
      if (!profileId && ps.length) setProfileId(ps[0].id);
    }).catch((e) => setError(e.message));
  }, [allowed, profileId]);

  if (!allowed || !me) return <Shell><Spinner /></Shell>;

  async function choose(f: File | undefined) {
    setError(null);
    setPhoto(null);
    setBoxes([]);
    setBlurry(false);
    setFile(f ?? null);
    if (!f) return;
    if (f.type.startsWith("image/")) {
      try {
        const c = await loadImage(f);
        setPhoto(c);
        setBlurry(sharpness(c) < BLUR_THRESHOLD);
      } catch {
        setError(t("photo_unreadable"));
        setFile(null);
      }
    } else if (f.type !== "application/pdf") {
      setError(t("pdf_or_photo"));
      setFile(null);
    }
  }

  async function send() {
    if (!file || !profileId) return;
    setBusy(true);
    setError(null);
    try {
      let blob: Blob = file;
      let name = file.name;
      if (photo) {
        const out = document.createElement("canvas");
        out.width = photo.width;
        out.height = photo.height;
        const ctx = out.getContext("2d")!;
        ctx.drawImage(photo, 0, 0);
        ctx.fillStyle = "#000";
        for (const b of boxes) ctx.fillRect(b.x, b.y, b.w, b.h);
        blob = await toJpeg(out);
        name = "report.jpg";
      }
      const profile = profiles.find((p) => p.id === profileId);
      const report = await uploadReport(blob, name, profileId, profile?.language || lang);
      router.push(`/report/?id=${report.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <Shell>
      <PageTitle sub={t("upload_sub")}>{t("upload_report")}</PageTitle>
      <div className="space-y-4">
        <div className={`${card} space-y-3`}>
          <label className="block text-sm font-medium" htmlFor="who">{t("whose_report")}</label>
          <select id="who" className={input} value={profileId} onChange={(e) => setProfileId(e.target.value)}>
            {profiles.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
          </select>
          <div className="flex flex-wrap gap-2">
            <label className={`${btnPrimary} cursor-pointer`}>
              {t("take_photo")}
              <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => choose(e.target.files?.[0])} />
            </label>
            <label className={`${btnSecondary} cursor-pointer`}>
              {t("choose_file")}
              <input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => choose(e.target.files?.[0])} />
            </label>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400">{t("upload_privacy_note")}</p>
        </div>

        {file && !photo && (
          <div className={card}>
            <p className="text-sm font-medium">{file.name}</p>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{t("pdf_redaction_note")}</p>
          </div>
        )}

        {photo && (
          <div className={`${card} space-y-3`}>
            <h2 className="font-semibold">{t("black_out_title")}</h2>
            <p className="text-sm">{t("black_out_help")}</p>
            {blurry && (
              <p role="alert" className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
                {t("photo_blurry")}
              </p>
            )}
            <BlackOut base={photo} boxes={boxes} setBoxes={setBoxes} />
            <div className="flex flex-wrap gap-2">
              <button className={btnSecondary} onClick={() => setBoxes(boxes.slice(0, -1))} disabled={!boxes.length}>{t("undo")}</button>
              <button className={btnSecondary} onClick={() => { setPhoto(rotate(photo)); setBoxes([]); }}>{t("rotate")}</button>
            </div>
            {boxes.length === 0 && <p className="text-xs text-amber-800 dark:text-amber-300">{t("no_black_out_yet")}</p>}
          </div>
        )}

        <ErrorBox message={error} />
        <button className={`${btnPrimary} w-full`} disabled={!file || !profileId || busy} onClick={send}>
          {busy ? t("sending") : t("read_my_report")}
        </button>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          {t("reports_left_today", { left: Math.max(0, me.daily_caps.reports - me.usage_today.reports) })}
        </p>
      </div>
    </Shell>
  );
}

export default function Page() {
  return <Suspense><Upload /></Suspense>;
}
