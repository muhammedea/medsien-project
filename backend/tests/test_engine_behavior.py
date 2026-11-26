"""Unit tests for scheduling, execution models and overload rules."""

from fractions import Fraction

from engine import SimulationConfig, simulate
from engine.execution import ServerState, SharedModel, cpu_share
from tests.conftest import reqs, srv

SHARED = SimulationConfig(execution_mode="shared")


def trace(result):
    return [(e.t, e.event, e.request_id, e.server_id, e.reason) for e in result.events]


def finish_times(result):
    return {e.request_id: e.t for e in result.events if e.event == "REQUEST_FINISHED"}


def start_servers(result):
    return {e.request_id: e.server_id for e in result.events if e.event == "REQUEST_STARTED"}


# ----------------------------------------------------------------- execution models


def test_exclusive_runs_one_request_at_a_time():
    result = simulate([srv("s1", 10, 1000, rate=5)], reqs((0, "a", 20, 10), (0, "b", 10, 10)))
    assert trace(result) == [
        (0, "REQUEST_ARRIVED", "a", None, None),
        (0, "REQUEST_ARRIVED", "b", None, None),
        (0, "REQUEST_STARTED", "a", "s1", None),
        (2, "REQUEST_FINISHED", "a", "s1", None),
        (2, "REQUEST_STARTED", "b", "s1", None),
        (3, "REQUEST_FINISHED", "b", "s1", None),
    ]


def test_shared_split_is_computed_once_per_tick():
    # 10 CPU, works of 1 and 6: each gets 5 in tick 0; the 6-unit one gets all 10 in tick 1.
    servers = [srv("s1", 10, 1000, rate=2)]
    result = simulate(servers, reqs((0, "short", 1, 1), (0, "long", 6, 1)), SHARED)
    assert finish_times(result) == {"short": 1, "long": 2}
    # Swapping ids must not change which workload finishes when.
    swapped = simulate(servers, reqs((0, "long", 1, 1), (0, "short", 6, 1)), SHARED)
    assert finish_times(swapped) == {"long": 1, "short": 2}


def test_shared_uses_exact_fractions():
    assert cpu_share(10, 3) == Fraction(10, 3)
    assert cpu_share(10, 2) == 5 and isinstance(cpu_share(10, 2), int)
    # Three requests of 10 work on 10 CPU: 10/3 per tick -> 30/3 = 10 after exactly 3 ticks.
    result = simulate([srv("s1", 10, 1000, rate=3)], reqs((0, "a", 10, 1), (0, "b", 10, 1), (0, "c", 10, 1)), SHARED)
    assert finish_times(result) == {"a": 3, "b": 3, "c": 3}


def test_shared_alone_matches_exclusive_timing():
    servers = [srv("s1", 7, 1000)]
    requests = reqs((0, "a", 20, 1))
    assert finish_times(simulate(servers, requests)) == finish_times(simulate(servers, requests, SHARED)) == {"a": 3}


def test_shared_respects_total_memory():
    result = simulate([srv("s1", 10, 100, rate=5)], reqs((0, "a", 10, 60), (0, "b", 10, 60)), SHARED)
    assert [e.t for e in result.events if e.event == "REQUEST_STARTED"] == [0, 1]


def test_shared_respects_rate_limit():
    result = simulate([srv("s1", 10, 1000, rate=2)], reqs((0, "a", 100, 1), (0, "b", 100, 1), (0, "c", 100, 1)), SHARED)
    starts = {e.request_id: e.t for e in result.events if e.event == "REQUEST_STARTED"}
    assert starts == {"a": 0, "b": 0, "c": 1}


def test_estimate_runtime_accounts_for_current_load():
    state = ServerState(srv("s1", 10, 1000))
    req = reqs((0, "x", 20, 1))[0]
    model = SharedModel()
    assert model.estimate_runtime(state, req) == 2
    state.start(reqs((0, "y", 50, 1))[0], 0)
    assert model.estimate_runtime(state, req) == 4


# ----------------------------------------------------------------- scheduling


def test_earliest_finish_prefers_faster_server():
    result = simulate([srv("a_slow", 1, 1000), srv("b_fast", 10, 1000)], reqs((0, "r", 10, 1)))
    assert start_servers(result) == {"r": "b_fast"}


