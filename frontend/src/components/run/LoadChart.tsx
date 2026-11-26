import { useMemo } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Timeline } from "@/api";
import { BAR_COLOR, SERIES_COLORS } from "@/lib/timeline";

const LABELS = { queued: "Waiting", running: "Running", dropped_total: "Dropped so far" } as const;

type ChartClick = { activeLabel?: string | number } | null;

function useStepData(tl: Timeline) {
  return useMemo(() => {
    // series only lists ticks where a value changed; stepAfter lines hold the value until the next entry.
    const data = tl.series.map((e) => ({ t: e.t, queued: e.queued, running: e.running, dropped_total: e.dropped_total, ...prefixMem(e.mem_used) }));
    const last = data[data.length - 1];
    if (last && last.t < tl.last_tick) data.push({ ...last, t: tl.last_tick });
    return data;
  }, [tl]);
}

function prefixMem(mem: Record<string, number>) {
  return Object.fromEntries(Object.entries(mem).map(([k, v]) => [`mem:${k}`, v]));
}

const axisProps = { fontSize: 11, stroke: "var(--muted-foreground)", tickLine: false } as const;

export function LoadChart({ tl, tick, onTick }: { tl: Timeline; tick: number; onTick: (t: number) => void }) {
  const data = useStepData(tl);
  const onClick = (e: ChartClick) => {
    if (e && e.activeLabel !== undefined) onTick(Number(e.activeLabel));
  };
  const domain: [number, number] = [tl.first_tick, Math.max(tl.last_tick, tl.first_tick + 1)];

  return (
    <div className="grid gap-6">
      <div>
        <h3 className="mb-2 text-sm font-medium">Requests over time</h3>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data} onClick={onClick} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="t" type="number" domain={domain} allowDecimals={false} {...axisProps} />
            <YAxis allowDecimals={false} width={40} {...axisProps} />
            <Tooltip labelFormatter={(t) => `t = ${t}`} contentStyle={{ fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {(Object.keys(LABELS) as (keyof typeof LABELS)[]).map((k) => (
              <Line key={k} type="stepAfter" dataKey={k} name={LABELS[k]} stroke={SERIES_COLORS[k]} strokeWidth={2} dot={false} isAnimationActive={false} />
            ))}
            <ReferenceLine x={tick} stroke="var(--foreground)" strokeDasharray="4 3" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Memory used per server (MB)</h3>
        <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-4">
          {tl.servers.map((s) => (
            <div key={s.id}>
              <div className="mb-1 text-xs text-muted-foreground">
                <span className="font-mono text-foreground">{s.id}</span> · capacity {s.mem_mb} MB
              </div>
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={data} onClick={onClick} syncId="mem" margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="t" type="number" domain={domain} allowDecimals={false} {...axisProps} />
                  <YAxis domain={[0, s.mem_mb]} allowDecimals={false} width={40} {...axisProps} />
                  <Tooltip labelFormatter={(t) => `t = ${t}`} formatter={(v) => [`${v} MB`, s.id]} contentStyle={{ fontSize: 12 }} />
                  <Line type="stepAfter" dataKey={`mem:${s.id}`} name={s.id} stroke={BAR_COLOR} strokeWidth={2} dot={false} isAnimationActive={false} />
                  <ReferenceLine x={tick} stroke="var(--foreground)" strokeDasharray="4 3" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
