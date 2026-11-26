"""The shared-mode validator: engine traces pass it, broken traces fail it, and the original is untouched."""

import dataclasses
import subprocess
import sys

import pytest

from engine import SimulationConfig, event_to_dict, load_requests, load_servers, simulate, to_jsonl
from tests.conftest import BACKEND_DIR, FIXTURES, random_case, reqs, srv
from validator import validate_run_shared as VS

SHARED = SimulationConfig(execution_mode="shared")


def run_shared_validator(servers, requests, events):
    v_servers = {s.id: VS.ServerSpec(s.id, s.cpu_units_per_tick, s.mem_mb, s.rate_limit_per_sec) for s in servers}
    v_requests = {r.id: VS.RequestSpec(r.id, r.arrival_t, r.work_units, r.mem_mb) for r in requests}
    dicts = [e if isinstance(e, dict) else event_to_dict(e) for e in events]
    return VS.validate(v_servers, v_requests, dicts)


def errors(issues):
    return [i.msg for i in issues if i.level == "ERROR"]


def ev(t, event, rid, sid=None):
    d = {"t": t, "event": event, "request_id": rid}
    if sid is not None:
        d["server_id"] = sid
    return d


@pytest.mark.parametrize("seed", range(300))
def test_random_shared_runs_pass(seed):
    servers, requests, config = random_case(seed)
    result = simulate(servers, requests, dataclasses.replace(config, execution_mode="shared"))
    ok, issues, summary = run_shared_validator(servers, requests, result.events)
    assert ok, errors(issues)
    assert summary["started"] == result.summary["started"]
    assert summary["dropped"] == result.summary["dropped"]
    assert summary["p95_wait_ticks"] == result.summary["p95_wait_ticks"]


@pytest.mark.parametrize("seed", range(100))
def test_random_exclusive_runs_also_pass(seed):
    # One request per server at a time is a special case of the shared rules.
    servers, requests, config = random_case(seed)
    result = simulate(servers, requests, config)
    ok, issues, _ = run_shared_validator(servers, requests, result.events)
    assert ok, errors(issues)


def test_cpu_split_example():
    # 10 CPU; 1 and 6 work units start at t=0: 5 each in tick 0, then the 6-unit request gets all 10.
    servers = [srv("s1", 10, 1000, rate=2)]
    requests = reqs((0, "a", 1, 10), (0, "b", 6, 10))
    events = [
        ev(0, "REQUEST_ARRIVED", "a"),
        ev(0, "REQUEST_ARRIVED", "b"),
        ev(0, "REQUEST_STARTED", "a", "s1"),
        ev(0, "REQUEST_STARTED", "b", "s1"),
        ev(1, "REQUEST_FINISHED", "a", "s1"),
        ev(2, "REQUEST_FINISHED", "b", "s1"),
    ]
    ok, issues, _ = run_shared_validator(servers, requests, events)
    assert ok, errors(issues)

    # Finishing b at t=1 would need the full CPU in tick 0, which is the exclusive rule.
    wrong = events[:5] + [ev(1, "REQUEST_FINISHED", "b", "s1")]
    ok, issues, _ = run_shared_validator(servers, requests, wrong)
    assert not ok
    assert any("Finish time mismatch for 'b'" in m for m in errors(issues))


