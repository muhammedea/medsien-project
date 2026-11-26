"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BACKEND_DIR / "fixtures"


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    fixtures_dir: Path = FIXTURES_DIR
    # Upload limits for POST /api/runs (the CLI has none). Exceeding either one gives 413.
    max_upload_bytes: int = 2_000_000
    max_request_rows: int = 20_000
    # Above this many requests, the timeline suggests starting the Gantt chart zoomed in.
    timeline_zoom_threshold: int = 2_000

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.sqlite3"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            # Docker sets DATA_DIR=/data. Locally, default to <repo>/data (gitignored).
            data_dir=Path(os.environ.get("DATA_DIR") or BACKEND_DIR.parent / "data"),
            max_upload_bytes=_int_env("MAX_UPLOAD_BYTES", 2_000_000),
            max_request_rows=_int_env("MAX_REQUEST_ROWS", 20_000),
            timeline_zoom_threshold=_int_env("TIMELINE_ZOOM_THRESHOLD", 2_000),
        )