def test_ties_go_to_smallest_server_id():
    result = simulate([srv("s2", 10, 1000), srv("s1", 10, 1000)], reqs((0, "r", 10, 1)))
    assert start_servers(result) == {"r": "s1"}


def test_skip_ahead_past_a_request_that_does_not_fit():
    # big needs s_big (busy); small can still use s_small instead of waiting behind big.
    servers = [srv("s_big", 10, 1000), srv("s_small", 10, 100)]
    result = simulate(servers, reqs((0, "first", 50, 900), (1, "big", 10, 900), (1, "small", 10, 50)))
    starts = {e.request_id: (e.t, e.server_id) for e in result.events if e.event == "REQUEST_STARTED"}
    assert starts == {"first": (0, "s_big"), "small": (1, "s_small"), "big": (5, "s_big")}


def test_fifo_order_among_waiting_requests():
    result = simulate([srv("s1", 10, 1000)], reqs((0, "a", 10, 1), (0, "b", 10, 1), (0, "c", 10, 1)))
    assert [e.request_id for e in result.events if e.event == "REQUEST_STARTED"] == ["a", "b", "c"]


def test_same_tick_arrivals_follow_csv_row_order_not_id():
    result = simulate([srv("s1", 10, 1000)], reqs((0, "zeta", 10, 1), (0, "alpha", 10, 1)))
    assert [e.request_id for e in result.events if e.event == "REQUEST_STARTED"] == ["zeta", "alpha"]


def test_memory_freed_at_t_is_reusable_at_t():
    result = simulate([srv("s1", 10, 100)], reqs((0, "a", 10, 100), (0, "b", 10, 100)))
    assert finish_times(result)["a"] == 1
    assert [(e.t, e.request_id) for e in result.events if e.event == "REQUEST_STARTED"] == [(0, "a"), (1, "b")]


def test_fast_forward_over_idle_gaps():
    result = simulate([srv("s1", 10, 1000)], reqs((0, "a", 10, 1), (10**9, "b", 10, 1)))
    assert finish_times(result) == {"a": 1, "b": 10**9 + 1}


# ----------------------------------------------------------------- overload


def test_drop_when_no_server_fits():
    result = simulate([srv("s1", 10, 100)], reqs((0, "huge", 10, 101), (0, "ok", 10, 100)))
    assert trace(result)[:2] == [
        (0, "REQUEST_ARRIVED", "huge", None, None),
        (0, "REQUEST_DROPPED", "huge", None, "no_server_fits"),
    ]
    assert result.summary["dropped_by_reason"]["no_server_fits"] == 1


def test_max_wait_zero_means_start_now_or_drop():
    config = SimulationConfig(max_wait_ticks=0)
    result = simulate([srv("s1", 10, 1000)], reqs((0, "a", 10, 1), (0, "b", 10, 1)), config)
    assert (0, "REQUEST_DROPPED", "b", None, "max_wait_exceeded") in trace(result)


def test_max_wait_drops_after_waiting_that_long():
    config = SimulationConfig(max_wait_ticks=2)
    result = simulate([srv("s1", 10, 1000)], reqs((0, "a", 50, 1), (0, "b", 10, 1)), config)
    assert (2, "REQUEST_DROPPED", "b", None, "max_wait_exceeded") in trace(result)


def test_queue_full_drops_newest_first():
    config = SimulationConfig(max_queue_length=1)
    result = simulate([srv("s1", 10, 1000)], reqs((0, "a", 50, 1), (0, "b", 10, 1), (0, "c", 10, 1)), config)
    dropped = [(e.request_id, e.reason) for e in result.events if e.event == "REQUEST_DROPPED"]
    assert dropped == [("c", "queue_full")]


def test_queue_length_zero_still_allows_immediate_starts():
    config = SimulationConfig(max_queue_length=0)
    result = simulate([srv("s1", 10, 1000)], reqs((0, "a", 10, 1), (0, "b", 10, 1)), config)
    assert start_servers(result) == {"a": "s1"}
    assert result.summary["dropped_by_reason"]["queue_full"] == 1