def test_sample_shared_run_passes_cli(tmp_path):
    servers = load_servers(FIXTURES / "servers.json")
    requests = load_requests(FIXTURES / "requests.csv")
    run = tmp_path / "run.jsonl"
    run.write_text(to_jsonl(simulate(servers, requests, SHARED).events))
    cmd = [sys.executable, str(BACKEND_DIR / "validator" / "validate_run_shared.py"),
           "--servers", str(FIXTURES / "servers.json"), "--requests", str(FIXTURES / "requests.csv"), "--run", str(run)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: VALID" in proc.stdout


def _shared_sample():
    servers = load_servers(FIXTURES / "servers.json")
    requests = load_requests(FIXTURES / "requests.csv")
    events = [event_to_dict(e) for e in simulate(servers, requests, SHARED).events]
    return servers, requests, events


def test_rejects_memory_overflow():
    servers = [srv("s1", 10, 100, rate=2)]
    requests = reqs((0, "a", 10, 60), (0, "b", 10, 60))
    events = [
        ev(0, "REQUEST_ARRIVED", "a"),
        ev(0, "REQUEST_ARRIVED", "b"),
        ev(0, "REQUEST_STARTED", "a", "s1"),
        ev(0, "REQUEST_STARTED", "b", "s1"),
        ev(2, "REQUEST_FINISHED", "a", "s1"),
        ev(2, "REQUEST_FINISHED", "b", "s1"),
    ]
    ok, issues, _ = run_shared_validator(servers, requests, events)
    assert not ok
    assert any("Memory exceeded on server 's1' at tick 0" in m for m in errors(issues))


def test_memory_freed_at_a_tick_can_be_reused_at_that_tick():
    servers = [srv("s1", 10, 100, rate=1)]
    requests = reqs((0, "a", 10, 80), (0, "b", 10, 80))
    events = [
        ev(0, "REQUEST_ARRIVED", "a"),
        ev(0, "REQUEST_ARRIVED", "b"),
        ev(0, "REQUEST_STARTED", "a", "s1"),
        ev(1, "REQUEST_STARTED", "b", "s1"),  # written before a's finish on purpose
        ev(1, "REQUEST_FINISHED", "a", "s1"),
        ev(2, "REQUEST_FINISHED", "b", "s1"),
    ]
    ok, issues, _ = run_shared_validator(servers, requests, events)
    assert ok, errors(issues)


def test_rejects_rate_limit():
    servers = [srv("s1", 10, 1000, rate=1)]
    requests = reqs((0, "a", 10, 10), (0, "b", 10, 10))
    events = [
        ev(0, "REQUEST_ARRIVED", "a"),
        ev(0, "REQUEST_ARRIVED", "b"),
        ev(0, "REQUEST_STARTED", "a", "s1"),
        ev(0, "REQUEST_STARTED", "b", "s1"),
        ev(2, "REQUEST_FINISHED", "a", "s1"),
        ev(2, "REQUEST_FINISHED", "b", "s1"),
    ]
    ok, issues, _ = run_shared_validator(servers, requests, events)
    assert any("Rate limit exceeded on server 's1' at tick 0" in m for m in errors(issues))


def test_rejects_request_that_never_ends():
    servers, requests, events = _shared_sample()
    events = [e for e in events if e["request_id"] != "r4" or e["event"] == "REQUEST_ARRIVED"]
    ok, issues, _ = run_shared_validator(servers, requests, events)
    assert not ok
    assert "Request 'r4' arrived but was never started or dropped" in errors(issues)


def test_rejects_unfinished_and_mismatched_server():
    servers, requests, events = _shared_sample()
    finishes = [e for e in events if e["event"] == "REQUEST_FINISHED"]
    first, second = finishes[0], finishes[1]
    broken = [e for e in events if e is not first]
    broken = [dict(e, server_id="s2" if e["server_id"] == "s1" else "s1") if e is second else e for e in broken]
    ok, issues, _ = run_shared_validator(servers, requests, broken)
    msgs = errors(issues)
    assert f"Request '{first['request_id']}' started but never finished" in msgs
    assert any("server mismatch" in m for m in msgs)


def test_rejects_drop_after_start_and_start_before_arrival():
    servers = [srv("s1", 10, 1000)]
    requests = reqs((1, "a", 10, 10), (0, "b", 10, 10))
    events = [
        ev(0, "REQUEST_STARTED", "a", "s1"),
        ev(1, "REQUEST_ARRIVED", "a"),
        ev(0, "REQUEST_ARRIVED", "b"),
        ev(0, "REQUEST_STARTED", "b", "s1"),
        ev(1, "REQUEST_DROPPED", "b"),
        ev(1, "REQUEST_FINISHED", "b", "s1"),
    ]
    msgs = errors(run_shared_validator(servers, requests, events)[1])
    assert "REQUEST_STARTED before REQUEST_ARRIVED for 'a'" in msgs
    assert "REQUEST_DROPPED after REQUEST_STARTED for 'b'" in msgs


def test_replay_jumps_over_long_runs():
    # 10^9 work units on a 1-CPU server must not be replayed tick by tick.
    assert VS.replay_server(1, [(0, "big", 10**9), (5, "small", 3)]) == {"small": 11, "big": 10**9 + 3}


def test_original_validator_is_unchanged():
    original = (BACKEND_DIR.parent / "project-info" / "validate_run.py")
    if not original.exists():  # not part of the backend Docker build context
        pytest.skip("project-info not available")
    assert (BACKEND_DIR / "validator" / "validate_run.py").read_bytes() == original.read_bytes()
