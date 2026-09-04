// Typed client for the control tower API.
//
// Shapes mirror the backend exactly. Where a field exists to make a governance point — `via` on a
// leg, `verified_by` on a guardrail check, `obo_active` on health — the comment says what the UI is
// expected to do with it, because rendering these wrongly would misrepresent the controls.

export interface RoutingLeg {
  domain: string;
  reason: string;
}

/** One domain subagent's result. `via` distinguishes a real Genie Agent answer from the degraded
 *  lanes, and the UI must show it: presenting a text2sql fallback or a throttled leg as if it were a
 *  Genie answer would hide the thing the operator most needs to know. */
export interface DomainLeg {
  domain: string;
  via: "genie_agent" | "text2sql_fallback" | "throttled" | "timeout" | "error" | null;
  sql: string;
  rows: Record<string, unknown>[];
  columns: string[];
  row_count: number;
  description: string;
  /** Set when the subagent's SQL answered the question but its PROSE did not — most often it replied
   *  with a clarifying question and never stated the figure. Detected in code rather than trusted to an
   *  instruction, because the instruction demonstrably did not hold. The UI must show it: a thin
   *  narrative presented as a normal answer is the failure this field exists to make visible. */
  narrative_defect: string | null;
  error: string | null;
  elapsed_ms: number;
}

export interface ActionDraft {
  action_type: string;
  subject: string;
  region: string | null;
  payload: Record<string, unknown>;
  level: number;
}

export interface AskResult {
  session_id: number | null;
  session_uuid: string;
  question: string;
  latency_ms: number;
  trace_id: string | null;
  routing: RoutingLeg[];
  router_fallback: boolean;
  legs: DomainLeg[];
  answer: string;
  recommended_action: string;
  proposed_action_type: string;
  action_draft: ActionDraft | null;
  data_is_synthetic: boolean;
}

/** A single guardrail outcome. `verified_by` is the honesty field: "payload" means we took the
 *  model's word for it, anything prefixed `unity_catalog:` means the check was confirmed against
 *  governed data. The UI renders that distinction rather than showing every check as equal. */
export interface GuardrailCheck {
  rule: string;
  applicable: boolean;
  passed: boolean;
  limit: unknown;
  value: unknown;
  detail: string;
  verified_by: string;
  legal_basis: string | null;
}

export interface Guardrail {
  passed: boolean;
  breaches: string[];
  checks: GuardrailCheck[];
  policy: Record<string, unknown> | null;
  verified_count: number;
  payload_count: number;
}

export interface ActionEvent {
  id: number;
  action_id: number;
  ts: string;
  event: string;
  actor: string;
  detail: Record<string, unknown> | null;
}

export interface Action {
  id: number;
  agent: string;
  action_type: string;
  subject: string;
  payload: Record<string, unknown> | string;
  status: string;
  level: number;
  region: string | null;
  branch_id: string | null;
  scheduled_at: string | null;
  session_uuid: string | null;
  trace_id: string | null;
  requested_by: string;
  approved_by: string | null;
  created_at: string;
  decided_at: string | null;
  executed_at: string | null;
  result: Record<string, unknown> | null;
  external_ref: string | null;
  events?: ActionEvent[];
}

export interface Health {
  status: string;
  service_identity: string;
  caller: string;
  obo_active: boolean;
  catalog: string;
  schema: string;
  warehouse_id: string;
  genie_agents: Record<string, boolean>;
  lakebase: string;
  data_is_synthetic: boolean;
  require_obo: boolean;
  turn_budget_seconds: number;
  genie_quota: { used_in_window: number; capacity: number; window_seconds: number };
}

export interface ScopeTable {
  table: string;
  visible: number;
  total: number;
  pct: number;
}

export interface Scope {
  identity: string | null;
  group_memberships: Record<string, boolean>;
  entitlements: Record<string, string>[];
  tables: ScopeTable[];
  unrestricted: boolean;
  masked_customer_id_example: string | null;
  note: string;
}

export interface Policies {
  row_filters: Record<string, string>[];
  column_masks: Record<string, string>[];
  column_tags: Record<string, string>[];
  table_tags: Record<string, string>[];
  functions: Record<string, string>[];
  summary: Record<string, number>;
}

export interface Controls {
  policies: Record<string, unknown>[];
  guardrail_visibility: Record<string, unknown>;
  kill_switch: { actions_enabled: boolean; detail: string };
  approver_directory: { principal: string; roles: string[] }[];
}

export interface AuditFeed {
  events: Record<string, string>[];
  by_action: Record<string, number>;
  window_hours: number;
  note: string;
}

export interface Evidence {
  complaint_id: string;
  found: boolean;
  record?: Record<string, string | null>;
  has_letter?: boolean;
  letter_path?: string | null;
  note?: string;
}

export interface Draft {
  ok: boolean;
  complaint_id?: string;
  document_path?: string;
  preview?: string;
  grounded_in_letter?: boolean;
  action_draft?: {
    action_type: string;
    subject: string;
    region: string | null;
    payload: Record<string, unknown>;
    level: number;
  };
  note?: string;
}

export interface Usage {
  turns: Record<string, unknown>;
  by_domain: Record<string, unknown>[];
  actions: Record<string, unknown>[];
  feedback: Record<string, unknown>;
  note: string;
}


