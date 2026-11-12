import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "@/lib/api";

export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  alert?: "emergency" | "self_harm" | "unavailable" | "error";
  call?: string;
  pending?: boolean;
}

export default function MessageBubble({ message }: { message: UiMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-teal-700 px-4 py-2 text-white">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.alert === "emergency" || message.alert === "self_harm") {
    const number = message.call ?? "112";
    return (
      <div role="alert" className="rounded-xl border-2 border-red-600 bg-red-50 p-4 dark:bg-red-950/40">
        <p className="font-semibold text-red-800 dark:text-red-300">
          {message.alert === "self_harm" ? "You're not alone" : "This may be an emergency"}
        </p>
        <p className="mt-1 text-red-900 dark:text-red-200">{message.content}</p>
        <a
          href={`tel:${number}`}
          className="mt-3 inline-block rounded-lg bg-red-700 px-4 py-2 font-semibold text-white hover:bg-red-800"
        >
          Call {number}
        </a>
      </div>
    );
  }

  if (message.alert) {
    return (
      <div className="rounded-xl border border-amber-400 bg-amber-50 p-3 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
        {message.content}
      </div>
    );
  }

  return (
    <div className="max-w-[90%] rounded-2xl rounded-bl-sm bg-white px-4 py-2 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
      {message.content ? (
        <div className="prose-chat">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      ) : (
        <p className="animate-pulse text-slate-500">Thinking…</p>
      )}
      {!message.pending && message.sources && message.sources.length > 0 && (
        <div className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-500 dark:border-slate-800">
          <p className="font-medium">Sources</p>
          <ol className="mt-1 space-y-0.5">
            {message.sources.map((s) => (
              <li key={s.index}>
                [{s.index}]{" "}
                <a href={s.url} target="_blank" rel="noreferrer" className="underline hover:text-slate-800 dark:hover:text-slate-200">
                  {s.title}
                </a>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
