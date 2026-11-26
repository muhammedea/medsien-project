"""The tick loop. See docs/engine-design.md section 4 for the exact step order."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .execution import EXECUTION_MODELS, ExecutionModel, ServerState
from .loaders import validate_config, validate_requests, validate_servers
from .models import (
    DROP_MAX_WAIT_EXCEEDED,
    DROP_NO_SERVER_FITS,
    DROP_QUEUE_FULL,
    DROP_REASONS,
    REQUEST_ARRIVED,
    REQUEST_DROPPED,
    REQUEST_FINISHED,
    REQUEST_STARTED,
    Event,
    RequestSpec,
    ServerSpec,
    SimulationConfig,
    SimulationInvariantError,
)
from .placement import PLACEMENTS


@dataclass(frozen=True)
class SimulationResult:
    events: list[Event]
    summary: dict[str, Any]


def simulate(
    servers: Sequence[ServerSpec],
    requests: Sequence[RequestSpec],
    config: SimulationConfig | None = None,
    *,
    step_every_tick: bool = False,
) -> SimulationResult:
    """Run the simulation. Pure: no I/O, no clock, no randomness.

    By default, ticks in which nothing can happen are skipped (see _next_event_tick).
    `step_every_tick=True` visits every tick while work is in progress. It exists so tests
    can check that skipping never changes the output.
    """
    config = validate_config(config or SimulationConfig())
    servers = validate_servers(servers)
    requests = validate_requests(requests)

    model = EXECUTION_MODELS[config.execution_mode]()
    placement = PLACEMENTS[config.placement]()

    states = [ServerState(spec) for spec in sorted(servers, key=lambda s: s.id)]
    largest_mem = max(s.mem_mb for s in servers)
    arrivals = sorted(requests, key=lambda r: (r.arrival_t, r.row))

    events: list[Event] = []
    queue: list[RequestSpec] = []
    next_arrival = 0
    t = arrivals[0].arrival_t

    while True:
        # 1. ARRIVALS
        while next_arrival < len(arrivals) and arrivals[next_arrival].arrival_t == t:
            req = arrivals[next_arrival]
            next_arrival += 1
            events.append(Event(t, REQUEST_ARRIVED, req.id))
            if req.mem_mb > largest_mem:
                events.append(Event(t, REQUEST_DROPPED, req.id, reason=DROP_NO_SERVER_FITS))
            else:
                queue.append(req)

        # 2. PROGRESS + FINISHES (CPU work done during tick t-1)
        for state in states:
            for done in model.advance(state):
                events.append(Event(t, REQUEST_FINISHED, done.request.id, server_id=state.spec.id))

        # 3. SCHEDULING (FIFO with skip-ahead)
        for state in states:
            state.starts_this_tick = 0
        still_waiting: list[RequestSpec] = []
        for req in queue:
            candidates = [
                s
                for s in states
                if s.starts_this_tick < s.spec.rate_limit_per_sec and model.can_accept(s, req)
            ]
            if candidates:
                chosen = placement.choose(req, candidates, model)
                chosen.start(req, t)
                events.append(Event(t, REQUEST_STARTED, req.id, server_id=chosen.spec.id))
            elif config.max_wait_ticks is not None and t - req.arrival_t >= config.max_wait_ticks:
                events.append(Event(t, REQUEST_DROPPED, req.id, reason=DROP_MAX_WAIT_EXCEEDED))
            else:
                still_waiting.append(req)
        if config.max_queue_length is not None and len(still_waiting) > config.max_queue_length:
            for req in still_waiting[config.max_queue_length :]:
                events.append(Event(t, REQUEST_DROPPED, req.id, reason=DROP_QUEUE_FULL))
            still_waiting = still_waiting[: config.max_queue_length]
        queue = still_waiting

        # Advance time.
        all_idle = all(s.idle for s in states)
        if all_idle and queue:
            # Every queued request fits some idle server, so scheduling must have placed one.
            raise SimulationInvariantError(f"t={t}: requests queued while every server is idle")
        next_t = _next_event_tick(t, states, queue, arrivals, next_arrival, model, config)
        if next_t is None:
            break
        if step_every_tick and not all_idle:
            next_t = t + 1
        # Apply the CPU of the skipped ticks t .. next_t-2 in one step; step 2 of the
        # next iteration applies tick next_t-1 and emits the finishes.
        for state in states:
            model.advance_many(state, next_t - t - 1)
        t = next_t

    check_lifecycle(events, requests)
    return SimulationResult(events=events, summary=summarize(events, requests, config))


def _next_event_tick(
    t: int,
    states: list[ServerState],
    queue: list[RequestSpec],
    arrivals: list[RequestSpec],
    next_arrival: int,
    model: ExecutionModel,
    config: SimulationConfig,
) -> int | None:
    """The next tick at which something can happen, or None when the simulation is over.

    Between ticks, the state only changes at:
      - the next arrival;
      - the next finish (only then is memory or a concurrency slot freed);
      - the next max-wait deadline of a queued request;
      - the next tick, if a queued request was held back only by a server's rate limit
        (the start counters reset every tick).
    Every tick before the earliest of these would repeat the same scheduling decisions,
    so it is safe to skip them.
    """
    candidates: list[int] = []
    if next_arrival < len(arrivals):
        candidates.append(arrivals[next_arrival].arrival_t)
    for state in states:
        ticks = model.ticks_until_next_finish(state)
        if ticks is not None:
            candidates.append(t + ticks)
    if queue:
        if config.max_wait_ticks is not None:
            candidates.append(min(r.arrival_t for r in queue) + config.max_wait_ticks)
        rate_limited = any(
            s.starts_this_tick >= s.spec.rate_limit_per_sec and any(model.can_accept(s, r) for r in queue)
            for s in states
        )
        if rate_limited:
            candidates.append(t + 1)
    return min(candidates) if candidates else None


def check_lifecycle(events: Sequence[Event], requests: Sequence[RequestSpec]) -> None:
    """Every request must end as ARRIVED→STARTED→FINISHED or ARRIVED→DROPPED, in emitted order."""
    sequences: dict[str, list[str]] = {r.id: [] for r in requests}
    for ev in events:
        if ev.request_id not in sequences:
            raise SimulationInvariantError(f"event for unknown request '{ev.request_id}'")
        sequences[ev.request_id].append(ev.event)
    allowed = (
        [REQUEST_ARRIVED, REQUEST_STARTED, REQUEST_FINISHED],
        [REQUEST_ARRIVED, REQUEST_DROPPED],
    )
    for rid, seq in sequences.items():
        if seq not in allowed:
            raise SimulationInvariantError(f"request '{rid}' has an invalid lifecycle: {seq}")


def _percentile(sorted_vals: list[int], p: float) -> int | None:
    # Same definition as validate_run.py, so the numbers match.
    if not sorted_vals:
        return None
    idx = max(0, min(int(math.ceil(p * len(sorted_vals))) - 1, len(sorted_vals) - 1))
    return sorted_vals[idx]


def summarize(events: Sequence[Event], requests: Sequence[RequestSpec], config: SimulationConfig) -> dict[str, Any]:
    arrival = {r.id: r.arrival_t for r in requests}
    waits = sorted(ev.t - arrival[ev.request_id] for ev in events if ev.event == REQUEST_STARTED)
    drops = {reason: 0 for reason in DROP_REASONS}
    finished = 0
    for ev in events:
        if ev.event == REQUEST_DROPPED:
            drops[ev.reason or "unknown"] = drops.get(ev.reason or "unknown", 0) + 1
        elif ev.event == REQUEST_FINISHED:
            finished += 1
    return {
        "execution_mode": config.execution_mode,
        "placement": config.placement,
        "total_requests": len(requests),
        "started": len(waits),
        "finished": finished,
        "dropped": sum(drops.values()),
        "dropped_by_reason": drops,
        "avg_wait_ticks": round(sum(waits) / len(waits), 4) if waits else None,
        "p50_wait_ticks": _percentile(waits, 0.50),
        "p95_wait_ticks": _percentile(waits, 0.95),
        "max_wait_ticks": waits[-1] if waits else None,
        "last_tick": events[-1].t if events else None,
    }
