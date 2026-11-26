#!/usr/bin/env python3
"""
validate_run_shared.py

Validator for traces made in `shared` mode (the concurrent model from Section 4
of the assignment). The original validate_run.py stays unchanged and still
checks the default `exclusive` mode.

Usage:
  python validate_run_shared.py --servers servers.json --requests requests.csv --run run.jsonl

Rules checked:
  - Lifecycle: each request arrives exactly once at its CSV tick, then either
    starts and finishes on the same server, or is dropped. A request that
    arrives and is never started or dropped is an error.
  - Rate limit: at most rate_limit_per_sec starts per server per tick.
  - Memory: at every tick, the requests running on a server (start <= t < finish)
    fit in its mem_mb together. Finishes at tick t free memory before starts at t.
  - Finish times: the trace's start times are replayed per server. During each
    tick, every running request gets cpu_units_per_tick / N, where N is the number
    of requests running in that tick; leftover CPU is not reused. A request
    finishes at the first tick where its remaining work is <= 0.

An `exclusive` trace is also a valid `shared` trace (N is always 1).

This file shares nothing with the engine on purpose, so the engine is not used
to check itself. Only the input loaders and dataclasses come from validate_run.py.

Exit codes:
  0 = valid
  2 = invalid
"""

import argparse
import math
import sys
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:  # run as a script: python validator/validate_run_shared.py
    from validate_run import (
        RequestSpec,
        ServerSpec,
        ValidationIssue,
        load_requests,
        load_servers,
        parse_run_jsonl,
    )
except ImportError:  # imported as a package: from validator import validate_run_shared
    from validator.validate_run import (
        RequestSpec,
        ServerSpec,
        ValidationIssue,
        load_requests,
        load_servers,
        parse_run_jsonl,
    )

LIFECYCLE_EVENTS = ("REQUEST_ARRIVED", "REQUEST_STARTED", "REQUEST_FINISHED", "REQUEST_DROPPED")

# Within one tick: arrivals first, then finishes (they free memory), then starts and drops.
PHASE = {"REQUEST_ARRIVED": 0, "REQUEST_FINISHED": 1, "REQUEST_STARTED": 2, "REQUEST_DROPPED": 3}


def replay_server(cpu: int, starts: List[Tuple[int, str, int]]) -> Dict[str, int]:
    """Expected finish tick for each request started on one server.

    `starts` holds (start_t, request_id, work_units). Between two moments where the
    running set changes, every request gets the same share per tick, so the replay
    jumps from one change to the next instead of visiting every tick.
    """
    starts = sorted(starts)
    finish: Dict[str, int] = {}
    running: Dict[str, Fraction] = {}  # request_id -> remaining work
    i = 0
    t = 0

    def add_starts_at(tick: int) -> None:
        nonlocal i
        while i < len(starts) and starts[i][0] == tick:
            _, rid, work = starts[i]
            running[rid] = Fraction(work)
            i += 1

    while i < len(starts) or running:
        if not running:
            t = starts[i][0]
            add_starts_at(t)
            continue
        n = len(running)
        # Ticks each request still needs at the current share cpu / n.
        next_finish = t + min(math.ceil(rem * n / cpu) for rem in running.values())
        next_t = min(next_finish, starts[i][0]) if i < len(starts) else next_finish
        share = Fraction(cpu * (next_t - t), n)
        done = []
        for rid in running:
            running[rid] -= share
            if running[rid] <= 0:
                done.append(rid)
        for rid in done:
            finish[rid] = next_t
            del running[rid]
        t = next_t
        add_starts_at(t)
    return finish


