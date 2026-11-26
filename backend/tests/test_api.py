"""The HTTP API: server CRUD, runs, downloads, events and the timeline."""

from __future__ import annotations

import json
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import Settings
from api.timeline import derive_timeline
from engine import load_requests, load_servers, parse_requests_csv, parse_servers_document, simulate
from engine.output import event_to_dict
from tests.conftest import FIXTURES, TEST_DATA, random_case
from validator import validate_run as V

HEADER = "t,request_id,work_units,mem_mb\n"


@pytest.fixture
def make_client(tmp_path):
    clients = []

    def _make(**overrides) -> TestClient:
        settings = Settings(data_dir=tmp_path / "data", **overrides)
        client = TestClient(create_app(settings))
        client.__enter__()  # runs the lifespan: creates the database and seeds the servers
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def start_run(client, config=None, csv_text=None, filename="requests.csv"):
    files = {"requests": (filename, csv_text.encode(), "text/csv")} if csv_text is not None else None
    return client.post("/api/runs", data={"config": json.dumps(config or {})}, files=files)


def validate_files(client, run_id) -> tuple[bool, list]:
    """Run the original validator on the run's saved inputs and trace."""
    servers_doc = client.get(f"/api/runs/{run_id}/inputs/servers.json").json()
    csv_text = client.get(f"/api/runs/{run_id}/inputs/requests.csv").text
    events = [json.loads(line) for line in client.get(f"/api/runs/{run_id}/run.jsonl").text.splitlines()]
    v_servers = {
        s.id: V.ServerSpec(s.id, s.cpu_units_per_tick, s.mem_mb, s.rate_limit_per_sec)
        for s in parse_servers_document(servers_doc)
    }
    v_requests = {r.id: V.RequestSpec(r.id, r.arrival_t, r.work_units, r.mem_mb) for r in parse_requests_csv(csv_text)}
    ok, issues, _ = V.validate(v_servers, v_requests, events)
    return ok, issues


# ----------------------------------------------------------------- servers


def test_servers_are_seeded_from_fixtures(client):
    servers = client.get("/api/servers").json()
    assert [s["id"] for s in servers] == ["s1", "s2"]
    assert servers[0] == {"id": "s1", "cpu_units_per_tick": 10, "mem_mb": 1024, "rate_limit_per_sec": 2}


def test_server_crud(client):
    new = {"id": "s3", "cpu_units_per_tick": 4, "mem_mb": 256, "rate_limit_per_sec": 1}
    assert client.post("/api/servers", json=new).status_code == 201
    r = client.put("/api/servers/s3", json={"cpu_units_per_tick": 8, "mem_mb": 256, "rate_limit_per_sec": 3})
    assert r.status_code == 200 and r.json()["cpu_units_per_tick"] == 8
    assert [s["id"] for s in client.get("/api/servers").json()] == ["s1", "s2", "s3"]
    assert client.delete("/api/servers/s3").status_code == 204
    assert client.delete("/api/servers/s3").status_code == 404
    assert client.put("/api/servers/nope", json=new).status_code == 404


@pytest.mark.parametrize(
    "body, field",
    [
        ({"id": "s1", "cpu_units_per_tick": 1, "mem_mb": 1, "rate_limit_per_sec": 1}, "id"),  # duplicate
        ({"id": " ", "cpu_units_per_tick": 1, "mem_mb": 1, "rate_limit_per_sec": 1}, "id"),
        ({"id": "x", "cpu_units_per_tick": 0, "mem_mb": 1, "rate_limit_per_sec": 1}, "cpu_units_per_tick"),
        ({"id": "x", "cpu_units_per_tick": 1, "mem_mb": "5", "rate_limit_per_sec": 1}, "mem_mb"),
        ({"id": "x", "cpu_units_per_tick": 1, "mem_mb": 1, "rate_limit_per_sec": 1.5}, "rate_limit_per_sec"),
    ],
)
def test_server_validation_errors_name_the_field(client, body, field):
    r = client.post("/api/servers", json=body)
    assert r.status_code == 422
    assert r.json()["field"] == field


def test_server_id_cannot_change(client):
    r = client.put("/api/servers/s1", json={"id": "s9", "cpu_units_per_tick": 1, "mem_mb": 1, "rate_limit_per_sec": 1})
    assert r.status_code == 422 and r.json()["field"] == "id"


def test_deleted_servers_are_not_reseeded(make_client):
    client = make_client()
    client.delete("/api/servers/s1")
    client.delete("/api/servers/s2")
    assert make_client().get("/api/servers").json() == []


# ----------------------------------------------------------------- runs


def test_default_run_reproduces_the_sample_and_passes_the_validator(client):
    r = start_run(client)
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "completed"
    assert run["config"] == {
        "execution_mode": "exclusive",
        "placement": "earliest_finish",
        "max_wait_ticks": None,
        "max_queue_length": None,
    }
    assert run["summary"]["finished"] == 4 and run["summary"]["dropped"] == 0
    trace = client.get(f"/api/runs/{run['id']}/run.jsonl").text
    expected = (TEST_DATA / "expected_sample_run.jsonl").read_text()
    as_set = lambda text: sorted(json.dumps(json.loads(x), sort_keys=True) for x in text.splitlines() if x.strip())  # noqa: E731
    assert as_set(trace) == as_set(expected)
    ok, issues = validate_files(client, run["id"])
    assert ok, issues