// --- semantic search over the letter corpus --------------------------------
export interface SearchHit {
  complaint_id: string | null;
  /** Null on a hit the caller may not read: the index found it, the record was withheld. */
  document_type: string | null;
  rbi_ground: string | null;
  city: string | null;
  score: number;
  snippet: string;
  record: Record<string, unknown> | null;
  /** The index found it; the caller may not read it. NOT "no such complaint" — the UI must never let
   *  anyone draw that conclusion, because retrieval runs as the service principal while the record is
   *  re-read under the caller's own entitlements. */
  outside_your_scope: boolean;
}

export interface SearchResult {
  ok: boolean;
  hits: SearchHit[];
  query?: string;
  index?: string;
  returned?: number;
  withheld_by_entitlement?: number;
  note: string;
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    // FastAPI validation errors put an ARRAY in `detail`; passing that to Error() yields a comma-joined
    // blob, so it is formatted rather than stringified by accident.
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d: { msg?: string }) => d?.msg ?? JSON.stringify(d)).join("; ")
      : body.detail;
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  // A 200 is not a promise of JSON. When a Databricks App's OAuth session lapses the auth proxy answers
  // 200 with an HTML login page, and the raw parser message ("Unexpected token '<'") tells the operator
  // nothing about what actually happened.
  return res.json().catch(() => {
    throw new Error(
      `${url} returned a non-JSON response. If this is the deployed app your workspace session has ` +
      `probably expired — reload the page to sign in again.`
    );
  });
}

function post<T>(url: string, body?: unknown): Promise<T> {
  return req<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const api = {
  health: () => req<Health>("/api/health"),
  ask: (question: string) => post<AskResult>("/api/ask", { question }),
  feedback: (session_uuid: string, rating: number, note?: string) =>
    post<{ feedback_id: number }>("/api/feedback", { session_uuid, rating, note }),

  // Act -> Approve -> Execute
  act: (body: {
    action_type: string;
    subject: string;
    payload: Record<string, unknown>;
    region?: string | null;
    level?: number;
    scheduled_at?: string | null;
    session_uuid?: string | null;
    trace_id?: string | null;
  }) => post<{ action: Action; guardrail: Guardrail; approver_role: string | null }>("/api/act", body),
  actions: (status?: string) =>
    req<{ actions: Action[] }>(`/api/actions${status ? `?status=${status}` : ""}`),
  action: (id: number) => req<{ action: Action; guardrail: Guardrail }>(`/api/actions/${id}`),
  approve: (id: number) => post<{ action: Action }>(`/api/actions/${id}/approve`),
  reject: (id: number, reason: string) =>
    post<{ action: Action }>(`/api/actions/${id}/reject`, { reason }),
  execute: (id: number) => post<{ action: Action }>(`/api/actions/${id}/execute`),

  // Governance evidence
  scope: () => req<Scope>("/api/governance/scope"),
  policies: () => req<Policies>("/api/governance/policies"),
  controls: () => req<Controls>("/api/governance/controls"),
  audit: () => req<AuditFeed>("/api/governance/audit"),
  usage: () => req<Usage>("/api/governance/usage"),
  killSwitch: (enabled: boolean, reason: string) =>
    post<Record<string, unknown>>("/api/governance/kill-switch", {
      flag: "actions_enabled",
      enabled,
      reason,
    }),
  dashboard: () => req<{ dashboard_id: string | null; workspace_host: string }>("/api/dashboard"),

  // The volumes lane
  evidence: (complaintId: string) => req<Evidence>(`/api/documents/evidence/${complaintId}`),
  draft: (complaintId: string) => post<Draft>(`/api/documents/draft/${complaintId}`),
  search: (query: string, limit = 8) => post<SearchResult>("/api/documents/search", { query, limit }),
  // `outbound_path` is absent when the volume listing itself failed, so it is optional here rather
  // than a lie the compiler believes.
  outbound: () =>
    req<{ documents: { name: string; path: string; size: number }[]; outbound_path?: string }>(
      "/api/documents/outbound"
    ),
};

// --- voice (agent assist) --------------------------------------------------
// Speech recognition happens in the browser, so the only thing that crosses to the server is text the
// officer's own device produced. That is a governance property, not an implementation detail: no
// customer audio is transmitted, stored, or sent to a model.
export interface VoiceCheck {
  rule: string;
  passed: boolean;
  detail: string;
  verified_by: string;
}

export interface VoiceAssist {
  entities: { loan_account_id?: string; complaint_id?: string; agent_id?: string };
  resolved: boolean;
  /** An identifier was heard but no row came back. Under OBO that means "outside your entitlement",
   *  which is NOT the same as "no such account" — the UI must not let the officer conclude the latter. */
  not_visible: boolean;
  loan: Record<string, unknown> | null;
  contact: Record<string, unknown> | null;
  complaint: Record<string, unknown> | null;
  grievance: Record<string, unknown>;
  customer_id: string | null;
  conduct: VoiceCheck[];
  blocked: string[];
  data_is_synthetic: boolean;
}

export const voiceApi = {
  assist: (transcript: string, at_epoch_seconds?: number) =>
    post<VoiceAssist>("/api/voice/assist", { transcript, at_epoch_seconds }),
};
