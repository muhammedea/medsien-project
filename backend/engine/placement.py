"""Placement strategies: which server gets a request when several can accept it."""

from __future__ import annotations

from typing import ClassVar, Protocol

from .execution import ExecutionModel, ServerState
from .models import RequestSpec


class PlacementStrategy(Protocol):
    name: str

    def choose(self, req: RequestSpec, candidates: list[ServerState], model: ExecutionModel) -> ServerState:
        """Pick one of `candidates` (non-empty, sorted by server id, all able to accept `req` now)."""
        ...


class EarliestFinish:
    """Smallest estimated runtime; ties go to the smallest server_id."""

    name: ClassVar[str] = "earliest_finish"

    def choose(self, req: RequestSpec, candidates: list[ServerState], model: ExecutionModel) -> ServerState:
        return min(candidates, key=lambda s: (model.estimate_runtime(s, req), s.spec.id))


PLACEMENTS: dict[str, type[PlacementStrategy]] = {
    EarliestFinish.name: EarliestFinish,
}