def test_rerun_gives_same_hashes_and_badge(client):
    first = start_run(client).json()
    start_run(client, config={"max_wait_ticks": 0})  # different input in between
    third = start_run(client).json()
    assert third["input_hash"] == first["input_hash"]
    assert third["trace_hash"] == first["trace_hash"]
    assert third["same_output_as"] == first["id"]
    runs = client.get("/api/runs").json()
    assert [r["id"] for r in runs] == [3, 2, 1]
    assert [r["same_output_as"] for r in runs] == [1, None, None]
    assert client.get("/api/runs/3").json()["same_output_as"] == 1


def test_upload_with_reordered_whitespace_rows_hashes_like_its_canonical_form(client):
    a = start_run(client, csv_text=HEADER + "0, r1 ,20,200\n").json()
    b = start_run(client, csv_text=HEADER + "0,r1,20,200").json()
    assert a["input_hash"] == b["input_hash"]
    assert client.get(f"/api/runs/{a['id']}/inputs/requests.csv").text == HEADER + "0,r1,20,200\n"


def test_server_edits_only_affect_later_runs(client):
    run = start_run(client).json()
    client.put("/api/servers/s1", json={"cpu_units_per_tick": 1, "mem_mb": 1024, "rate_limit_per_sec": 2})
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["servers"][0]["cpu_units_per_tick"] == 10
    assert start_run(client).json()["input_hash"] != run["input_hash"]


def test_shared_mode_and_saved_config(client):
    run = start_run(client, config={"execution_mode": "shared", "max_queue_length": 5}).json()
    assert run["config"]["execution_mode"] == "shared"
    config = client.get(f"/api/runs/{run['id']}/inputs/config.json").json()
    assert config == {
        "execution_mode": "shared",
        "placement": "earliest_finish",
        "max_wait_ticks": None,
        "max_queue_length": 5,
    }


@pytest.mark.parametrize(
    "kwargs, field, fragment",
    [
        ({"csv_text": HEADER + "0,r1,20,200\n0,r2,abc,1\n"}, "requests", "line 3"),
        ({"csv_text": "a,b\n1,2\n"}, "requests", "missing columns"),
        ({"config": {"max_wait_ticks": -1}}, "config", "max_wait_ticks"),
        ({"config": {"execution_mode": "fast"}}, "config", "execution_mode"),
    ],
)
def test_invalid_run_input_is_422_and_creates_no_run(client, kwargs, field, fragment):
    r = start_run(client, **kwargs)
    assert r.status_code == 422
    assert r.json()["field"] == field and fragment in r.json()["detail"]
    assert client.get("/api/runs").json() == []


def test_invalid_config_json(client):
    r = client.post("/api/runs", data={"config": "{not json"})
    assert r.status_code == 422 and r.json()["field"] == "config"


def test_upload_limits_give_413(make_client):
    client = make_client(max_upload_bytes=60, max_request_rows=2)
    assert client.get("/api/limits").json() == {"max_upload_bytes": 60, "max_request_rows": 2}
    too_many = HEADER + "0,a,1,1\n0,b,1,1\n0,c,1,1\n"
    assert start_run(client, csv_text=too_many).status_code == 413
    too_big = HEADER + "".join(f"0,request-{i},1,1\n" for i in range(5))
    assert start_run(client, csv_text=too_big).status_code == 413


def test_run_without_servers_is_422(client):
    client.delete("/api/servers/s1")
    client.delete("/api/servers/s2")
    r = start_run(client)
    assert r.status_code == 422 and r.json()["field"] == "servers"


def test_unknown_run_and_input(client):
    assert client.get("/api/runs/99").status_code == 404
    run = start_run(client).json()
    assert client.get(f"/api/runs/{run['id']}/inputs/secrets.txt").status_code == 404


def test_sample_csv_download(client):
    r = client.get("/api/samples/requests.csv")
    assert r.status_code == 200 and r.text == (FIXTURES / "requests.csv").read_text()


# ----------------------------------------------------------------- events


def test_events_pagination_and_filters(client):
    run_id = start_run(client).json()["id"]
    page = client.get(f"/api/runs/{run_id}/events", params={"limit": 3}).json()
    assert page["total"] == 12 and [e["line"] for e in page["items"]] == [1, 2, 3]
    page2 = client.get(f"/api/runs/{run_id}/events", params={"limit": 3, "offset": 9}).json()
    assert [e["line"] for e in page2["items"]] == [10, 11, 12]
    r1 = client.get(f"/api/runs/{run_id}/events", params={"request_id": "r1"}).json()
    assert [e["event"] for e in r1["items"]] == ["REQUEST_ARRIVED", "REQUEST_STARTED", "REQUEST_FINISHED"]
    s2_starts = client.get(f"/api/runs/{run_id}/events", params={"server_id": "s2", "event": "REQUEST_STARTED"}).json()
    assert [e["request_id"] for e in s2_starts["items"]] == ["r2", "r4"]
    at_2 = client.get(f"/api/runs/{run_id}/events", params={"t": 2}).json()
    assert {e["t"] for e in at_2["items"]} == {2} and at_2["total"] == 5


