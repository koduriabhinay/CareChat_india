export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Flag = "normal" | "low" | "high" | "abnormal" | "critical" | "not_flagged";

export interface LabResult {
  test_name: string;
  value: string;
  unit: string | null;
  reference_range: string | null;
  flag: Flag;
}

export interface Report {
  is_medical_report: boolean;
  report_type: string | null;
  report_date: string | null;
  results: LabResult[];
  other_findings: string[];
}

export interface Source {
  index: number;
  title: string;
  url: string;
}

export type ChatEvent =
  | { type: "safety"; verdict: "emergency" | "self_harm" | "unavailable"; message: string; call: string }
  | { type: "sources"; sources: Source[] }
  | { type: "text"; text: string }
  | { type: "replace"; text: string }
  | { type: "error"; message: string }
  | { type: "done" };

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* fall through */
  }
  return `Request failed (${res.status}).`;
}

export interface Health {
  disclaimer: string;
  region: string;
  emergency_number: string;
  crisis_number: string;
}

export async function getHealth(): Promise<Health> {
  const res = await fetch(`${API_URL}/api/health`);
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export interface Language {
  code: string;
  name: string;
}

export async function getLanguages(): Promise<Language[]> {
  const res = await fetch(`${API_URL}/api/languages`);
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function uploadReport(file: File): Promise<{ report_id: string; report: Report }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/reports`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json();
}

export async function deleteReport(reportId: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/reports/${reportId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) throw new Error(await errorDetail(res));
}

/** Sends the conversation and calls onEvent for each server-sent event. */
export async function streamChat(
  messages: { role: "user" | "assistant"; content: string }[],
  reportId: string | null,
  language: string,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, report_id: reportId, language }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(await errorDetail(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const chunk = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as ChatEvent);
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
