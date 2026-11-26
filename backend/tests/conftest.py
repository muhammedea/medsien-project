"""Shared test helpers.

The checks here are written separately from the engine on purpose, so the tests
don't simply re-run the engine's own logic against itself.
"""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

from engine import RequestSpec, ServerSpec, SimulationConfig, event_to_dict
from validator import validate_run as V

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURES = BACKEND_DIR / "fixtures"
TEST_DATA = Path(__file__).resolve().parent / "data"


def srv(sid: str, cpu: int, mem: int, rate: int = 1) -> ServerSpec:
    return ServerSpec(id=sid, cpu_units_per_tick=cpu, mem_mb=mem, rate_limit_per_sec=rate)


def reqs(*rows: tuple[int, str, int, int]) -> list[RequestSpec]:
    """Build requests from (t, id, work_units, mem_mb) tuples, keeping their order as the CSV row order."""
    return [RequestSpec(id=rid, arrival_t=t, work_units=w, mem_mb=m, row=i) for i, (t, rid, w, m) in enumerate(rows)]


def run_validator(servers, requests, events) -> tuple[bool, list, dict]:
    """Run the original, unmodified validate_run.validate() on an engine trace."""
    v_servers = {s.id: V.ServerSpec(s.id, s.cpu_units_per_tick, s.mem_mb, s.rate_limit_per_sec) for s in servers}
    v_requests = {r.id: V.RequestSpec(r.id, r.arrival_t, r.work_units, r.mem_mb) for r in requests}
    return V.validate(v_servers, v_requests, [event_to_dict(e) for e in events])


def assert_lifecycle(requests, events) -> None:
    """Each request: ARRIVED→STARTED→FINISHED or ARRIVED→DROPPED, in emitted order. The validator doesn't check this."""
    seqs = defaultdict(list)
    for e in events:
        seqs[e.request_id].append(e.event)
    assert set(seqs) == {r.id for r in requests}, "some request has no events at all"
    for r in requests:
        assert seqs[r.id] in (
            ["REQUEST_ARRIVED", "REQUEST_STARTED", "REQUEST_FINISHED"],
            ["REQUEST_ARRIVED", "REQUEST_DROPPED"],
        ), f"{r.id}: {seqs[r.id]}"


def assert_resources(servers, requests, events) -> None:
    """Replay the trace: total memory per server and starts per tick never exceed their limits (works for both modes)."""
    spec = {s.id: s for s in servers}
    req = {r.id: r for r in requests}
    mem = defaultdict(int)
    starts = defaultdict(int)
    for e in events:  # emitted order: finishes come before starts within a tick
        if e.event == "REQUEST_FINISHED":
            mem[e.server_id] -= req[e.request_id].mem_mb
        elif e.event == "REQUEST_STARTED":
            mem[e.server_id] += req[e.request_id].mem_mb
            starts[(e.server_id, e.t)] += 1
            assert mem[e.server_id] <= spec[e.server_id].mem_mb, f"memory exceeded on {e.server_id} at t={e.t}"
            assert starts[(e.server_id, e.t)] <= spec[e.server_id].rate_limit_per_sec, (
                f"rate limit exceeded on {e.server_id} at t={e.t}"
            )
    for e in events:
        if e.event == "REQUEST_STARTED":
            assert e.t >= req[e.request_id].arrival_t


def random_case(seed: int) -> tuple[list[ServerSpec], list[RequestSpec], SimulationConfig]:
    """Random but reproducible input, including overload and requests too big for every server."""
    rng = random.Random(seed)
    servers = [
        srv(f"s{i}", cpu=rng.randint(1, 20), mem=rng.randint(128, 2048), rate=rng.randint(1, 3))
        for i in range(1, rng.randint(1, 5) + 1)
    ]
    n = rng.randint(1, 80)
    horizon = rng.choice([1, 5, 30, 200])  # small horizon = heavy overload
    rows = [(rng.randint(0, horizon), f"r{i}", rng.randint(1, 120), rng.randint(0, 2600)) for i in range(n)]
    rng.shuffle(rows)  # CSV rows are not necessarily sorted by t
    config = SimulationConfig(
        max_wait_ticks=rng.choice([None, None, 0, 1, 3, 10]),
        max_queue_length=rng.choice([None, None, 0, 1, 5, 20]),
    )
    return servers, reqs(*rows), config
