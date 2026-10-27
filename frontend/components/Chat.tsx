"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, streamChat, type ChatMessage, type Source } from "@/lib/api";
import { SPEECH_LOCALE, useI18n } from "@/lib/i18n";
import { btnPrimary, EmergencyBox, ErrorBox, input, SpeakButton } from "@/components/ui";

interface Turn {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  safety?: { message: string; call: string };
  error?: string;
  streaming?: boolean;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function getRecognition(): any | null {
  if (typeof window === "undefined") return null;
  const R = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  return R ? new R() : null;
}

function Feedback({ question, answer, lang }: { question: string; answer: string; lang: string }) {
  const { t } = useI18n();
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  const send = async (r: "up" | "down", c?: string) => {
    try {
      await api("/api/feedback", "POST", { rating: r, comment: c || null, question, answer, language: lang });
    } catch {
      /* feedback is best effort */
    }
  };
  if (sent) return <p className="text-xs text-slate-500">{t("thanks_feedback")}</p>;
  return (
    <div className="mt-1 text-xs">
      <span className="text-slate-500">{t("was_this_helpful")}</span>{" "}
      <button aria-label={t("helpful")} className={`px-1 ${rating === "up" ? "opacity-100" : "opacity-60"}`}
              onClick={() => { setRating("up"); setSent(true); send("up"); }}>👍</button>
      <button aria-label={t("not_helpful")} className={`px-1 ${rating === "down" ? "opacity-100" : "opacity-60"}`}
              onClick={() => setRating("down")}>👎</button>
      {rating === "down" && (
        <div className="mt-1 flex gap-2">
          <input className={`${input} py-1 text-sm`} placeholder={t("what_was_wrong")} value={comment}
                 maxLength={1000} onChange={(e) => setComment(e.target.value)} />
          <button className="rounded-lg border px-2" onClick={() => { setSent(true); send("down", comment); }}>{t("send")}</button>
        </div>
      )}
    </div>
  );
}

export default function Chat({
  reportId, profileId, historyEnabled, suggestions = [],
}: { reportId?: string | null; profileId?: string | null; historyEnabled: boolean; suggestions?: string[] }) {
  const { t, lang } = useI18n();
  const storeKey = `carechat.chat.${reportId ?? profileId ?? "general"}`;
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [canListen, setCanListen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const recRef = useRef<any>(null);

  useEffect(() => {
    setCanListen(!!getRecognition());
  }, []);

  useEffect(() => {
    if (historyEnabled && reportId) {
      api<ChatMessage[]>(`/api/reports/${reportId}/messages`).then((m) => setTurns(m)).catch(() => {});
      return;
    }
    try {
      const saved = sessionStorage.getItem(storeKey);
      if (saved) setTurns(JSON.parse(saved));
    } catch {
      /* ignore */
    }
  }, [historyEnabled, reportId, storeKey]);

  useEffect(() => {
    if (busy) return;
    try {
      // Without saved history the conversation lives only in this browser tab.
      sessionStorage.setItem(storeKey, JSON.stringify(turns.slice(-30)));
    } catch {
      /* ignore */
    }
  }, [turns, busy, storeKey]);

  // Newer browsers make scrollIntoView return a Promise, so keep it out of the return value.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns]);

  async function ask(question: string) {
    question = question.trim();
    if (!question || busy) return;
    setText("");
    setError(null);
    setBusy(true);
    const history: ChatMessage[] = turns
      .filter((x) => !x.safety && !x.error && x.content)
      .map((x) => ({ role: x.role, content: x.content }));
    const next: Turn[] = [...turns, { role: "user", content: question }, { role: "assistant", content: "", streaming: true }];
    setTurns(next);
    const update = (fn: (a: Turn) => Turn) =>
      setTurns((cur) => [...cur.slice(0, -1), fn(cur[cur.length - 1])]);
    try {
      for await (const ev of streamChat({
        messages: [...history, { role: "user", content: question }],
        report_id: reportId ?? null, profile_id: profileId ?? null, language: lang,
      })) {
        if (ev.type === "text") update((a) => ({ ...a, content: a.content + ev.text }));
        else if (ev.type === "replace") update((a) => ({ ...a, content: ev.text }));
        else if (ev.type === "sources") update((a) => ({ ...a, sources: ev.sources }));
        else if (ev.type === "safety") update((a) => ({ ...a, safety: { message: ev.message, call: ev.call } }));
        else if (ev.type === "error") update((a) => ({ ...a, error: ev.message }));
      }
    } catch (e) {
      setTurns((cur) => cur.slice(0, -2));
      setText(question);
      setError((e as Error).message);
    } finally {
      update((a) => ({ ...a, streaming: false }));
      setBusy(false);
    }
  }

  function listen() {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const rec = getRecognition();
    if (!rec) return;
    rec.lang = SPEECH_LOCALE[lang] ?? "en-IN";
    rec.interimResults = true;
    rec.onresult = (e: any) => setText(Array.from(e.results).map((r: any) => r[0].transcript).join(" "));
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  }

  return (
    <div className="space-y-3">
      {turns.length === 0 && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button key={s} onClick={() => ask(s)} className="rounded-full border border-teal-700 px-3 py-1 text-sm text-teal-800 dark:text-teal-300">
              {s}
            </button>
          ))}
        </div>
      )}
      {turns.map((turn, i) =>
        turn.role === "user" ? (
          <div key={i} className="ms-auto max-w-[85%] rounded-2xl rounded-ee-sm bg-teal-700 px-3 py-2 text-white">
            {turn.content}
          </div>
        ) : turn.safety ? (
          <EmergencyBox key={i} message={turn.safety.message} call={turn.safety.call} />
        ) : (
          <div key={i} className="max-w-[95%] rounded-2xl rounded-es-sm bg-white px-3 py-2 shadow-sm dark:bg-slate-900">
            {turn.error ? (
              <p className="text-sm text-red-700">{turn.error}</p>
            ) : turn.content ? (
              <div className="prose-chat text-[15px] leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
              </div>
            ) : (
              <span className="inline-block h-4 w-4 animate-pulse rounded-full bg-slate-300" />
            )}
            {turn.sources && turn.sources.length > 0 && !turn.streaming && (
              <ol className="mt-2 space-y-0.5 border-t border-slate-200 pt-2 text-xs dark:border-slate-700">
                {turn.sources.map((s) => (
                  <li key={s.index}>
                    [{s.index}]{" "}
                    <a href={s.url} target="_blank" rel="noreferrer" className="underline">{s.title}</a>
                  </li>
                ))}
              </ol>
            )}
            {!turn.streaming && turn.content && !turn.error && (
              <div className="mt-1 flex flex-wrap items-center gap-3">
                <SpeakButton text={turn.content} lang={lang} />
                <Feedback question={turns[i - 1]?.content ?? ""} answer={turn.content} lang={lang} />
              </div>
            )}
          </div>
        ),
      )}
      <div ref={endRef} />
      <ErrorBox message={error} />
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <textarea
          rows={1}
          maxLength={4000}
          className={`${input} min-h-[44px] resize-none`}
          placeholder={t("ask_placeholder")}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(text);
            }
          }}
        />
        {canListen && (
          <button type="button" onClick={listen} aria-label={t("speak_question")}
                  className={`rounded-lg border px-3 ${listening ? "border-red-600 text-red-700" : "border-slate-300 dark:border-slate-700"}`}>
            {listening ? "■" : "🎤"}
          </button>
        )}
        <button className={btnPrimary} disabled={busy || !text.trim()}>{t("send")}</button>
      </form>
    </div>
  );
}
