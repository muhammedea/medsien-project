import { useMemo } from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { api, type Timeline } from "@/api";
import { useLoad } from "@/hooks/useLoad";
import { DROP_COLORS, eventTicks, stateAt } from "@/lib/timeline";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Loading, ErrorState } from "@/components/states";

const MAX_LISTED = 40;

export function TickInspector({
  runId,
  tl,
  tick,
  onTick,
  onSelectRequest,
}: {
  runId: number;
  tl: Timeline;
  tick: number;
  onTick: (t: number) => void;
  onSelectRequest: (id: string) => void;
}) {
  const state = useMemo(() => stateAt(tl, tick), [tl, tick]);
  const ticks = useMemo(() => eventTicks(tl), [tl]);
  const prevEvent = [...ticks].reverse().find((t) => t < tick);
  const nextEvent = ticks.find((t) => t > tick);
  const events = useLoad(() => api.events(runId, 0, 1000, { t: tick }), [runId, tick]);
  const clamp = (t: number) => Math.min(Math.max(t, tl.first_tick), tl.last_tick);

  const reqChip = (id: string) => (
    <button
      key={id}
      type="button"
      onClick={() => onSelectRequest(id)}
      className="rounded border bg-background px-1.5 py-0.5 font-mono text-xs hover:bg-muted"
    >
      {id}
    </button>
  );

  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="icon-sm" onClick={() => prevEvent !== undefined && onTick(prevEvent)} disabled={prevEvent === undefined} aria-label="Previous tick with events">
          <ChevronsLeft aria-hidden />
        </Button>
        <Button variant="outline" size="icon-sm" onClick={() => onTick(clamp(tick - 1))} disabled={tick <= tl.first_tick} aria-label="Previous tick">
          <ChevronLeft aria-hidden />
        </Button>
        <Slider
          className="flex-1"
          min={tl.first_tick}
          max={Math.max(tl.last_tick, tl.first_tick + 1)}
          step={1}
          value={[tick]}
          onValueChange={([v]) => onTick(clamp(v))}
          aria-label="Selected tick"
        />
        <Button variant="outline" size="icon-sm" onClick={() => onTick(clamp(tick + 1))} disabled={tick >= tl.last_tick} aria-label="Next tick">
          <ChevronRight aria-hidden />
        </Button>
        <Button variant="outline" size="icon-sm" onClick={() => nextEvent !== undefined && onTick(nextEvent)} disabled={nextEvent === undefined} aria-label="Next tick with events">
          <ChevronsRight aria-hidden />
        </Button>
        <span className="w-20 text-right text-sm font-medium tabular-nums">t = {tick}</span>
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">State after all events of tick {tick} (arrivals, then finishes, then scheduling).</p>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
        {tl.servers.map((s) => {
          const running = state.running[s.id];
          const mem = running.reduce((sum, r) => sum + r.mem_mb, 0);
          const pct = Math.min(100, (mem / s.mem_mb) * 100);
          const starts = state.starts[s.id];
          return (
            <div key={s.id} className="rounded-lg border p-3">
              <div className="mb-2 flex items-baseline justify-between">
                <span className="font-mono font-medium">{s.id}</span>
                <span className="text-xs text-muted-foreground">
                  starts {starts}/{s.rate_limit_per_sec}
                  {starts >= s.rate_limit_per_sec && " (limit)"}
                </span>
              </div>
              <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                <span>Memory</span>
                <span className="tabular-nums">
                  {mem} / {s.mem_mb} MB
                </span>
              </div>
              <div className="mb-3 h-2 overflow-hidden rounded-full bg-muted" role="meter" aria-valuemin={0} aria-valuemax={s.mem_mb} aria-valuenow={mem} aria-label={`${s.id} memory used`}>
                <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
              <div className="text-xs text-muted-foreground">Running ({running.length})</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {running.length === 0 ? <span className="text-xs text-muted-foreground">idle</span> : running.map((r) => reqChip(r.id))}
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border p-3">
          <div className="mb-2 text-sm font-medium">Queue ({state.queue.length}), oldest first</div>
          {state.queue.length === 0 ? (
            <span className="text-xs text-muted-foreground">empty</span>
          ) : (
            <div className="flex flex-wrap gap-1">
              {state.queue.slice(0, MAX_LISTED).map((r) => reqChip(r.id))}
              {state.queue.length > MAX_LISTED && (
                <span className="text-xs text-muted-foreground">and {state.queue.length - MAX_LISTED} more</span>
              )}
            </div>
          )}
        </div>

        <div className="rounded-lg border p-3">
          <div className="mb-2 text-sm font-medium">Events at t = {tick}, in written order</div>
          {events.loading && !events.data ? (
            <Loading />
          ) : events.error ? (
            <ErrorState error={events.error} onRetry={events.reload} />
          ) : events.data && events.data.items.length === 0 ? (
            <span className="text-xs text-muted-foreground">No events at this tick.</span>
          ) : (
            <ol className="grid gap-0.5 font-mono text-xs">
              {events.data?.items.map((e) => (
                <li key={e.line} className="flex gap-2">
                  <span className="w-8 text-right text-muted-foreground">{e.line}</span>
                  <span className="w-36">{e.event}</span>
                  <span>{e.request_id}</span>
                  {e.server_id && <span className="text-muted-foreground">→ {e.server_id}</span>}
                  {e.reason && (
                    <span>
                      <span style={{ color: DROP_COLORS[e.reason] }} aria-hidden>
                        ✕
                      </span>{" "}
                      {e.reason}
                    </span>
                  )}
                </li>
              ))}
              {events.data && events.data.total > events.data.items.length && (
                <li className="text-muted-foreground">and {events.data.total - events.data.items.length} more</li>
              )}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}
