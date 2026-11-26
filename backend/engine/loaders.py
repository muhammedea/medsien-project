"""Parsing and validation of engine inputs.

This module is the single place where input rules live. The CLI and the API both
go through it, and simulate() re-checks its arguments with the same functions.
All problems are reported as InputError.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import (
    EXECUTION_MODES,
    PLACEMENT_NAMES,
    InputError,
    RequestSpec,
    ServerSpec,
    SimulationConfig,
)

REQUEST_COLUMNS = ("t", "request_id", "work_units", "mem_mb")
SERVER_FIELDS = ("id", "cpu_units_per_tick", "mem_mb", "rate_limit_per_sec")
CONFIG_FIELDS = ("execution_mode", "placement", "max_wait_ticks", "max_queue_length")


# --------------------------------------------------------------------------- helpers


def _require_int(value: Any, what: str, minimum: int) -> int:
    # bool is a subclass of int; reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"{what} must be an integer, got {value!r}")
    if value < minimum:
        raise InputError(f"{what} must be >= {minimum}, got {value}")
    return value


def _parse_csv_int(raw: str | None, what: str, minimum: int) -> int:
    text = (raw or "").strip()
    try:
        value = int(text)
    except ValueError:
        raise InputError(f"{what} must be an integer, got {raw!r}") from None
    return _require_int(value, what, minimum)


# --------------------------------------------------------------------------- servers


def validate_server(server: ServerSpec) -> ServerSpec:
    if not isinstance(server.id, str) or not server.id.strip():
        raise InputError(f"server id must be a non-empty string, got {server.id!r}")
    _require_int(server.cpu_units_per_tick, f"server '{server.id}' cpu_units_per_tick", 1)
    _require_int(server.mem_mb, f"server '{server.id}' mem_mb", 1)
    _require_int(server.rate_limit_per_sec, f"server '{server.id}' rate_limit_per_sec", 1)
    return server


def validate_servers(servers: Iterable[ServerSpec]) -> list[ServerSpec]:
    result = [validate_server(s) for s in servers]
    if not result:
        raise InputError("at least one server is required")
    seen: set[str] = set()
    for s in result:
        if s.id in seen:
            raise InputError(f"duplicate server id '{s.id}'")
        seen.add(s.id)
    return result


def parse_server(data: Mapping[str, Any]) -> ServerSpec:
    if not isinstance(data, Mapping):
        raise InputError(f"each server must be an object, got {data!r}")
    missing = [f for f in SERVER_FIELDS if f not in data]
    if missing:
        raise InputError(f"server {data.get('id', '?')!r} is missing fields: {', '.join(missing)}")
    return validate_server(
        ServerSpec(
            id=data["id"],
            cpu_units_per_tick=data["cpu_units_per_tick"],
            mem_mb=data["mem_mb"],
            rate_limit_per_sec=data["rate_limit_per_sec"],
        )
    )


def parse_servers_document(data: Any) -> list[ServerSpec]:
    """Parse the servers.json structure: {"tick_seconds": 1, "servers": [...]}."""
    if not isinstance(data, Mapping):
        raise InputError("servers.json must contain a JSON object")
    if "tick_seconds" in data and data["tick_seconds"] != 1:
        raise InputError(f"tick_seconds must be 1, got {data['tick_seconds']!r}")
    raw = data.get("servers")
    if not isinstance(raw, list):
        raise InputError("servers.json must contain a 'servers' list")
    return validate_servers(parse_server(s) for s in raw)


def load_servers(path: str | Path) -> list[ServerSpec]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise InputError(f"cannot read servers file: {e}") from None
    except json.JSONDecodeError as e:
        raise InputError(f"servers file is not valid JSON: {e}") from None
    return parse_servers_document(data)


# --------------------------------------------------------------------------- requests


def validate_request(req: RequestSpec) -> RequestSpec:
    if not isinstance(req.id, str) or not req.id or req.id != req.id.strip():
        raise InputError(f"request_id must be a non-empty, trimmed string, got {req.id!r}")
    _require_int(req.arrival_t, f"request '{req.id}' t", 0)
    _require_int(req.work_units, f"request '{req.id}' work_units", 1)
    _require_int(req.mem_mb, f"request '{req.id}' mem_mb", 0)
    _require_int(req.row, f"request '{req.id}' row", 0)
    return req


def validate_requests(requests: Iterable[RequestSpec]) -> list[RequestSpec]:
    result = [validate_request(r) for r in requests]
    if not result:
        raise InputError("at least one request is required")
    seen_ids: set[str] = set()
    seen_rows: set[int] = set()
    for r in result:
        if r.id in seen_ids:
            raise InputError(f"duplicate request_id '{r.id}'")
        if r.row in seen_rows:
            raise InputError(f"duplicate row index {r.row} (request '{r.id}')")
        seen_ids.add(r.id)
        seen_rows.add(r.row)
    return result


def parse_requests_csv(text: str) -> list[RequestSpec]:
    """Parse requests.csv content. Rows may be in any order; row index is kept for tie-breaks."""
    reader = csv.DictReader(io.StringIO(text))
    fields = [f.strip() for f in (reader.fieldnames or [])]
    missing = [c for c in REQUEST_COLUMNS if c not in fields]
    if missing:
        raise InputError(f"requests.csv is missing columns: {', '.join(missing)}")
    reader.fieldnames = fields

    requests: list[RequestSpec] = []
    for row_index, row in enumerate(reader):
        line = row_index + 2  # header is line 1
        rid = (row.get("request_id") or "").strip()
        if not rid:
            raise InputError(f"requests.csv line {line}: request_id is blank")
        requests.append(
            RequestSpec(
                id=rid,
                arrival_t=_parse_csv_int(row.get("t"), f"requests.csv line {line} t", 0),
                work_units=_parse_csv_int(row.get("work_units"), f"requests.csv line {line} work_units", 1),
                mem_mb=_parse_csv_int(row.get("mem_mb"), f"requests.csv line {line} mem_mb", 0),
                row=row_index,
            )
        )
    if not requests:
        raise InputError("requests.csv has no request rows")
    return validate_requests(requests)


def load_requests(path: str | Path) -> list[RequestSpec]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise InputError(f"cannot read requests file: {e}") from None
    return parse_requests_csv(text)


# --------------------------------------------------------------------------- config


def validate_config(config: SimulationConfig) -> SimulationConfig:
    if config.execution_mode not in EXECUTION_MODES:
        raise InputError(f"execution_mode must be one of {EXECUTION_MODES}, got {config.execution_mode!r}")
    if config.placement not in PLACEMENT_NAMES:
        raise InputError(f"placement must be one of {PLACEMENT_NAMES}, got {config.placement!r}")
    if config.max_wait_ticks is not None:
        _require_int(config.max_wait_ticks, "max_wait_ticks", 0)
    if config.max_queue_length is not None:
        _require_int(config.max_queue_length, "max_queue_length", 0)
    return config


def parse_config(data: Mapping[str, Any]) -> SimulationConfig:
    if not isinstance(data, Mapping):
        raise InputError("config must be a JSON object")
    unknown = sorted(set(data) - set(CONFIG_FIELDS))
    if unknown:
        raise InputError(f"unknown config fields: {', '.join(unknown)}")
    return validate_config(SimulationConfig(**data))


def load_config(path: str | Path) -> SimulationConfig:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise InputError(f"cannot read config file: {e}") from None
    except json.JSONDecodeError as e:
        raise InputError(f"config file is not valid JSON: {e}") from None
    return parse_config(data)
