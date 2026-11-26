// Small typed client for the backend API (docs/high-level-design.md, "API").

export type Server = {
  id: string;
  cpu_units_per_tick: number;
  mem_mb: number;
  rate_limit_per_sec: number;
};

export type ExecutionMode = "exclusive" | "shared";
export type DropReason = "no_server_fits" | "max_wait_exceeded" | "queue_full";
export const DROP_REASONS: DropReason[] = ["no_server_fits", "max_wait_exceeded", "queue_full"];

export type RunConfig = {
  execution_mode: ExecutionMode;
  placement: string;
  max_wait_ticks: number | null;
  max_queue_length: number | null;
};

export type RunSummary = {
  execution_mode: ExecutionMode;
  placement: string;
  total_requests: number;
  started: number;
  finished: number;
  dropped: number;
  dropped_by_reason: Record<string, number>;
  avg_wait_ticks: number | null;
  p50_wait_ticks: number | null;
  p95_wait_ticks: number | null;
  max_wait_ticks: number | null;
  last_tick: number | null;
};

export type Run = {
  id: number;
  created_at: string;
  status: "pending" | "completed" | "failed";
  config: RunConfig;
  requests_source: "sample" | "upload";
  requests_filename: string | null;
  summary: RunSummary | null;
  input_hash: string;
  trace_hash: string | null;
  engine_version: string;
  error: string | null;
  same_output_as: number | null;
};

export type RunDetail = Run & { servers: Server[] | null };

export type EventType = "REQUEST_ARRIVED" | "REQUEST_STARTED" | "REQUEST_FINISHED" | "REQUEST_DROPPED";
export const EVENT_TYPES: EventType[] = ["REQUEST_ARRIVED", "REQUEST_STARTED", "REQUEST_FINISHED", "REQUEST_DROPPED"];

export type TraceEvent = {
  line: number;
  t: number;
  event: EventType;
  request_id: string;
  server_id?: string;
  reason?: DropReason;
};

export type EventPage = { total: number; offset: number; limit: number; items: TraceEvent[] };

export type EventFilters = { event?: string; request_id?: string; server_id?: string; t?: number };

export type TimelineRequest = {
  id: string;
  arrival: number;
  work_units: number;
  mem_mb: number;
  server_id: string | null;
  start: number | null;
  finish: number | null;
  drop_t: number | null;
  drop_reason: DropReason | null;
};

export type SeriesEntry = {
  t: number;
  queued: number;
  running: number;
  dropped_total: number;
  mem_used: Record<string, number>;
};

export type Timeline = {
  mode: ExecutionMode;
  first_tick: number;
  last_tick: number;
  initial_view: { start: number; end: number };
  servers: Server[];
  requests: TimelineRequest[];
  series: SeriesEntry[];
};

export type Limits = { max_upload_bytes: number; max_request_rows: number };

/** An error response from the API. `field` names the input it concerns, when known. */
export class ApiError extends Error {
  status: number;
  field?: string;
  constructor(status: number, message: string, field?: string) {
    super(message);
    this.status = status;
    this.field = field;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (e) {
    throw new ApiError(0, `Cannot reach the API: ${(e as Error).message}`);
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    let field: string | undefined;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        // FastAPI's own request validation errors.
        message = body.detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).join(".")}: ${d.msg}`).join("; ");
      }
      if (typeof body.field === "string") field = body.field;
    } catch {
      // Not JSON; keep the status text.
    }
    throw new ApiError(res.status, message, field);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  limits: () => request<Limits>("/api/limits"),

  listServers: () => request<Server[]>("/api/servers"),
  createServer: (s: Server) => request<Server>("/api/servers", json("POST", s)),
  updateServer: (id: string, s: Omit<Server, "id">) =>
    request<Server>(`/api/servers/${encodeURIComponent(id)}`, json("PUT", s)),
  deleteServer: (id: string) => request<void>(`/api/servers/${encodeURIComponent(id)}`, { method: "DELETE" }),

  listRuns: () => request<Run[]>("/api/runs"),
  getRun: (id: number) => request<RunDetail>(`/api/runs/${id}`),
  startRun: (config: Partial<RunConfig>, requests?: File | Blob, filename?: string) => {
    const form = new FormData();
    form.append("config", JSON.stringify(config));
    if (requests) form.append("requests", requests, filename ?? "requests.csv");
    return request<Run>("/api/runs", { method: "POST", body: form });
  },
  rerun: (id: number) => request<Run>(`/api/runs/${id}/rerun`, { method: "POST" }),
  events: (id: number, offset: number, limit: number, filters: EventFilters) => {
    const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined && v !== "") params.set(k, String(v));
    }
    return request<EventPage>(`/api/runs/${id}/events?${params}`);
  },
  timeline: (id: number) => request<Timeline>(`/api/runs/${id}/timeline`),
};

// Plain download links (the browser handles them).
export const urls = {
  trace: (id: number) => `/api/runs/${id}/run.jsonl`,
  input: (id: number, name: "servers.json" | "requests.csv" | "config.json") => `/api/runs/${id}/inputs/${name}`,
  sampleCsv: "/api/samples/requests.csv",
};
