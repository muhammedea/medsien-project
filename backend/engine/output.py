"""Serialization of events to run.jsonl. Byte-stable for identical event lists."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import Event


def event_to_dict(ev: Event) -> dict[str, Any]:
    """Fixed key order: t, event, request_id, server_id, reason (absent keys omitted)."""
    out: dict[str, Any] = {"t": ev.t, "event": ev.event, "request_id": ev.request_id}
    if ev.server_id is not None:
        out["server_id"] = ev.server_id
    if ev.reason is not None:
        out["reason"] = ev.reason
    return out


def to_jsonl(events: Iterable[Event]) -> str:
    return "".join(
        json.dumps(event_to_dict(ev), separators=(",", ":"), ensure_ascii=False) + "\n" for ev in events
    )


def write_text_atomic(path: str | Path, text: str) -> None:
    """Write via a temp file + rename so readers never see a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_jsonl(events: Iterable[Event], path: str | Path) -> None:
    write_text_atomic(path, to_jsonl(events))
