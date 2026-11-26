"""Starting runs and turning run rows into API responses (docs/high-level-design.md, "Run lifecycle")."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import engine as sim
from engine import InputError
from engine.loaders import validate_servers

from . import storage
from .db import RunRow, ServerRow
from .errors import ApiError
from .settings import Settings


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_config_field(raw: str | None) -> sim.SimulationConfig:
    try:
        data = json.loads(raw) if raw and raw.strip() else {}
    except json.JSONDecodeError as e:
        raise ApiError(422, f"config is not valid JSON: {e}", field="config") from None
    try:
        return sim.parse_config(data)
    except InputError as e:
        raise ApiError(422, str(e), field="config") from None


def parse_requests_upload(data: bytes, settings: Settings) -> list[sim.RequestSpec]:
    if len(data) > settings.max_upload_bytes:
        raise ApiError(413, f"requests file is larger than the {settings.max_upload_bytes:,} byte limit", "requests")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError(422, "requests file must be UTF-8 text", field="requests") from None
    try:
        requests = sim.parse_requests_csv(text)
    except InputError as e:
        raise ApiError(422, str(e), field="requests") from None
    if len(requests) > settings.max_request_rows:
        raise ApiError(
            413, f"requests file has {len(requests):,} rows; the limit is {settings.max_request_rows:,}", "requests"
        )
    return requests



def create_run(
    session: Session,
    settings: Settings,
    config_raw: str | None,
    upload: tuple[str | None, bytes] | None,
) -> RunRow:
    """POST /api/runs: the current servers, the sample or uploaded requests, and the given config."""
    # 1. Snapshot. Invalid input is rejected here, before any run row exists.
    config = parse_config_field(config_raw)
    if upload is None:
        source, filename = "sample", None
        requests = sim.load_requests(settings.fixtures_dir / "requests.csv")
    else:
        source, filename = "upload", upload[0]
        requests = parse_requests_upload(upload[1], settings)
    rows = session.scalars(select(ServerRow)).all()
    try:
        servers = validate_servers(sorted((r.to_spec() for r in rows), key=lambda s: s.id))
    except InputError as e:
        raise ApiError(422, f"{e}: add a server before starting a run", field="servers") from None
    return execute_run(session, settings, servers, requests, config, source, filename)


def rerun(session: Session, settings: Settings, original: RunRow) -> RunRow:
    """POST /api/runs/{id}/rerun: a new run from the saved snapshot of an earlier run, whatever the
    current servers are. With the same engine_version it must produce the same trace_hash."""
    path = storage.run_dir(settings.runs_dir, original.id)
    if not path.is_dir():
        raise ApiError(409, f"run #{original.id} has no saved inputs (status: {original.status})")
    servers = sim.load_servers(path / "servers.json")
    requests = sim.load_requests(path / "requests.csv")
    config = sim.load_config(path / "config.json")
    return execute_run(
        session, settings, servers, requests, config, original.requests_source, original.requests_filename
    )


def execute_run(
    session: Session,
    settings: Settings,
    servers: list[sim.ServerSpec],
    requests: list[sim.RequestSpec],
    config: sim.SimulationConfig,
    source: str,
    filename: str | None,
) -> RunRow:
    inputs = {
        "servers.json": storage.servers_text(servers),
        "requests.csv": storage.requests_text(requests),
        "config.json": storage.config_text(config),
    }

    # 2. Create the record; the database assigns the id.
    run = RunRow(
        created_at=_now(),
        status="pending",
        execution_mode=config.execution_mode,
        placement=config.placement,
        max_wait_ticks=config.max_wait_ticks,
        max_queue_length=config.max_queue_length,
        requests_source=source,
        requests_filename=filename,
        input_hash=storage.input_hash(inputs),
        engine_version=sim.__version__,
    )
    session.add(run)
    session.commit()

    # 3. Simulate and write the files. 4. Finish.
    try:
        result = sim.simulate(servers, requests, config)
        trace = sim.to_jsonl(result.events)
        summary = result.summary
        storage.write_run_dir(
            settings.runs_dir,
            run.id,
            {**inputs, "run.jsonl": trace, "summary.json": json.dumps(summary, indent=2) + "\n"},
        )
    except Exception as e:  # noqa: BLE001 - any failure marks the run as failed
        run.status = "failed"
        run.error = f"{type(e).__name__}: {e}"
        session.commit()
        raise ApiError(500, f"run #{run.id} failed: {run.error}") from e

    run.status = "completed"
    run.trace_hash = storage.sha256(trace)
    run.summary_json = json.dumps(summary)
    run.total_requests = summary["total_requests"]
    run.finished = summary["finished"]
    run.dropped = summary["dropped"]
    run.avg_wait_ticks = summary["avg_wait_ticks"]
    run.p95_wait_ticks = summary["p95_wait_ticks"]
    session.commit()
    return run


# --------------------------------------------------------------------------- responses


def output_key(run: RunRow) -> tuple[str, str, str | None]:
    return (run.input_hash, run.engine_version, run.trace_hash)


def same_output_map(runs: list[RunRow]) -> dict[int, int]:
    """run id -> id of the earliest earlier run with the same input_hash, engine_version and trace_hash."""
    first: dict[tuple[str, str, str | None], int] = {}
    result: dict[int, int] = {}
    for run in sorted(runs, key=lambda r: r.id):
        if run.status != "completed":
            continue
        key = output_key(run)
        if key in first:
            result[run.id] = first[key]
        else:
            first[key] = run.id
    return result


def same_output_as(session: Session, run: RunRow) -> int | None:
    if run.status != "completed":
        return None
    return session.scalars(
        select(RunRow.id)
        .where(
            RunRow.id < run.id,
            RunRow.status == "completed",
            RunRow.input_hash == run.input_hash,
            RunRow.engine_version == run.engine_version,
            RunRow.trace_hash == run.trace_hash,
        )
        .order_by(RunRow.id)
        .limit(1)
    ).first()


def run_to_dict(run: RunRow, same_as: int | None) -> dict[str, Any]:
    return {
        "id": run.id,
        "created_at": run.created_at,
        "status": run.status,
        "config": {
            "execution_mode": run.execution_mode,
            "placement": run.placement,
            "max_wait_ticks": run.max_wait_ticks,
            "max_queue_length": run.max_queue_length,
        },
        "requests_source": run.requests_source,
        "requests_filename": run.requests_filename,
        "summary": json.loads(run.summary_json) if run.summary_json else None,
        "input_hash": run.input_hash,
        "trace_hash": run.trace_hash,
        "engine_version": run.engine_version,
        "error": run.error,
        "same_output_as": same_as,
    }
