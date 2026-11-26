// Pure helpers for the run visualization. All layouts are deterministic.
import type { DropReason, SeriesEntry, Timeline, TimelineRequest } from "@/api";

// Reference data-viz palette (validated categorical slots 1-3, light mode).
export const SERIES_COLORS = { queued: "#2a78d6", running: "#eb6834", dropped_total: "#1baf7a" } as const;
export const DROP_COLORS: Record<DropReason, string> = {
  no_server_fits: "#e34948",
  max_wait_exceeded: "#eda100",
  queue_full: "#6250d6",
};
export const BAR_COLOR = "#2a78d6";
export const HIGHLIGHT_COLOR = "#eb6834";

export type Placed<T> = { item: T; row: number };

/**
 * Greedy interval packing: items sorted by (start, id) go into the first sub-row whose last
 * item has ended. Intervals are half-open [start, end), so a bar finishing at t and one
 * starting at t share a row.
 */
export function packRows<T>(items: T[], start: (x: T) => number, end: (x: T) => number, id: (x: T) => string) {
  const sorted = [...items].sort((a, b) => start(a) - start(b) || (id(a) < id(b) ? -1 : id(a) > id(b) ? 1 : 0));
  const rowEnds: number[] = [];
  const placed: Placed<T>[] = [];
  for (const item of sorted) {
    let row = rowEnds.findIndex((e) => e <= start(item));
    if (row === -1) {
      row = rowEnds.length;
      rowEnds.push(end(item));
    } else rowEnds[row] = end(item);
    placed.push({ item, row });
  }
  return { placed, rows: Math.max(1, rowEnds.length) };
}

/** When the request left the queue: its start or its drop tick. */
export const leftQueue = (r: TimelineRequest) => (r.start ?? r.drop_t ?? r.arrival) as number;

/** The series value at tick t (entries only exist where something changed). */
export function seriesAt(series: SeriesEntry[], t: number): SeriesEntry | null {
  let lo = 0;
  let hi = series.length - 1;
  let found: SeriesEntry | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (series[mid].t <= t) {
      found = series[mid];
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return found;
}

/** The state after all events of tick t. */
export function stateAt(tl: Timeline, t: number) {
  const running: Record<string, TimelineRequest[]> = {};
  const starts: Record<string, number> = {};
  for (const s of tl.servers) {
    running[s.id] = [];
    starts[s.id] = 0;
  }
  const queue: TimelineRequest[] = [];
  for (const r of tl.requests) {
    if (r.start !== null && r.server_id !== null && r.finish !== null) {
      if (r.start <= t && t < r.finish) running[r.server_id].push(r);
      if (r.start === t) starts[r.server_id] += 1;
    }
    const inQueue = r.arrival <= t && !(r.start !== null && r.start <= t) && !(r.drop_t !== null && r.drop_t <= t);
    if (inQueue) queue.push(r); // tl.requests is in arrival order (t, CSV row), so oldest first
  }
  return { running, starts, queue };
}

/** Ticks where at least one event happened, for the inspector's "next event" buttons. */
export function eventTicks(tl: Timeline): number[] {
  const set = new Set<number>();
  for (const r of tl.requests) {
    set.add(r.arrival);
    if (r.start !== null) set.add(r.start);
    if (r.finish !== null) set.add(r.finish);
    if (r.drop_t !== null) set.add(r.drop_t);
  }
  return [...set].sort((a, b) => a - b);
}

/** Round axis step: 1, 2, 5, 10, 20, 50, ... giving about `target` ticks. */
export function niceStep(span: number, target = 10): number {
  const raw = Math.max(1, span / target);
  const pow = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 5, 10]) if (m * pow >= raw) return m * pow;
  return 10 * pow;
}