# ----------------------------------------------------------------- timeline


def test_timeline_for_the_sample(client):
    run_id = start_run(client).json()["id"]
    tl = client.get(f"/api/runs/{run_id}/timeline").json()
    assert tl["mode"] == "exclusive" and tl["last_tick"] == 4
    by_id = {r["id"]: r for r in tl["requests"]}
    assert by_id["r3"] == {
        "id": "r3", "arrival": 1, "work_units": 15, "mem_mb": 300,
        "server_id": "s1", "start": 2, "finish": 4, "drop_t": None, "drop_reason": None,
    }  # fmt: skip
    assert tl["series"] == [
        {"t": 0, "queued": 0, "running": 2, "dropped_total": 0, "mem_used": {"s1": 200, "s2": 100}},
        {"t": 1, "queued": 1, "running": 2, "dropped_total": 0, "mem_used": {"s1": 200, "s2": 100}},
        {"t": 2, "queued": 0, "running": 2, "dropped_total": 0, "mem_used": {"s1": 300, "s2": 100}},
        {"t": 3, "queued": 0, "running": 1, "dropped_total": 0, "mem_used": {"s1": 300, "s2": 0}},
        {"t": 4, "queued": 0, "running": 0, "dropped_total": 0, "mem_used": {"s1": 0, "s2": 0}},
    ]


@pytest.mark.parametrize("mode", ["exclusive", "shared"])
@pytest.mark.parametrize("seed", range(40))
def test_timeline_matches_an_independent_per_tick_count(seed, mode):
    """Cross-check derive_timeline against a brute-force count over every tick."""
    import dataclasses

    servers, requests, config = random_case(seed)
    config = dataclasses.replace(config, execution_mode=mode)
    events = [event_to_dict(e) for e in simulate(servers, requests, config).events]
    tl = derive_timeline(sorted(servers, key=lambda s: s.id), requests, config, events, zoom_threshold=10**9)
    by_id = {r["id"]: r for r in tl["requests"]}

    # Every request has a consistent outcome.
    for r in tl["requests"]:
        assert (r["start"] is None) == (r["finish"] is None) == (r["drop_t"] is not None)

    # The series, expanded to every tick, matches a direct count from the request list.
    expanded, current = {}, None
    entries = {e["t"]: e for e in tl["series"]}
    for t in range(tl["first_tick"], tl["last_tick"] + 1):
        current = entries.get(t, current)
        expanded[t] = current
    spec = {s.id: s for s in servers}
    for t, entry in expanded.items():
        queued = sum(
            1 for r in by_id.values()
            if r["arrival"] <= t
            and not (r["start"] is not None and r["start"] <= t)
            and not (r["drop_t"] is not None and r["drop_t"] <= t)
        )  # fmt: skip
        running = [r for r in by_id.values() if r["start"] is not None and r["start"] <= t < r["finish"]]
        mem = defaultdict(int)
        for r in running:
            mem[r["server_id"]] += r["mem_mb"]
        dropped = sum(1 for r in by_id.values() if r["drop_t"] is not None and r["drop_t"] <= t)
        assert (entry["queued"], entry["running"], entry["dropped_total"]) == (queued, len(running), dropped), t
        for sid, used in entry["mem_used"].items():
            assert used == mem[sid] and used <= spec[sid].mem_mb


def test_large_runs_start_zoomed_in():
    servers = load_servers(FIXTURES / "servers.json")
    requests = load_requests(FIXTURES / "requests.csv")
    events = [event_to_dict(e) for e in simulate(servers, requests).events]
    from engine import SimulationConfig

    tl = derive_timeline(servers, requests, SimulationConfig(), events, zoom_threshold=2)
    assert tl["initial_view"] == {"start": 0, "end": 1}  # covers the first two arrivals (t=0), at least 1 tick wide


def test_rerun_uses_the_saved_snapshot_not_the_current_servers(client):
    first = start_run(client, config={"execution_mode": "shared"}).json()
    client.put("/api/servers/s1", json={"cpu_units_per_tick": 1, "mem_mb": 1024, "rate_limit_per_sec": 2})
    client.delete("/api/servers/s2")
    again = client.post(f"/api/runs/{first['id']}/rerun")
    assert again.status_code == 201, again.text
    again = again.json()
    assert again["id"] != first["id"]
    assert again["config"]["execution_mode"] == "shared"
    assert (again["input_hash"], again["trace_hash"]) == (first["input_hash"], first["trace_hash"])
    assert again["same_output_as"] == first["id"]
    assert client.post("/api/runs/99/rerun").status_code == 404
