import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { ChevronLeft, ChevronRight, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import type { DropReason, Timeline, TimelineRequest } from "@/api";
import { BAR_COLOR, DROP_COLORS, HIGHLIGHT_COLOR, leftQueue, niceStep, packRows } from "@/lib/timeline";
import { Button } from "@/components/ui/button";

export type View = { start: number; end: number };

const LABEL_W = 72;
const ROW_H = 16;
const ROW_GAP = 3;
const LANE_PAD = 6;
const AXIS_H = 22;
const QUEUE_ROW_H = 7;
const MAX_QUEUE_ROWS = 12; // the queue lane wraps beyond this many sub-rows

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    if (!ref.current) return;
    const obs = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return { ref, width };
}

export function fullView(tl: Timeline): View {
  return { start: tl.first_tick, end: Math.max(tl.last_tick, tl.first_tick + 1) };
}

export function Gantt({
  tl,
  view,
  onViewChange,
  selectedTick,
  onSelectTick,
  highlighted,
  onSelectRequest,
}: {
  tl: Timeline;
  view: View;
  onViewChange: (v: View) => void;
  selectedTick: number;
  onSelectTick: (t: number) => void;
  highlighted: string | null;
  onSelectRequest: (id: string | null) => void;
}) {
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ r: TimelineRequest; x: number; y: number } | null>(null);

  // Lane layout (independent of zoom).
  const layout = useMemo(() => {
    const waited = tl.requests.filter((r) => leftQueue(r) > r.arrival || r.drop_t !== null);
    const queue = packRows(waited, (r) => r.arrival, (r) => Math.max(leftQueue(r), r.arrival + 1), (r) => r.id);
    const queueRows = Math.min(queue.rows, MAX_QUEUE_ROWS);
    const lanes = tl.servers.map((s) => {
      const bars = tl.requests.filter((r) => r.server_id === s.id && r.start !== null && r.finish !== null);
      return { server: s, ...packRows(bars, (r) => r.start!, (r) => r.finish!, (r) => r.id) };
    });
    let y = AXIS_H;
    const queueTop = y;
    const queueH = LANE_PAD * 2 + queueRows * QUEUE_ROW_H;
    y += queueH;
    const laneTops = lanes.map((lane) => {
      const top = y;
      y += LANE_PAD * 2 + lane.rows * (ROW_H + ROW_GAP) - ROW_GAP;
      return top;
    });
    return { queue: queue.placed, queueRows, queueTop, queueH, lanes, laneTops, height: y + 4 };
  }, [tl]);

  const plotW = Math.max(100, width - LABEL_W - 8);
  const span = Math.max(1, view.end - view.start);
  const x = (t: number) => LABEL_W + ((t - view.start) / span) * plotW;
  const visible = (a: number, b: number) => b >= view.start && a <= view.end;
  const full = fullView(tl);

  const clamp = (v: View): View => {
    const s = Math.max(1, Math.min(v.end - v.start, full.end - full.start));
    const start = Math.min(Math.max(v.start, full.start), full.end - s);
    return { start, end: start + s };
  };
  const zoom = (factor: number) => {
    const center = selectedTick >= view.start && selectedTick <= view.end ? selectedTick : (view.start + view.end) / 2;
    const s = Math.max(1, Math.round(span * factor));
    onViewChange(clamp({ start: Math.round(center - s / 2), end: Math.round(center - s / 2) + s }));
  };
  const pan = (dir: number) => {
    const d = Math.max(1, Math.round(span / 4)) * dir;
    onViewChange(clamp({ start: view.start + d, end: view.end + d }));
  };

  const step = niceStep(span, Math.max(2, Math.floor(plotW / 70)));
  const axisTicks: number[] = [];
  for (let t = Math.ceil(view.start / step) * step; t <= view.end; t += step) axisTicks.push(t);

  function onBackgroundClick(e: MouseEvent<SVGRectElement>) {
    const rect = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
    const t = Math.round(view.start + ((e.clientX - rect.left - LABEL_W) / plotW) * span);
    onSelectTick(Math.min(Math.max(t, tl.first_tick), tl.last_tick));
    onSelectRequest(null);
  }

  function showHover(e: MouseEvent, r: TimelineRequest) {
    const box = ref.current!.getBoundingClientRect();
    setHover({ r, x: e.clientX - box.left, y: e.clientY - box.top });
  }

  const zoomed = view.start !== full.start || view.end !== full.end;

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-1">
        <Button variant="outline" size="sm" onClick={() => zoom(0.5)} disabled={span <= 1} aria-label="Zoom in">
          <ZoomIn aria-hidden />
        </Button>
        <Button variant="outline" size="sm" onClick={() => zoom(2)} disabled={!zoomed} aria-label="Zoom out">
          <ZoomOut aria-hidden />
        </Button>
        <Button variant="outline" size="sm" onClick={() => pan(-1)} disabled={view.start <= full.start} aria-label="Pan left">
          <ChevronLeft aria-hidden />
        </Button>
        <Button variant="outline" size="sm" onClick={() => pan(1)} disabled={view.end >= full.end} aria-label="Pan right">
          <ChevronRight aria-hidden />
        </Button>
        <Button variant="outline" size="sm" onClick={() => onViewChange(full)} disabled={!zoomed}>
          <Maximize2 aria-hidden /> Show all
        </Button>
        <span className="ml-2 text-xs text-muted-foreground">
          Ticks {view.start}–{view.end} of {full.start}–{full.end}. Click a bar to filter the events table; click empty
          space to select a tick.
        </span>
      </div>

      <div ref={ref} className="relative w-full" onMouseLeave={() => setHover(null)}>
        <svg width={width} height={layout.height} className="block select-none" role="img" aria-label="Server timeline">
          <defs>
            <clipPath id="gantt-plot">
              <rect x={LABEL_W} y={0} width={plotW} height={layout.height} />
            </clipPath>
          </defs>

          {/* Axis and grid */}
          {axisTicks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={AXIS_H - 4} y2={layout.height} stroke="var(--border)" />
              <text x={x(t)} y={AXIS_H - 8} textAnchor="middle" fontSize={10} fill="var(--muted-foreground)">
                {t}
              </text>
            </g>
          ))}

          <rect
            x={LABEL_W}
            y={AXIS_H}
            width={plotW}
            height={layout.height - AXIS_H}
            fill="transparent"
            onClick={onBackgroundClick}
            className="cursor-crosshair"
          />

          {/* Queue lane */}
          <rect x={0} y={layout.queueTop} width={width} height={layout.queueH} fill="var(--muted)" opacity={0.5} pointerEvents="none" />
          <text x={8} y={layout.queueTop + layout.queueH / 2 + 4} fontSize={11} fontWeight={500} fill="var(--foreground)">
            Queue
          </text>
          <g clipPath="url(#gantt-plot)">
            {layout.queue.map(({ item: r, row }) => {
              const end = leftQueue(r);
              if (!visible(r.arrival, end)) return null;
              const y = layout.queueTop + LANE_PAD + (row % MAX_QUEUE_ROWS) * QUEUE_ROW_H + QUEUE_ROW_H / 2;
              const hl = highlighted === r.id;
              return (
                <g
                  key={r.id}
                  onMouseMove={(e) => showHover(e, r)}
                  onClick={() => onSelectRequest(r.id)}
                  className="cursor-pointer"
                >
                  <rect x={x(r.arrival)} y={y - 3} width={Math.max(6, x(end) - x(r.arrival))} height={6} fill="transparent" />
                  {end > r.arrival && (
                    <line
                      x1={x(r.arrival)}
                      x2={x(end)}
                      y1={y}
                      y2={y}
                      stroke={hl ? HIGHLIGHT_COLOR : "var(--muted-foreground)"}
                      strokeWidth={hl ? 3 : 1.5}
                      strokeLinecap="round"
                    />
                  )}
                  {r.drop_t !== null && <DropMark cx={x(r.drop_t)} cy={y} reason={r.drop_reason!} highlight={hl} />}
                </g>
              );
            })}
          </g>

          {/* Server lanes */}
          {layout.lanes.map((lane, i) => {
            const top = layout.laneTops[i];
            return (
              <g key={lane.server.id}>
                <line x1={0} x2={width} y1={top} y2={top} stroke="var(--border)" />
                <text x={8} y={top + LANE_PAD + ROW_H / 2 + 4} fontSize={11} fontWeight={500} fill="var(--foreground)" className="font-mono">
                  {lane.server.id}
                </text>
                <g clipPath="url(#gantt-plot)">
                  {lane.placed.map(({ item: r, row }) => {
                    if (!visible(r.start!, r.finish!)) return null;
                    const bx = x(r.start!);
                    const bw = Math.max(2, x(r.finish!) - bx - 2); // 2px gap between adjacent bars
                    const by = top + LANE_PAD + row * (ROW_H + ROW_GAP);
                    const hl = highlighted === r.id;
                    return (
                      <g
                        key={r.id}
                        onMouseMove={(e) => showHover(e, r)}
                        onClick={() => onSelectRequest(r.id)}
                        className="cursor-pointer"
                      >
                        <rect
                          x={bx}
                          y={by}
                          width={bw}
                          height={ROW_H}
                          rx={3}
                          fill={hl ? HIGHLIGHT_COLOR : BAR_COLOR}
                          opacity={highlighted && !hl ? 0.45 : 1}
                        />
                        {bw > r.id.length * 6.5 + 6 && (
                          <text x={bx + 4} y={by + ROW_H / 2 + 4} fontSize={10} fill="white" pointerEvents="none">
                            {r.id}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </g>
              </g>
            );
          })}

          {/* Selected tick */}
          {selectedTick >= view.start && selectedTick <= view.end && (
            <line
              x1={x(selectedTick)}
              x2={x(selectedTick)}
              y1={AXIS_H - 4}
              y2={layout.height}
              stroke="var(--foreground)"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              pointerEvents="none"
            />
          )}
        </svg>

        {hover && <RequestTooltip r={hover.r} x={hover.x} y={hover.y} containerWidth={width} />}
      </div>

      <DropLegend />
    </div>
  );
}

function DropMark({ cx, cy, reason, highlight }: { cx: number; cy: number; reason: DropReason; highlight?: boolean }) {
  const s = highlight ? 5 : 4;
  return (
    <g stroke={DROP_COLORS[reason]} strokeWidth={2} strokeLinecap="round">
      <line x1={cx - s} y1={cy - s} x2={cx + s} y2={cy + s} />
      <line x1={cx - s} y1={cy + s} x2={cx + s} y2={cy - s} />
    </g>
  );
}

export function DropLegend() {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2.5 w-5 rounded-sm" style={{ background: BAR_COLOR }} /> running request
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-0.5 w-5 bg-muted-foreground" /> waiting in queue
      </span>
      {(Object.keys(DROP_COLORS) as DropReason[]).map((reason) => (
        <span key={reason} className="flex items-center gap-1">
          <span style={{ color: DROP_COLORS[reason] }} className="font-bold" aria-hidden>
            ✕
          </span>
          dropped: {reason}
        </span>
      ))}
    </div>
  );
}

function RequestTooltip({ r, x, y, containerWidth }: { r: TimelineRequest; x: number; y: number; containerWidth: number }) {
  const left = x + 240 > containerWidth ? x - 232 : x + 12;
  const wait = r.start !== null ? r.start - r.arrival : r.drop_t !== null ? r.drop_t - r.arrival : null;
  const rows: [string, string | number][] = [
    ["Work units", r.work_units],
    ["Memory", `${r.mem_mb} MB`],
    ["Arrival", r.arrival],
  ];
  if (r.start !== null) rows.push(["Server", r.server_id ?? "—"], ["Start", r.start], ["Finish", r.finish ?? "—"]);
  if (r.drop_t !== null) rows.push(["Dropped", `t=${r.drop_t} (${r.drop_reason})`]);
  if (wait !== null) rows.push(["Wait", `${wait} ticks`]);
  return (
    <div
      className="pointer-events-none absolute z-10 w-56 rounded-md border bg-popover p-2 text-xs shadow-md"
      style={{ left, top: y + 12 }}
    >
      <div className="mb-1 font-mono font-semibold">{r.id}</div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
