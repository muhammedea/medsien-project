"""Execution models: how a server runs the requests placed on it.

Both models share one CPU rule: each tick, every request that ran during that tick
gets cpu_units_per_tick / N, where N is the number of those requests. `exclusive`
is simply `shared` with at most one running request per server.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import ClassVar, Protocol

from .models import RequestSpec, ServerSpec, SimulationInvariantError

Work = int | Fraction


def ceil_div(a: Work, b: Work) -> int:
    """Exact ceiling division for ints and Fractions."""
    return -(-a // b)


def cpu_share(cpu: int, n: int) -> Work:
    """Exact per-request share. Stays an int when the split is even (always in exclusive mode)."""
    return cpu // n if cpu % n == 0 else Fraction(cpu, n)


@dataclass
class RunningRequest:
    request: RequestSpec
    started_t: int
    remaining: Work


@dataclass
class ServerState:
    spec: ServerSpec
    running: list[RunningRequest] = field(default_factory=list)
    mem_used: int = 0
    starts_this_tick: int = 0

    @property
    def idle(self) -> bool:
        return not self.running

    def start(self, req: RequestSpec, t: int) -> None:
        self.running.append(RunningRequest(request=req, started_t=t, remaining=req.work_units))
        self.mem_used += req.mem_mb
        self.starts_this_tick += 1


class ExecutionModel(Protocol):
    name: str

    def can_accept(self, server: ServerState, req: RequestSpec) -> bool:
        """Capacity check only. The simulator checks the rate limit."""
        ...

    def advance(self, server: ServerState) -> list[RunningRequest]:
        """Apply one tick of CPU. Remove and return finished requests, sorted by request id."""
        ...

    def estimate_runtime(self, server: ServerState, req: RequestSpec) -> int:
        """Ticks the request would need if started on this server now, assuming the load stays the same."""
        ...

    def ticks_until_next_finish(self, server: ServerState) -> int | None:
        """How many more advance() calls until the first running request finishes. None if idle."""
        ...

    def advance_many(self, server: ServerState, ticks: int) -> None:
        """Apply `ticks` ticks of CPU at once. Caller guarantees no request finishes during them."""
        ...


class SharedModel:
    """Spec Section 4: any number of concurrent requests while their total memory fits."""

    name: ClassVar[str] = "shared"
    max_concurrency: ClassVar[int | None] = None

    def can_accept(self, server: ServerState, req: RequestSpec) -> bool:
        if self.max_concurrency is not None and len(server.running) >= self.max_concurrency:
            return False
        return server.mem_used + req.mem_mb <= server.spec.mem_mb

    def advance(self, server: ServerState) -> list[RunningRequest]:
        if not server.running:
            return []
        # Compute the share once from the set that ran this tick, apply it to all,
        # and only then remove finished requests (no leftover CPU is redistributed).
        share = cpu_share(server.spec.cpu_units_per_tick, len(server.running))
        for r in server.running:
            r.remaining -= share
        finished = [r for r in server.running if r.remaining <= 0]
        if finished:
            server.running = [r for r in server.running if r.remaining > 0]
            server.mem_used -= sum(r.request.mem_mb for r in finished)
        finished.sort(key=lambda r: r.request.id)
        return finished

    def estimate_runtime(self, server: ServerState, req: RequestSpec) -> int:
        sharers = len(server.running) + 1
        return ceil_div(req.work_units * sharers, server.spec.cpu_units_per_tick)

    # Used by the simulator to skip ticks in which nothing observable happens.
    # The share stays the same while no request starts or finishes, so N ticks of
    # progress equal one subtraction of N * share.

    def ticks_until_next_finish(self, server: ServerState) -> int | None:
        if not server.running:
            return None
        share = cpu_share(server.spec.cpu_units_per_tick, len(server.running))
        return min(ceil_div(r.remaining, share) for r in server.running)

    def advance_many(self, server: ServerState, ticks: int) -> None:
        if ticks <= 0 or not server.running:
            return
        share = cpu_share(server.spec.cpu_units_per_tick, len(server.running))
        for r in server.running:
            r.remaining -= share * ticks
            if r.remaining <= 0:
                raise SimulationInvariantError(f"request '{r.request.id}' would finish inside a skipped interval")


class ExclusiveModel(SharedModel):
    """Default: one request per server at a time, with the full CPU. Matches validate_run.py."""

    name: ClassVar[str] = "exclusive"
    max_concurrency: ClassVar[int | None] = 1


EXECUTION_MODELS: dict[str, type[SharedModel]] = {
    ExclusiveModel.name: ExclusiveModel,
    SharedModel.name: SharedModel,
}
