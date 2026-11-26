"""Immutable data types shared by the whole engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExecutionMode = Literal["exclusive", "shared"]
PlacementName = Literal["earliest_finish"]

EXECUTION_MODES: tuple[str, ...] = ("exclusive", "shared")
PLACEMENT_NAMES: tuple[str, ...] = ("earliest_finish",)

# Event types written to run.jsonl.
REQUEST_ARRIVED = "REQUEST_ARRIVED"
REQUEST_STARTED = "REQUEST_STARTED"
REQUEST_FINISHED = "REQUEST_FINISHED"
REQUEST_DROPPED = "REQUEST_DROPPED"

# Reasons attached to REQUEST_DROPPED events.
DROP_NO_SERVER_FITS = "no_server_fits"
DROP_MAX_WAIT_EXCEEDED = "max_wait_exceeded"
DROP_QUEUE_FULL = "queue_full"
DROP_REASONS: tuple[str, ...] = (DROP_NO_SERVER_FITS, DROP_MAX_WAIT_EXCEEDED, DROP_QUEUE_FULL)


class InputError(ValueError):
    """Invalid servers, requests or configuration. Raised before any simulation work."""


class SimulationInvariantError(RuntimeError):
    """The engine broke one of its own guarantees. Always a bug, never bad input."""


@dataclass(frozen=True)
class ServerSpec:
    id: str
    cpu_units_per_tick: int
    mem_mb: int
    rate_limit_per_sec: int  # max REQUEST_STARTED per tick (1 tick = 1 second)


@dataclass(frozen=True)
class RequestSpec:
    id: str
    arrival_t: int
    work_units: int
    mem_mb: int
    row: int  # 0-based position in requests.csv; breaks ties between same-tick arrivals


@dataclass(frozen=True)
class SimulationConfig:
    execution_mode: ExecutionMode = "exclusive"
    placement: PlacementName = "earliest_finish"
    max_wait_ticks: int | None = None  # None = wait forever
    max_queue_length: int | None = None  # None = unbounded queue


@dataclass(frozen=True)
class Event:
    t: int
    event: str
    request_id: str
    server_id: str | None = None
    reason: str | None = None