def validate(
    servers: Dict[str, ServerSpec], requests: Dict[str, RequestSpec], events: List[dict]
) -> Tuple[bool, List[ValidationIssue], dict]:
    issues: List[ValidationIssue] = []

    def add_error(msg: str) -> None:
        issues.append(ValidationIssue("ERROR", msg))

    # Basic schema checks
    valid_events: List[Tuple[int, int, dict]] = []
    for line_no, ev in enumerate(events, start=1):
        if "t" not in ev or "event" not in ev:
            add_error(f"Missing required fields in event: {ev}")
            continue
        if not isinstance(ev["t"], int) or isinstance(ev["t"], bool):
            add_error(f"Event t must be int: {ev}")
            continue
        if not isinstance(ev["event"], str):
            add_error(f"Event event must be str: {ev}")
            continue
        valid_events.append((line_no, ev["t"], ev))

    # Sort by tick and phase; the written order is kept within the same phase.
    valid_events.sort(key=lambda x: (x[1], PHASE.get(x[2]["event"], 4), x[0]))

    seen_arrival: Dict[str, int] = {}
    started: Dict[str, Tuple[int, str]] = {}  # request_id -> (t_start, server_id)
    finished: Dict[str, Tuple[int, str]] = {}  # request_id -> (t_finish, server_id)
    dropped: Dict[str, int] = {}
    starts_per_server_tick: Dict[Tuple[str, int], int] = {}

    for _line, t, ev in valid_events:
        et = ev["event"]
        if et not in LIFECYCLE_EVENTS:
            continue  # unknown events are ignored, as in the original validator
        rid = ev.get("request_id")
        if not isinstance(rid, str) or not rid:
            add_error(f"{et} missing/invalid request_id: {ev}")
            continue
        if rid not in requests:
            add_error(f"{et} references unknown request_id '{rid}' not in requests.csv")
            continue

        if et == "REQUEST_ARRIVED":
            if rid in seen_arrival:
                add_error(f"Duplicate REQUEST_ARRIVED for request '{rid}'")
                continue
            expected_t = requests[rid].arrival_t
            if t != expected_t:
                add_error(f"REQUEST_ARRIVED.t mismatch for '{rid}': got {t}, expected {expected_t}")
            seen_arrival[rid] = t

        elif et == "REQUEST_STARTED":
            sid = ev.get("server_id")
            if not isinstance(sid, str) or sid not in servers:
                add_error(f"REQUEST_STARTED invalid server_id '{sid}' for request '{rid}'")
                continue
            if rid not in seen_arrival:
                add_error(f"REQUEST_STARTED before REQUEST_ARRIVED for '{rid}'")
                continue
            if rid in started:
                add_error(f"Duplicate REQUEST_STARTED for '{rid}'")
                continue
            if rid in dropped:
                add_error(f"REQUEST_STARTED after REQUEST_DROPPED for '{rid}'")
                continue
            key = (sid, t)
            starts_per_server_tick[key] = starts_per_server_tick.get(key, 0) + 1
            started[rid] = (t, sid)

        elif et == "REQUEST_FINISHED":
            sid = ev.get("server_id")
            if not isinstance(sid, str) or sid not in servers:
                add_error(f"REQUEST_FINISHED invalid server_id '{sid}' for request '{rid}'")
                continue
            if rid not in started:
                add_error(f"REQUEST_FINISHED before REQUEST_STARTED for '{rid}'")
                continue
            if rid in finished:
                add_error(f"Duplicate REQUEST_FINISHED for '{rid}'")
                continue
            sid_start = started[rid][1]
            if sid != sid_start:
                add_error(f"REQUEST_FINISHED server mismatch for '{rid}': started on {sid_start}, finished on {sid}")
            finished[rid] = (t, sid)

        elif et == "REQUEST_DROPPED":
            if rid not in seen_arrival:
                add_error(f"REQUEST_DROPPED before REQUEST_ARRIVED for '{rid}'")
                continue
            if rid in dropped:
                add_error(f"Duplicate REQUEST_DROPPED for '{rid}'")
                continue
            if rid in started:
                add_error(f"REQUEST_DROPPED after REQUEST_STARTED for '{rid}'")
                continue
            dropped[rid] = t

    # Every request arrives, and every arrived request ends.
    for rid in requests:
        if rid not in seen_arrival:
            add_error(f"Missing REQUEST_ARRIVED for request '{rid}'")
        elif rid not in started and rid not in dropped:
            add_error(f"Request '{rid}' arrived but was never started or dropped")
    for rid in started:
        if rid not in finished:
            add_error(f"Request '{rid}' started but never finished")

    # Rate limit
    for (sid, t), count in sorted(starts_per_server_tick.items()):
        limit = servers[sid].rate_limit_per_sec
        if count > limit:
            add_error(f"Rate limit exceeded on server '{sid}' at tick {t}: starts={count} > limit={limit}")

    # Memory: sweep each server's [start, finish) intervals; finishes before starts at the same tick.
    for sid, srv in servers.items():
        changes: List[Tuple[int, int, str]] = []  # (t, 0 = finish / 1 = start, request_id)
        for rid, (t_start, s) in started.items():
            if s != sid:
                continue
            changes.append((t_start, 1, rid))
            if rid in finished:
                changes.append((finished[rid][0], 0, rid))
        changes.sort()
        used = 0
        reported_ticks: List[int] = []
        for t, kind, rid in changes:
            used += requests[rid].mem_mb if kind == 1 else -requests[rid].mem_mb
            if kind == 1 and used > srv.mem_mb and (not reported_ticks or reported_ticks[-1] != t):
                reported_ticks.append(t)
                add_error(f"Memory exceeded on server '{sid}' at tick {t}: used={used} > mem_mb={srv.mem_mb}")

    # Finish times: replay the CPU split from the trace's start times.
    for sid, srv in servers.items():
        on_server = [(t_start, rid, requests[rid].work_units) for rid, (t_start, s) in started.items() if s == sid]
        expected = replay_server(srv.cpu_units_per_tick, on_server)
        for _t, rid, work in sorted(on_server):
            if rid not in finished:
                continue
            t_finish = finished[rid][0]
            if t_finish != expected[rid]:
                add_error(
                    f"Finish time mismatch for '{rid}' on '{sid}': got t_finish={t_finish}, "
                    f"expected {expected[rid]} (shared CPU; work_units={work}, "
                    f"cpu_units_per_tick={srv.cpu_units_per_tick})"
                )

    waits = sorted(t_start - requests[rid].arrival_t for rid, (t_start, _sid) in started.items())

    def pctl(vals: List[int], p: float) -> Optional[int]:
        if not vals:
            return None
        idx = max(0, min(int(math.ceil(p * len(vals))) - 1, len(vals) - 1))
        return vals[idx]

    summary = {
        "total_requests": len(requests),
        "started": len(started),
        "finished": len(finished),
        "dropped": len(dropped),
        "avg_wait_ticks": (sum(waits) / len(waits)) if waits else None,
        "p50_wait_ticks": pctl(waits, 0.50),
        "p95_wait_ticks": pctl(waits, 0.95),
        "max_wait_ticks": max(waits) if waits else None,
    }

    ok = not any(i.level == "ERROR" for i in issues)
    return ok, issues, summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a run.jsonl made in shared mode.")
    ap.add_argument("--servers", required=True, help="Path to servers.json")
    ap.add_argument("--requests", required=True, help="Path to requests.csv")
    ap.add_argument("--run", required=True, help="Path to run.jsonl")
    args = ap.parse_args()

    _tick_seconds, servers = load_servers(Path(args.servers))
    requests = load_requests(Path(args.requests))
    events = parse_run_jsonl(Path(args.run))

    ok, issues, summary = validate(servers, requests, events)

    for it in issues:
        print(f"{it.level}: {it.msg}")

    print("\nSUMMARY:")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if ok:
        print("\nRESULT: VALID ✅")
        return 0
    print("\nRESULT: INVALID ❌")
    return 2


if __name__ == "__main__":
    sys.exit(main())
