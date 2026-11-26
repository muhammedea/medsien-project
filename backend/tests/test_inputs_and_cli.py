"""Input validation (docs/engine-design.md section 8) and the CLI."""

import json

import pytest

from engine import InputError, SimulationConfig, parse_config, parse_requests_csv, parse_servers_document, simulate
from engine.cli import main
from tests.conftest import FIXTURES, reqs, srv

HEADER = "t,request_id,work_units,mem_mb\n"


def servers_doc(*servers, **extra):
    return {**extra, "servers": list(servers)}


GOOD_SERVER = {"id": "s1", "cpu_units_per_tick": 10, "mem_mb": 100, "rate_limit_per_sec": 1}


# ----------------------------------------------------------------- servers


def test_parses_servers_document():
    (s,) = parse_servers_document(servers_doc(GOOD_SERVER, tick_seconds=1))
    assert (s.id, s.cpu_units_per_tick, s.mem_mb, s.rate_limit_per_sec) == ("s1", 10, 100, 1)


@pytest.mark.parametrize(
    "doc, message",
    [
        (servers_doc(), "at least one server"),
        (servers_doc(GOOD_SERVER, GOOD_SERVER), "duplicate server id"),
        (servers_doc(GOOD_SERVER, tick_seconds=2), "tick_seconds"),
        (servers_doc({**GOOD_SERVER, "cpu_units_per_tick": 0}), "cpu_units_per_tick"),
        (servers_doc({**GOOD_SERVER, "rate_limit_per_sec": 0}), "rate_limit_per_sec"),
        (servers_doc({**GOOD_SERVER, "mem_mb": "100"}), "must be an integer"),
        (servers_doc({**GOOD_SERVER, "mem_mb": True}), "must be an integer"),
        (servers_doc({k: v for k, v in GOOD_SERVER.items() if k != "mem_mb"}), "missing fields"),
        (servers_doc({**GOOD_SERVER, "id": " "}), "server id"),
        ({"no_servers": []}, "'servers' list"),
    ],
)
def test_rejects_bad_servers(doc, message):
    with pytest.raises(InputError, match=message):
        parse_servers_document(doc)


# ----------------------------------------------------------------- requests


def test_trims_ids_and_keeps_csv_row_order():
    rs = parse_requests_csv(HEADER + "5, r2 ,10,0\n0,r1,10,5\n")
    assert [(r.id, r.arrival_t, r.row) for r in rs] == [("r2", 5, 0), ("r1", 0, 1)]


@pytest.mark.parametrize(
    "text, message",
    [
        (HEADER, "no request rows"),
        ("t,request_id,work_units\n0,r1,10\n", "missing columns"),
        (HEADER + "0,  ,10,5\n", "request_id is blank"),
        (HEADER + "0,r1,10,5\n0, r1,10,5\n", "duplicate request_id"),
        (HEADER + "0,r1,0,5\n", "work_units must be >= 1"),
        (HEADER + "-1,r1,10,5\n", "t must be >= 0"),
        (HEADER + "0,r1,10,-5\n", "mem_mb must be >= 0"),
        (HEADER + "0,r1,1.5,5\n", "must be an integer"),
    ],
)
def test_rejects_bad_requests(text, message):
    with pytest.raises(InputError, match=message):
        parse_requests_csv(text)


# ----------------------------------------------------------------- config


@pytest.mark.parametrize(
    "data, message",
    [
        ({"execution_mode": "parallel"}, "execution_mode"),
        ({"placement": "random"}, "placement"),
        ({"max_wait_ticks": -1}, "max_wait_ticks"),
        ({"max_queue_length": -1}, "max_queue_length"),
        ({"surprise": 1}, "unknown config fields"),
    ],
)
def test_rejects_bad_config(data, message):
    with pytest.raises(InputError, match=message):
        parse_config(data)


def test_zero_limits_are_valid():
    assert parse_config({"max_wait_ticks": 0, "max_queue_length": 0}) == SimulationConfig(
        max_wait_ticks=0, max_queue_length=0
    )


def test_simulate_validates_its_arguments():
    with pytest.raises(InputError, match="duplicate request_id"):
        simulate([srv("s1", 1, 1)], reqs((0, "a", 1, 1), (0, "a", 1, 1)))


# ----------------------------------------------------------------- CLI


def run_cli(tmp_path, *extra):
    out = tmp_path / "run.jsonl"
    code = main(
        ["--servers", str(FIXTURES / "servers.json"), "--requests", str(FIXTURES / "requests.csv"),
         "--out", str(out), "--quiet", *extra]
    )
    return code, out


def test_cli_writes_trace_and_overwrites(tmp_path):
    code, out = run_cli(tmp_path)
    assert code == 0
    first = out.read_bytes()
    out.write_text("stale\n")
    code, out = run_cli(tmp_path)
    assert code == 0 and out.read_bytes() == first


def test_cli_flags_override_config_file(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"execution_mode": "exclusive", "max_wait_ticks": 0}))
    code, out = run_cli(tmp_path, "--config", str(config), "--mode", "shared")
    assert code == 0
    events = [json.loads(line) for line in out.read_text().splitlines()]
    # Shared mode + max_wait 0: r1 and r2 both start on s1 at t=0 (rate limit 2).
    assert [(e["request_id"], e["server_id"]) for e in events if e["event"] == "REQUEST_STARTED"][:2] == [
        ("r1", "s1"),
        ("r2", "s1"),
    ]


def test_cli_reports_input_errors(tmp_path, capsys):
    bad = tmp_path / "requests.csv"
    bad.write_text(HEADER)
    code = main(["--servers", str(FIXTURES / "servers.json"), "--requests", str(bad), "--out", str(tmp_path / "x")])
    assert code == 1
    assert "no request rows" in capsys.readouterr().err
