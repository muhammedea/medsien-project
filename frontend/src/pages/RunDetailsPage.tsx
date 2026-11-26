import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, Download, RotateCcw } from "lucide-react";
import { api, ApiError, DROP_REASONS, urls, type RunDetail, type Timeline } from "@/api";
import { useLoad } from "@/hooks/useLoad";
import { formatDate, shortHash, show } from "@/lib/format";
import { DROP_COLORS } from "@/lib/timeline";
import { EmptyState, ErrorState, Loading } from "@/components/states";
import { SameOutputBadge, StatusBadge } from "@/components/run/badges";
import { ServersTable } from "@/components/run/ServersTable";
import { EventsTable } from "@/components/run/EventsTable";
import { Gantt, type View } from "@/components/run/Gantt";
import { TickInspector } from "@/components/run/TickInspector";
import { LoadChart } from "@/components/run/LoadChart";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function RunDetailsPage() {
  const id = Number(useParams().id);
  const run = useLoad(() => api.getRun(id), [id]);

  if (!Number.isInteger(id) || id < 1) return <EmptyState message="Invalid run id." />;
  if (run.loading && !run.data) return <Loading />;
  if (run.error) return <ErrorState error={run.error} onRetry={run.reload} title={`Could not load run #${id}`} />;
  if (!run.data) return null;
  return <RunDetails key={run.data.id} run={run.data} />;
}

