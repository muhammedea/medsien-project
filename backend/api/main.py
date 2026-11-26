"""FastAPI application: server CRUD, runs, downloads and visualization data.

See docs/high-level-design.md ("API") for the endpoint list and docs/ui-requirements.md for
the screens that use them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Body, Depends, FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import engine as sim
from engine.loaders import SERVER_FIELDS, validate_servers

from . import storage
from .db import RunRow, ServerRow, init_db, make_engine
from .errors import ApiError, register_error_handlers
from .runs import create_run, rerun, run_to_dict, same_output_as, same_output_map
from .settings import Settings
from .timeline import build_timeline, read_events


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings or Settings.from_env()
    app.state.settings = settings
    db_engine = make_engine(settings.db_path)
    app.state.sessions = init_db(db_engine, settings.fixtures_dir)
    yield
    db_engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Load Balancer Simulation API", version=sim.__version__, lifespan=lifespan)
    app.state.settings = settings
    register_error_handlers(app)
    _add_routes(app)
    return app


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


# --------------------------------------------------------------------------- helpers


def _server_dict(row: ServerRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "cpu_units_per_tick": row.cpu_units_per_tick,
        "mem_mb": row.mem_mb,
        "rate_limit_per_sec": row.rate_limit_per_sec,
    }


def _server_error_field(message: str) -> str | None:
    """Which form field an engine InputError about a server concerns, for showing it inline."""
    for field in ("cpu_units_per_tick", "rate_limit_per_sec", "mem_mb"):
        if field in message:
            return field
    if "server id" in message or "duplicate" in message:
        return "id"
    return None


def _parse_server(body: Any) -> sim.ServerSpec:
    try:
        return sim.parse_server(body)
    except sim.InputError as e:
        raise ApiError(422, str(e), field=_server_error_field(str(e))) from None


def _get_run(session: Session, run_id: int) -> RunRow:
    run = session.get(RunRow, run_id)
    if run is None:
        raise ApiError(404, f"run #{run_id} not found")
    return run


def _completed_run_dir(session: Session, settings: Settings, run_id: int):
    run = _get_run(session, run_id)
    path = storage.run_dir(settings.runs_dir, run.id)
    if run.status != "completed" or not path.is_dir():
        raise ApiError(409, f"run #{run_id} has no output (status: {run.status})")
    return path


# --------------------------------------------------------------------------- routes


def _add_routes(app: FastAPI) -> None:
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine_version": sim.__version__}

    @app.get("/api/limits")
    def limits(settings: SettingsDep) -> dict[str, int]:
        """Upload limits for POST /api/runs, so the browser can check them early."""
        return {"max_upload_bytes": settings.max_upload_bytes, "max_request_rows": settings.max_request_rows}

    # ----------------------------------------------------------------- servers

    @app.get("/api/servers")
    def list_servers(session: SessionDep) -> list[dict[str, Any]]:
        rows = session.scalars(select(ServerRow)).all()
        return [_server_dict(r) for r in sorted(rows, key=lambda r: r.id)]

    @app.post("/api/servers", status_code=201)
    def create_server(session: SessionDep, body: Annotated[Any, Body()]) -> dict[str, Any]:
        spec = _parse_server(body)
        existing = [r.to_spec() for r in session.scalars(select(ServerRow)).all()]
        try:
            validate_servers([*existing, spec])  # the engine's rule for unique ids
        except sim.InputError as e:
            raise ApiError(422, str(e), field="id") from None
        row = ServerRow(**{f: getattr(spec, f) for f in SERVER_FIELDS})
        session.add(row)
        session.commit()
        return _server_dict(row)

    @app.put("/api/servers/{server_id}")
    def update_server(server_id: str, session: SessionDep, body: Annotated[Any, Body()]) -> dict[str, Any]:
        row = session.get(ServerRow, server_id)
        if row is None:
            raise ApiError(404, f"server '{server_id}' not found")
        if isinstance(body, dict) and "id" in body and body["id"] != server_id:
            raise ApiError(422, "the server id can't be changed", field="id")
        spec = _parse_server({**body, "id": server_id} if isinstance(body, dict) else body)
        row.cpu_units_per_tick = spec.cpu_units_per_tick
        row.mem_mb = spec.mem_mb
        row.rate_limit_per_sec = spec.rate_limit_per_sec
        session.commit()
        return _server_dict(row)

    @app.delete("/api/servers/{server_id}", status_code=204)
    def delete_server(server_id: str, session: SessionDep) -> Response:
        row = session.get(ServerRow, server_id)
        if row is None:
            raise ApiError(404, f"server '{server_id}' not found")
        session.delete(row)
        session.commit()
        return Response(status_code=204)

    # ----------------------------------------------------------------- runs

    @app.post("/api/runs", status_code=201)
    def start_run(
        session: SessionDep,
        settings: SettingsDep,
        config: Annotated[str, Form(description="SimulationConfig fields as JSON")] = "{}",
        requests: Annotated[UploadFile | None, File(description="requests.csv; the sample is used when omitted")] = None,
    ) -> dict[str, Any]:
        upload = None
        if requests is not None:
            # Read one byte past the limit, so an oversized file is detected without reading all of it.
            upload = (requests.filename, requests.file.read(settings.max_upload_bytes + 1))
        run = create_run(session, settings, config, upload)
        return run_to_dict(run, same_output_as(session, run))

    @app.post("/api/runs/{run_id}/rerun", status_code=201)
    def rerun_run(run_id: int, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
        """Start a new run from the saved inputs (servers, requests, config) of an earlier run."""
        run = rerun(session, settings, _get_run(session, run_id))
        return run_to_dict(run, same_output_as(session, run))

    @app.get("/api/runs")
    def list_runs(session: SessionDep) -> list[dict[str, Any]]:
        runs = list(session.scalars(select(RunRow)).all())
        same = same_output_map(runs)
        return [run_to_dict(r, same.get(r.id)) for r in sorted(runs, key=lambda r: r.id, reverse=True)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
        run = _get_run(session, run_id)
        result = run_to_dict(run, same_output_as(session, run))
        servers_file = storage.run_dir(settings.runs_dir, run.id) / "servers.json"
        result["servers"] = (
            [
                {f: getattr(s, f) for f in SERVER_FIELDS}
                for s in sorted(sim.load_servers(servers_file), key=lambda s: s.id)
            ]
            if servers_file.is_file()
            else None
        )
        return result

    @app.get("/api/runs/{run_id}/run.jsonl")
    def download_trace(run_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
        path = _completed_run_dir(session, settings, run_id) / "run.jsonl"
        return FileResponse(path, media_type="application/x-ndjson", filename="run.jsonl")

    @app.get("/api/runs/{run_id}/inputs/{name}")
    def download_input(run_id: int, name: str, session: SessionDep, settings: SettingsDep) -> FileResponse:
        if name not in storage.INPUT_FILES:
            raise ApiError(404, f"unknown input file '{name}'; expected one of {', '.join(storage.INPUT_FILES)}")
        path = _completed_run_dir(session, settings, run_id) / name
        media = "text/csv" if name.endswith(".csv") else "application/json"
        return FileResponse(path, media_type=media, filename=name)

    @app.get("/api/runs/{run_id}/events")
    def list_events(
        run_id: int,
        session: SessionDep,
        settings: SettingsDep,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        event: str | None = None,
        request_id: str | None = None,
        server_id: str | None = None,
        t: int | None = None,
    ) -> dict[str, Any]:
        """The lines of run.jsonl, in written order, with optional exact-match filters."""
        path = _completed_run_dir(session, settings, run_id) / "run.jsonl"
        rows = [{"line": i + 1, **ev} for i, ev in enumerate(read_events(path))]
        filters = {"event": event, "request_id": request_id, "server_id": server_id, "t": t}
        for key, value in filters.items():
            if value is not None and value != "":
                rows = [r for r in rows if r.get(key) == value]
        return {"total": len(rows), "offset": offset, "limit": limit, "items": rows[offset : offset + limit]}

    @app.get("/api/runs/{run_id}/timeline")
    def timeline(run_id: int, session: SessionDep, settings: SettingsDep) -> dict[str, Any]:
        path = _completed_run_dir(session, settings, run_id)
        return build_timeline(path, settings.timeline_zoom_threshold)

    # ----------------------------------------------------------------- samples

    @app.get("/api/samples/requests.csv")
    def sample_requests(settings: SettingsDep) -> FileResponse:
        return FileResponse(settings.fixtures_dir / "requests.csv", media_type="text/csv", filename="requests.csv")


app = create_app()
