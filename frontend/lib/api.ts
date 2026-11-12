// Talks to the CareChat API. The session token lives in localStorage.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const TOKEN_KEY = "carechat.token";

export type Status = "low" | "normal" | "high" | "abnormal" | "critical" | "no_range" | "see_report";
export type Role = "guest" | "patient" | "doctor" | "admin";

export interface Health {
  disclaimer: string;
  region: string;
  emergency_number: string;
  ambulance_number: string;
  crisis_number: string;
  crisis_line_name: string;
  google_client_id: string | null;
  dev_auth: boolean;
  notice_version: string;
}

export interface Me {
  id: string;
  role: Role;
  guest: boolean;
  email: string | null;
  ui_language: string;
  history_enabled: boolean;
  reminder_emails: boolean;
  consents: Record<string, boolean>;
  needs_consent: boolean;
  notice_version: string;
  usage_today: { reports: number; questions: number };
  daily_caps: { reports: number; questions: number };
}

export interface Profile {
  id: string;
  display_name: string;
  relation: string;
  language: string | null;
  name_on_reports: string | null;
  birth_year: number | null;
  sex: "male" | "female" | "other" | null;
  height_cm: number | null;
  weight_kg: number | null;
  weights: { date: string; kg: number }[];
  conditions: string[];
  medicines: string[];
  pregnant: boolean;
  diet_type: string | null;
  diet_notes: string | null;
  is_self: boolean;
  age: number | null;
  bmi: { value: number; band: string } | null;
  health_form_due: boolean;
  health_updated_at: string | null;
  report_count?: number;
  latest_report?: {
    id: string;
    report_type: string | null;
    report_date: string | null;
    flagged: number;
    critical: boolean;
    created_at: string;
  } | null;
}

export interface Row {
  test_name: string;
  value: string;
  unit: string | null;
  reference_range: string | null;
  status: Status;
  critical: boolean;
  key: string;
}

export interface Source {
  index: number;
  title: string;
  url: string;
}

export interface Summary {
  overall: string;
  flagged: { test_name: string; meaning: string }[];
  doctor_questions: string[];
  general_tips: string[];
}

export interface ReportOut {
  id: string;
  profile_id: string;
  status: "reading" | "ready" | "failed";
  source: "pdf" | "image";
  error: string | null;
  error_code: string | null;
  report_type: string | null;
  report_date: string | null;
  created_at: string;
  expires_at: string | null;
  critical: boolean;
  language: string | null;
  flagged: number;
  rows?: Row[];
  summary?: Summary | null;
  sources?: Source[];
  other_findings?: string[];
  mismatch?: string[];
  patient_age?: string | null;
  patient_sex?: string | null;
  suggested_profile_id?: string | null;
  critical_message?: string | null;
}

export interface TrendPoint {
  report_id: string;
  date: string;
  value: number;
  status: Status;
  reference_range: string | null;
}

export interface Series {
  key: string;
  test_name: string;
  unit: string;
  points: TrendPoint[];
  change: { from: number; to: number; difference: number; percent: number | null; direction: string; big: boolean } | null;
}

export interface Trends {
  timeline: { id: string; date: string; report_type: string | null; flagged: number }[];
  series: Series[];
  since_last_visit: Series[];
  history_enabled: boolean;
}

export interface Reminder {
  id: string;
  profile_id: string | null;
  title: string;
  kind: "medicine" | "test" | "other";
  schedule: { type: "daily" | "once" | "monthly"; time: string; date?: string | null; day?: number | null };
  email: boolean;
  active: boolean;
}

export type ChatEvent =
  | { type: "safety"; verdict: "emergency" | "self_harm" | "unavailable"; message: string; call: string }
  | { type: "sources"; sources: Source[] }
  | { type: "text"; text: string }
  | { type: "replace"; text: string }
  | { type: "error"; message: string }
  | { type: "done" };

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// --- token -------------------------------------------------------------------

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode */
  }
}

// --- requests ----------------------------------------------------------------

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return String(body.detail[0].msg).replace(/^Value error, /, "");
  } catch {
    /* not JSON */
  }
  return `Something went wrong (${res.status}). Please try again.`;
}

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  const token = getToken();
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function raw(path: string, init: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Can't reach CareChat. Check your internet connection and try again.");
  }
  if (res.status === 401 && getToken()) {
    setToken(null);
    if (typeof window !== "undefined") window.location.href = `${BASE_PATH}/`;
  }
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res;
}

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await raw(path, {
    method,
    headers: headers(body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return res.json();
}

export async function uploadReport(file: Blob, filename: string, profileId: string, language: string): Promise<ReportOut> {
  const form = new FormData();
  form.append("file", file, filename);
  form.append("profile_id", profileId);
  form.append("language", language);
  const res = await raw("/api/reports", { method: "POST", headers: headers(false), body: form });
  return res.json();
}

export async function downloadCsv(profileId?: string) {
  const q = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : "";
  const res = await raw(`/api/export.csv${q}`, { headers: headers(false) });
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "carechat-results.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export async function* streamChat(body: {
  messages: ChatMessage[];
  report_id?: string | null;
  profile_id?: string | null;
  language?: string | null;
}): AsyncGenerator<ChatEvent> {
  const res = await raw("/api/chat", { method: "POST", headers: headers(), body: JSON.stringify(body) });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) yield JSON.parse(line.slice(6)) as ChatEvent;
      }
    }
  }
}