function Section({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Meta({ label, children, title }: { label: string; children: ReactNode; title?: string }) {
  return (
    <div title={title}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function RunDetails({ run }: { run: RunDetail }) {
  const navigate = useNavigate();
  const [rerunning, setRerunning] = useState(false);
  const [rerunError, setRerunError] = useState<string | null>(null);
  const [requestFilter, setRequestFilter] = useState("");
  const eventsRef = useRef<HTMLDivElement>(null);
  const completed = run.status === "completed";

  async function rerun() {
    setRerunning(true);
    setRerunError(null);
    try {
      const next = await api.rerun(run.id);
      navigate(`/runs/${next.id}`);
    } catch (e) {
      setRerunError((e as ApiError).message);
      setRerunning(false);
    }
  }

  const selectRequest = useCallback((rid: string | null) => {
    setRequestFilter(rid ?? "");
    if (rid) eventsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const c = run.config;
  const s = run.summary;

  return (
    <div className="grid gap-6">
      <div>
        <Link to="/runs" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" aria-hidden /> All runs
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">Run #{run.id}</h1>
            <StatusBadge status={run.status} />
            <SameOutputBadge runId={run.same_output_as} />
          </div>
          {completed && (
            <div className="flex flex-wrap items-center gap-2">
              <Button asChild>
                <a href={urls.trace(run.id)} download>
                  <Download aria-hidden /> Download run.jsonl
                </a>
              </Button>
              {(["servers.json", "requests.csv", "config.json"] as const).map((name) => (
                <Button key={name} variant="outline" asChild>
                  <a href={urls.input(run.id, name)} download>
                    <Download aria-hidden /> {name}
                  </a>
                </Button>
              ))}
              <Button variant="outline" onClick={rerun} disabled={rerunning}>
                <RotateCcw aria-hidden /> {rerunning ? "Running…" : "Run again with the same inputs"}
              </Button>
            </div>
          )}
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-3 rounded-lg border p-4 md:grid-cols-4 lg:grid-cols-6">
          <Meta label="Created">{formatDate(run.created_at)}</Meta>
          <Meta label="Mode">
            <span className="font-mono">{c.execution_mode}</span>
          </Meta>
          <Meta label="Placement">
            <span className="font-mono">{c.placement}</span>
          </Meta>
          <Meta label="Max wait (ticks)">{c.max_wait_ticks ?? "no limit"}</Meta>
          <Meta label="Max queue length">{c.max_queue_length ?? "no limit"}</Meta>
          <Meta label="Requests">{run.requests_source === "sample" ? "sample" : `upload: ${run.requests_filename ?? "file"}`}</Meta>
          <Meta label="Engine version">
            <span className="font-mono">{run.engine_version}</span>
          </Meta>
          <Meta label="Input hash" title={run.input_hash}>
            <span className="font-mono">{shortHash(run.input_hash)}</span>
          </Meta>
          <Meta label="Trace hash" title={run.trace_hash ?? undefined}>
            <span className="font-mono">{shortHash(run.trace_hash)}</span>
          </Meta>
        </dl>
      </div>

      {rerunError && (
        <Alert variant="destructive">
          <AlertDescription>{rerunError}</AlertDescription>
        </Alert>
      )}

      {run.status === "failed" && (
        <Alert variant="destructive">
          <AlertTitle>The run failed</AlertTitle>
          <AlertDescription>{run.error ?? "No error message was recorded."}</AlertDescription>
        </Alert>
      )}

      {s && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
          <Stat label="Total requests" value={s.total_requests} />
          <Stat label="Started" value={s.started} />
          <Stat label="Finished" value={s.finished} />
          <Stat label="Dropped" value={s.dropped}>
            <ul className="mt-1 grid gap-0.5 text-xs text-muted-foreground">
              {DROP_REASONS.map((reason) => (
                <li key={reason} className="flex items-center gap-1">
                  <span style={{ color: DROP_COLORS[reason] }} aria-hidden>
                    ✕
                  </span>
                  {reason}: <span className="tabular-nums text-foreground">{s.dropped_by_reason[reason] ?? 0}</span>
                </li>
              ))}
            </ul>
          </Stat>
          <Stat label="Last tick" value={s.last_tick} />
          <Stat label="Avg wait" value={s.avg_wait_ticks} unit="ticks" />
          <Stat label="p50 wait" value={s.p50_wait_ticks} unit="ticks" />
          <Stat label="p95 wait" value={s.p95_wait_ticks} unit="ticks" />
          <Stat label="Max wait" value={s.max_wait_ticks} unit="ticks" />
        </div>
      )}

      {run.servers && (
        <Section title="Servers used" description="The server snapshot this run was made with.">
          <ServersTable servers={run.servers} />
        </Section>
      )}

      {completed && <Visualization runId={run.id} onSelectRequest={selectRequest} highlighted={requestFilter || null} />}

      {completed && (
        <div ref={eventsRef} className="scroll-mt-4">
          <Section title="Events" description="One row per line of run.jsonl, in written order.">
            <EventsTable
              runId={run.id}
              serverIds={(run.servers ?? []).map((x) => x.id)}
              requestFilter={requestFilter}
              onRequestFilterChange={setRequestFilter}
            />
          </Section>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, unit, children }: { label: string; value: number | null; unit?: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">
        {show(value)}
        {unit && value !== null && <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span>}
      </div>
      {children}
    </div>
  );
}

function Visualization({
  runId,
  highlighted,
  onSelectRequest,
}: {
  runId: number;
  highlighted: string | null;
  onSelectRequest: (id: string | null) => void;
}) {
  const tl = useLoad(() => api.timeline(runId), [runId]);
  if (tl.loading && !tl.data) return <Loading label="Loading the timeline…" />;
  if (tl.error) return <ErrorState error={tl.error} onRetry={tl.reload} title="Could not load the timeline" />;
  if (!tl.data) return null;
  return <VisualizationViews runId={runId} tl={tl.data} highlighted={highlighted} onSelectRequest={onSelectRequest} />;
}

function VisualizationViews({
  runId,
  tl,
  highlighted,
  onSelectRequest,
}: {
  runId: number;
  tl: Timeline;
  highlighted: string | null;
  onSelectRequest: (id: string | null) => void;
}) {
  const [tick, setTick] = useState(tl.first_tick);
  const [view, setView] = useState<View>(() => ({
    start: tl.initial_view.start,
    end: Math.max(tl.initial_view.end, tl.initial_view.start + 1),
  }));
  const zoomedForSize = tl.initial_view.end < tl.last_tick;

  // Selecting a request also moves the tick to when it started (or was dropped).
  const selectRequest = (id: string | null) => {
    onSelectRequest(id);
    const r = id ? tl.requests.find((x) => x.id === id) : undefined;
    if (r) setTick(r.start ?? r.drop_t ?? r.arrival);
  };

  // Keep the selected tick visible in the Gantt chart.
  useEffect(() => {
    setView((v) => {
      if (tick >= v.start && tick <= v.end) return v;
      const span = v.end - v.start;
      const start = Math.max(tl.first_tick, Math.min(tick - Math.floor(span / 2), Math.max(tl.last_tick, tl.first_tick + 1) - span));
      return { start, end: start + span };
    });
  }, [tick, tl]);

  return (
    <>
      <Section
        title="Server timeline"
        description={
          <>
            One lane per server; each bar runs from a request's start tick to its finish tick.
            {tl.mode === "shared" && " In shared mode, overlapping requests are stacked in sub-rows."}
            {zoomedForSize && ` This is a large run, so the chart starts zoomed in on ticks ${tl.initial_view.start}–${tl.initial_view.end}.`}
          </>
        }
      >
        <Gantt
          tl={tl}
          view={view}
          onViewChange={setView}
          selectedTick={tick}
          onSelectTick={setTick}
          highlighted={highlighted}
          onSelectRequest={selectRequest}
        />
      </Section>

      <Section title="Tick inspector" description="Pick a tick to see each server, the queue and the events written at that tick.">
        <TickInspector runId={runId} tl={tl} tick={tick} onTick={setTick} onSelectRequest={(id) => selectRequest(id)} />
      </Section>

      <Section title="Load over time" description="Click the chart to select a tick.">
        <LoadChart tl={tl} tick={tick} onTick={setTick} />
      </Section>
    </>
  );
}
