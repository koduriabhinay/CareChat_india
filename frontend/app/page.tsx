"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app";
import { useI18n, type TKey } from "@/lib/i18n";
import { btnPrimary, btnSecondary, ErrorBox, LanguageSelect, Shell, Spinner } from "@/components/ui";

const SCREENS: { title: TKey; points: TKey[] }[] = [
  { title: "onb1_title", points: ["onb1_p1", "onb1_p2"] },
  { title: "onb2_title", points: ["onb2_p1", "onb2_p2", "onb2_p3"] },
  { title: "onb3_title", points: ["onb3_p1", "onb3_p2", "onb3_p3"] },
  { title: "onb4_title", points: ["onb4_p1", "onb4_p2", "onb4_p3"] },
];

export default function Welcome() {
  const { t, lang } = useI18n();
  const { me, loading, signIn, health } = useApp();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && me) router.replace(me.needs_consent ? "/consent/" : "/home/");
  }, [loading, me, router]);

  async function tryAsGuest() {
    setBusy(true);
    setError(null);
    try {
      const { token } = await api<{ token: string }>("/api/auth/guest", "POST", { language: lang });
      await signIn(token);
      router.push("/consent/");
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  if (loading || me) {
    return (
      <Shell>
        <Spinner />
      </Shell>
    );
  }

  const screen = SCREENS[step];
  const last = step === SCREENS.length - 1;
  return (
    <Shell>
      <section className="mx-auto max-w-md py-4">
        {step === 0 && (
          <div className="mb-6">
            <label className="mb-1 block text-sm font-medium">{t("choose_language")}</label>
            <LanguageSelect className="w-full py-2.5 text-base" />
          </div>
        )}
        <h1 className="text-2xl font-semibold leading-snug">{t(screen.title)}</h1>
        <ul className="mt-4 space-y-3">
          {screen.points.map((p) => (
            <li key={p} className="flex gap-3 text-base">
              <span aria-hidden className="mt-1 h-2 w-2 shrink-0 rounded-full bg-teal-600" />
              <span>{t(p, { number: health?.emergency_number ?? "112", crisis: health?.crisis_number ?? "14416" })}</span>
            </li>
          ))}
        </ul>
        <div className="mt-6 flex items-center justify-center gap-2" aria-hidden>
          {SCREENS.map((_, i) => (
            <span key={i} className={`h-2 w-2 rounded-full ${i === step ? "bg-teal-700" : "bg-slate-300 dark:bg-slate-700"}`} />
          ))}
        </div>
        <div className="mt-6 flex flex-col gap-3">
          {!last && (
            <>
              <button className={btnPrimary} onClick={() => setStep(step + 1)}>
                {t("next")}
              </button>
              <button className="text-sm underline" onClick={() => setStep(SCREENS.length - 1)}>
                {t("skip")}
              </button>
            </>
          )}
          {last && (
            <>
              <Link href="/signin/" className={btnPrimary}>
                {t("sign_in_or_create")}
              </Link>
              <button className={btnSecondary} onClick={tryAsGuest} disabled={busy}>
                {t("try_as_guest")}
              </button>
              <p className="text-center text-xs text-slate-600 dark:text-slate-400">{t("guest_note")}</p>
              <ErrorBox message={error} />
            </>
          )}
          {step > 0 && (
            <button className="text-sm underline" onClick={() => setStep(step - 1)}>
              {t("back")}
            </button>
          )}
        </div>
      </section>
    </Shell>
  );
}
