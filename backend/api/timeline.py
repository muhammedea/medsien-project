"""Visualization data for a run, worked out from its saved files (docs/ui-requirements.md §4.4).

The trace says when each request arrived, started, finished or was dropped. The saved inputs
add what the trace doesn't carry: work units, memory and the server limits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import engine as sim
from engine.models import REQUEST_ARRIVED, REQUEST_DROPPED, REQUEST_FINISHED, REQUEST_STARTED


def read_events(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_timeline(run_path: Path, zoom_threshold: int) -> dict[str, Any]:
    servers = sorted(sim.load_servers(run_path / "servers.json"), key=lambda s: s.id)
    requests = sorted(sim.load_requests(run_path / "requests.csv"), key=lambda r: (r.arrival_t, r.row))
    config = sim.load_config(run_path / "config.json")
    events = read_events(run_path / "run.jsonl")
    return derive_timeline(servers, requests, config, events, zoom_threshold)


def derive_timeline(
    servers: list[sim.ServerSpec],
    requests: list[sim.RequestSpec],
    config: sim.SimulationConfig,
    events: list[dict[str, Any]],
    zoom_threshold: int,
) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {
        r.id: {
            "id": r.id,
            "arrival": r.arrival_t,
            "work_units": r.work_units,
            "mem_mb": r.mem_mb,
            "server_id": None,
            "start": None,
            "finish": None,
            "drop_t": None,
            "drop_reason": None,
        }
        for r in requests
    }

    # Replay the trace in written order. After all events of tick t, record the state, but
    # only when it differs from the last recorded entry.
    queued = running = dropped_total = 0
    mem_used = {s.id: 0 for s in servers}
    series: list[dict[str, Any]] = []
    last_state: tuple[Any, ...] | None = None

    def flush(t: int) -> None:
        nonlocal last_state
        state = (queued, running, dropped_total, tuple(mem_used.values()))
        if state != last_state:
            series.append(
                {"t": t, "queued": queued, "running": running, "dropped_total": dropped_total, "mem_used": dict(mem_used)}
            )
            last_state = state

    current_t: int | None = None
    for ev in events:
        t = ev["t"]
        if current_t is not None and t != current_t:
            flush(current_t)
        current_t = t
        req = by_id[ev["request_id"]]
        kind = ev["event"]
        if kind == REQUEST_ARRIVED:
            queued += 1
        elif kind == REQUEST_STARTED:
            queued -= 1
            running += 1
            mem_used[ev["server_id"]] += req["mem_mb"]
            req["server_id"] = ev["server_id"]
            req["start"] = t
        elif kind == REQUEST_FINISHED:
            running -= 1
            mem_used[ev["server_id"]] -= req["mem_mb"]
            req["finish"] = t
        elif kind == REQUEST_DROPPED:
            queued -= 1
            dropped_total += 1
            req["drop_t"] = t
            req["drop_reason"] = ev.get("reason")
    if current_t is not None:
        flush(current_t)

    first_tick = events[0]["t"] if events else 0
    last_tick = events[-1]["t"] if events else 0
    # Large runs: start the Gantt chart on the ticks covering the first `zoom_threshold` arrivals.
    view_end = last_tick
    if len(requests) > zoom_threshold:
        view_end = max(requests[zoom_threshold - 1].arrival_t, first_tick + 1)

    return {
        "mode": config.execution_mode,
        "first_tick": first_tick,
        "last_tick": last_tick,
        "initial_view": {"start": first_tick, "end": view_end},
        "servers": [
            {
                "id": s.id,
                "cpu_units_per_tick": s.cpu_units_per_tick,
                "mem_mb": s.mem_mb,
                "rate_limit_per_sec": s.rate_limit_per_sec,
            }
            for s in servers
        ],
        "requests": list(by_id.values()),
        "series": series,
    }
