"use client";

import { useEffect, useRef, useState } from "react";
import MessageBubble, { type UiMessage } from "@/components/MessageBubble";
import ReportPanel from "@/components/ReportPanel";
import { getHealth, getLanguages, streamChat, type Language, type Report } from "@/lib/api";

const SUGGESTIONS_NO_REPORT = [
  "What does an HbA1c test measure?",
  "What is a normal cholesterol level?",
  "What does eGFR mean on a kidney test?",
];
const SUGGESTIONS_WITH_REPORT = [
  "Explain my results in simple words",
  "Which results are outside the normal range?",
  "What should I ask my doctor about these results?",
];

let nextId = 0;
const newId = () => `m${nextId++}`;

export default function Home() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [reportId, setReportId] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [disclaimer, setDisclaimer] = useState(
    "For education only, not medical advice. CareChat can't diagnose or treat. In an emergency, call 112.",
  );
  const [languages, setLanguages] = useState<Language[]>([{ code: "en", name: "English" }]);
  const [language, setLanguage] = useState("en");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getHealth()
      .then((h) => setDisclaimer(h.disclaimer))
      .catch(() => {});
    getLanguages()
      .then(setLanguages)
      .catch(() => {});
    try {
      const saved = localStorage.getItem("carechat-language");
      if (saved) setLanguage(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);

  function chooseLanguage(code: string) {
    setLanguage(code);
    try {
      localStorage.setItem("carechat-language", code);
    } catch {
      /* storage unavailable */
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function patch(id: string, update: (m: UiMessage) => UiMessage) {
    setMessages((prev) => prev.map((m) => (m.id === id ? update(m) : m)));
  }

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const userMsg: UiMessage = { id: newId(), role: "user", content };
    const reply: UiMessage = { id: newId(), role: "assistant", content: "", pending: true };
    // Fixed safety messages are not part of the model's conversation history.
    const history = [...messages, userMsg]
      .filter((m) => !m.alert && m.content)
      .map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, userMsg, reply]);
    setInput("");
    setBusy(true);
    try {
      await streamChat(history, reportId, language, (event) => {
        switch (event.type) {
          case "safety":
            patch(reply.id, (m) => ({
              ...m,
              content: event.message,
              alert: event.verdict,
              call: event.call,
              pending: false,
            }));
            break;
          case "sources":
            patch(reply.id, (m) => ({ ...m, sources: event.sources }));
            break;
          case "text":
            patch(reply.id, (m) => ({ ...m, content: m.content + event.text }));
            break;
          case "replace":
            patch(reply.id, (m) => ({ ...m, content: event.text, sources: [] }));
            break;
          case "error":
            patch(reply.id, (m) => ({ ...m, content: event.message, alert: "error" }));
            break;
          case "done":
            patch(reply.id, (m) => ({ ...m, pending: false }));
            break;
        }
      });
    } catch (e) {
      patch(reply.id, (m) => ({
        ...m,
        content: e instanceof Error ? e.message : "Something went wrong.",
        alert: "error",
        pending: false,
      }));
    } finally {
      patch(reply.id, (m) => ({ ...m, pending: false }));
      setBusy(false);
    }
  }

  const suggestions = report ? SUGGESTIONS_WITH_REPORT : SUGGESTIONS_NO_REPORT;

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col px-4">
      <header className="pt-5 pb-3">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-xl font-semibold text-teal-800 dark:text-teal-400">CareChat</h1>
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            Answer in
            <select
              value={language}
              onChange={(e) => chooseLanguage(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            >
              {languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="mt-1 rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-600 dark:bg-slate-900 dark:text-slate-400">
          {disclaimer}
        </p>
      </header>

      <main className="flex-1 space-y-4 overflow-y-auto pb-4">
        <ReportPanel
          reportId={reportId}
          report={report}
          disabled={busy}
          onLoaded={(id, r) => {
            setReportId(id);
            setReport(r);
          }}
          onCleared={() => {
            setReportId(null);
            setReport(null);
          }}
        />

        {messages.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-sm hover:border-teal-600 dark:border-slate-700 dark:bg-slate-900"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <div ref={bottomRef} />
      </main>

      <form
        className="flex gap-2 border-t border-slate-200 py-3 dark:border-slate-800"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          rows={1}
          maxLength={4000}
          dir="auto"
          placeholder={report ? "Ask about your report, in any language…" : "Ask a health question, in any language…"}
          className="flex-1 resize-none rounded-xl border border-slate-300 bg-white px-3 py-2 focus:border-teal-600 focus:outline-none dark:border-slate-700 dark:bg-slate-900"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-xl bg-teal-700 px-4 font-medium text-white hover:bg-teal-800 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
