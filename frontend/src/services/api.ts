// Client for the FastAPI backend (proxied by Vite from /api to http://127.0.0.1:8000).
export type Verification = { status: 'OFFICIAL' | 'THIRD_PARTY' | 'UNVERIFIED'; label: string; reason: string };
export type Freshness = { state: 'FRESH' | 'STALE' | 'NEVER_CHECKED'; stale: boolean; checked_hours_ago: number | null; changed_hours_ago: number | null; stale_after_hours: number };
export type ApiSource = {
  id: number; college_id: string; source_name: string; source_url: string; source_type: string; authority_level: string;
  status: string; last_checked: string | null; last_changed: string | null; last_error: string | null; is_demo: boolean;
  verification: Verification; freshness: Freshness; chunks: number | null;
};
export type Citation = {
  index: number; source_id: number; source_name: string; source_url: string; authority_level: string; source_type: string;
  college_id: string; document_title: string; snippet: string; score: number; is_demo: boolean;
  verification: Verification; freshness: Freshness; last_checked: string | null; last_changed: string | null;
};
export type AskResult = {
  answer: string; sources: Citation[]; mode: 'gemini' | 'groq' | 'extractive' | 'none'; grounded: boolean; intent: string;
  provider?: 'gemini' | 'groq' | 'demo' | 'none'; model?: string | null;
  answer_label?: string; third_party_note?: string; official_links?: { title: string; url: string }[];
  live_available?: { college_id?: string; colleges?: string[]; domain: string; topic: string };
  query_type?: 'FACT' | 'COMPARE' | 'RECOMMEND' | 'LIST';
  table?: { columns: { id: string; name: string }[]; rows: { aspect: string; cells: { text: string; cite: number[] }[] }[] };
  live?: { step: 'official' | 'nirf' | 'third_party' | 'none'; domain: string; cached: boolean; checked?: string[]; fetched?: string[]; elapsed_s?: number };
  college_ids: string[]; notice?: string; demo_notice?: string;
  latency: { retrieval_ms: number; generation_ms: number; total_ms: number };
};
export type UpdateEvent = {
  id: number; college_id: string; source_id: number; change_type: string; detected_date: string; summary: string | null;
  summary_mode: string | null; added_count: number; removed_count: number; source_name: string | null; source_url: string | null;
  is_demo: boolean; verification: Verification | null; monitor_run_id: number | null; diff?: string | null;
};
export type MonitorRun = {
  id: number; trigger: string; status: string; started_at: string; finished_at: string | null; duration_ms: number | null;
  sources_checked: number; changes_found: number; errors: number;
  details?: { source_id: number; source_name: string; college_id: string; status: string; summary?: string; error?: string }[];
};
export type MonitorStatus = { enabled: boolean; running: boolean; interval_minutes: number; next_run_at: string | null; check_in_progress: boolean; stale_after_hours: number; last_run: MonitorRun | null };
export type WebResearchResult = { answer: string; provider: string; model: string; latency_ms: number; sources: { title: string; url: string; domain: string; verification: Verification }[] };
export type EvidenceCell = { available: boolean; text: string; source_name?: string; source_url?: string; is_demo?: boolean };
export type CompareEvidence = { topics: string[]; colleges: Record<string, Record<string, EvidenceCell>> };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch('/api' + path, { headers: { 'Content-Type': 'application/json' }, ...init });
  if (!r.ok) {
    let detail = `${r.status}`;
    try { detail = (await r.json()).detail || detail } catch { /* ignore */ }
    throw new Error(detail);
  }
  return r.json();
}
const post = <T,>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });

export const api = {
  health: () => fetch('/health').then(r => r.ok ? r.json() : null).catch(() => null),
  ask: (query: string, college_ids: string[] = [], live = true) => post<AskResult>('/ask', { query, college_ids, live }),
  sources: (college_id = '') => request<ApiSource[]>('/sources' + (college_id ? `?college_id=${encodeURIComponent(college_id)}` : '')),
  college: (id: string) => request<any>('/colleges/' + encodeURIComponent(id)),
  updates: (college_id = '') => request<UpdateEvent[]>('/updates' + (college_id ? `?college_id=${encodeURIComponent(college_id)}` : '')),
  update: (id: number) => request<UpdateEvent>('/updates/' + id),
  monitorStatus: () => request<MonitorStatus>('/monitor/status'),
  monitorRuns: () => request<MonitorRun[]>('/monitor/runs'),
  runCheck: (source_ids?: number[]) => post<MonitorRun>('/monitor/run', source_ids ? { source_ids } : undefined),
  simulateChange: (id: number) => post<any>(`/demo/sources/${id}/simulate-change`),
  ingestionEvents: () => request<any[]>('/ingestion-events'),
  analytics: () => request<any>('/analytics'),
  webResearch: (question: string) => post<WebResearchResult>('/web-research', { question }),
  compareEvidence: (college_ids: string[]) => post<CompareEvidence>('/compare/evidence', { college_ids }),
};

export function timeAgo(value: string | null | undefined): string {
  if (!value) return 'never';
  const then = new Date(value.endsWith('Z') || value.includes('+') ? value : value + 'Z').getTime();
  const s = Math.max(0, (Date.now() - then) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value.endsWith('Z') || value.includes('+') ? value : value + 'Z');
  return d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
