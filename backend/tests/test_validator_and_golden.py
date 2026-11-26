"""The sample trace, the original validator on many random cases, and determinism."""

import dataclasses
import json

import pytest

from engine import SimulationConfig, load_requests, load_servers, simulate, to_jsonl
from tests.conftest import (
    BACKEND_DIR,
    FIXTURES,
    TEST_DATA,
    assert_lifecycle,
    assert_resources,
    random_case,
    run_validator,
)


def _event_set(lines):
    return sorted(json.dumps(json.loads(line), sort_keys=True) for line in lines if line.strip())


def test_sample_matches_provided_trace():
    servers = load_servers(FIXTURES / "servers.json")
    requests = load_requests(FIXTURES / "requests.csv")
    result = simulate(servers, requests)
    expected = (TEST_DATA / "expected_sample_run.jsonl").read_text().splitlines()
    # Same events as the provided run.jsonl; line order within a tick may differ.
    assert _event_set(to_jsonl(result.events).splitlines()) == _event_set(expected)
    ok, issues, _ = run_validator(servers, requests, result.events)
    assert ok, issues


def test_committed_example_is_up_to_date():
    example = BACKEND_DIR.parent / "examples" / "run.jsonl"
    if not example.exists():  # not part of the backend Docker build context
        pytest.skip("examples/run.jsonl not available")
    result = simulate(load_servers(FIXTURES / "servers.json"), load_requests(FIXTURES / "requests.csv"))
    assert example.read_text() == to_jsonl(result.events), "regenerate examples/run.jsonl with the CLI"


@pytest.mark.parametrize("seed", range(300))
def test_random_exclusive_runs_pass_original_validator(seed):
    servers, requests, config = random_case(seed)
    result = simulate(servers, requests, config)
    ok, issues, summary = run_validator(servers, requests, result.events)
    assert ok, [i.msg for i in issues if i.level == "ERROR"]
    assert_lifecycle(requests, result.events)
    assert_resources(servers, requests, result.events)
    assert summary["started"] == result.summary["started"]
    assert summary["dropped"] == result.summary["dropped"]
    assert summary["p95_wait_ticks"] == result.summary["p95_wait_ticks"]


@pytest.mark.parametrize("seed", range(300))
def test_random_shared_runs_respect_resources(seed):
    servers, requests, config = random_case(seed)
    result = simulate(servers, requests, dataclasses.replace(config, execution_mode="shared"))
    assert_lifecycle(requests, result.events)
    assert_resources(servers, requests, result.events)


@pytest.mark.parametrize("mode", ["exclusive", "shared"])
@pytest.mark.parametrize("seed", range(20))
def test_same_input_gives_byte_identical_output(seed, mode):
    servers, requests, config = random_case(seed)
    config = dataclasses.replace(config, execution_mode=mode)
    first = to_jsonl(simulate(servers, requests, config).events)
    # Different list order for servers; rows keep their CSV index, so the input is the same.
    second = to_jsonl(simulate(list(reversed(servers)), list(reversed(requests)), config).events)
    assert first == second


@pytest.mark.parametrize("mode", ["exclusive", "shared"])
@pytest.mark.parametrize("seed", range(300))
def test_skipping_ticks_never_changes_output(seed, mode):
    servers, requests, config = random_case(seed)
    config = dataclasses.replace(config, execution_mode=mode)
    assert simulate(servers, requests, config).events == simulate(
        servers, requests, config, step_every_tick=True
    ).events


def test_default_config_is_exclusive():
    assert SimulationConfig().execution_mode == "exclusive"
