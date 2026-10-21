"use client";

import Script from "next/script";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken } from "@/lib/api";
import { useApp } from "@/lib/app";
import { useI18n } from "@/lib/i18n";
import { btnPrimary, btnSecondary, card, ErrorBox, input, PageTitle, Shell } from "@/components/ui";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (o: { client_id: string; callback: (r: { credential: string }) => void }) => void;
          renderButton: (el: HTMLElement, o: Record<string, unknown>) => void;
        };
      };
    };
  }
}

export default function SignIn() {
  const { t, lang } = useI18n();
  const { health, me, signIn } = useApp();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [devCode, setDevCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gisLoaded, setGisLoaded] = useState(false);
  const googleRef = useRef<HTMLDivElement>(null);

  // A guest who signs in keeps what they added.
  const guestToken = me?.guest ? getToken() : null;

  const finish = useCallback(
    async (token: string) => {
      const m = await signIn(token);
      router.push(m?.needs_consent ? "/consent/" : "/home/");
    },
    [signIn, router],
  );

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const clientId = health?.google_client_id;
    if (!clientId || !gisLoaded || !window.google || !googleRef.current) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (r) =>
        run(async () => {
          const out = await api<{ token: string }>("/api/auth/google", "POST", {
            id_token: r.credential, guest_token: guestToken, language: lang,
          });
          await finish(out.token);
        }),
    });
    window.google.accounts.id.renderButton(googleRef.current, { theme: "outline", size: "large", width: 300, locale: lang });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [health?.google_client_id, gisLoaded, lang]);

  return (
    <Shell>
      {health?.google_client_id && (
        <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" onLoad={() => setGisLoaded(true)} />
      )}
      <PageTitle sub={t("signin_sub")}>{t("sign_in_or_create")}</PageTitle>
      <div className="mx-auto max-w-md space-y-4">
        {health?.google_client_id && (
          <div className={`${card} flex justify-center`}>
            <div ref={googleRef} />
          </div>
        )}
        <form
          className={`${card} space-y-3`}
          onSubmit={(e) => {
            e.preventDefault();
            if (!sent) {
              run(async () => {
                const out = await api<{ sent: boolean; dev_code?: string }>("/api/auth/email/start", "POST", { email });
                setSent(true);
                setDevCode(out.dev_code ?? null);
              });
            } else {
              run(async () => {
                const out = await api<{ token: string }>("/api/auth/email/verify", "POST", {
                  email, code, guest_token: guestToken, language: lang,
                });
                await finish(out.token);
              });
            }
          }}
        >
          <label className="block text-sm font-medium" htmlFor="email">{t("email")}</label>
          <input id="email" type="email" required autoComplete="email" className={input} value={email}
                 onChange={(e) => setEmail(e.target.value)} disabled={sent} />
          {sent && (
            <>
              <label className="block text-sm font-medium" htmlFor="code">{t("enter_code")}</label>
              <input id="code" inputMode="numeric" autoComplete="one-time-code" required className={input} value={code}
                     onChange={(e) => setCode(e.target.value.trim())} />
              {devCode && <p className="text-xs text-amber-700">{t("dev_code_note", { code: devCode })}</p>}
            </>
          )}
          <button className={`${btnPrimary} w-full`} disabled={busy}>
            {sent ? t("sign_in") : t("send_code")}
          </button>
          {sent && (
            <button type="button" className="text-sm underline" onClick={() => { setSent(false); setCode(""); }}>
              {t("use_other_email")}
            </button>
          )}
        </form>
        {health?.dev_auth && (
          <button
            className={`${btnSecondary} w-full`}
            disabled={busy || !email}
            onClick={() =>
              run(async () => {
                const out = await api<{ token: string }>("/api/auth/dev", "POST", { email, guest_token: guestToken, language: lang });
                await finish(out.token);
              })
            }
          >
            {t("dev_sign_in")}
          </button>
        )}
        <ErrorBox message={error} />
      </div>
    </Shell>
  );
}
