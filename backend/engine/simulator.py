"""The tick loop. See docs/engine-design.md section 4 for the exact step order."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .execution import EXECUTION_MODELS, ServerState
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
) -> SimulationResult:
    """Run the simulation. Pure: no I/O, no clock, no randomness."""
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
        if all_idle and not queue:
            if next_arrival == len(arrivals):
                break
            t = arrivals[next_arrival].arrival_t  # fast-forward over idle gaps
        else:
            t += 1

    check_lifecycle(events, requests)
    return SimulationResult(events=events, summary=summarize(events, requests, config))


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
