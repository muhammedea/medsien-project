"""Run files on disk: the canonical input snapshot and the outputs of each run.

Layout (docs/high-level-design.md, "Storage"):

    <data_dir>/runs/<id>/servers.json   requests.csv   config.json   run.jsonl   summary.json
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

import engine as sim

INPUT_FILES = ("servers.json", "requests.csv", "config.json")


# --------------------------------------------------------------------------- canonical text forms
#
# The snapshot is saved in one fixed text form, so the saved files reproduce the run exactly
# (`python -m engine.cli --servers servers.json --requests requests.csv --config config.json`)
# and two runs with equivalent inputs get the same input_hash.


def servers_text(servers: Sequence[sim.ServerSpec]) -> str:
    doc = {
        "tick_seconds": 1,
        "servers": [
            {
                "id": s.id,
                "cpu_units_per_tick": s.cpu_units_per_tick,
                "mem_mb": s.mem_mb,
                "rate_limit_per_sec": s.rate_limit_per_sec,
            }
            for s in sorted(servers, key=lambda s: s.id)
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def requests_text(requests: Sequence[sim.RequestSpec]) -> str:
    """CSV in the original row order (row order breaks ties between same-tick arrivals)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["t", "request_id", "work_units", "mem_mb"])
    for r in sorted(requests, key=lambda r: r.row):
        writer.writerow([r.arrival_t, r.id, r.work_units, r.mem_mb])
    return buf.getvalue()


def config_text(config: sim.SimulationConfig) -> str:
    return json.dumps(dataclasses.asdict(config), indent=2) + "\n"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def input_hash(files: dict[str, str]) -> str:
    """SHA-256 over the three canonical input files, each prefixed by its name."""
    return sha256("".join(f"{name}\n{files[name]}" for name in INPUT_FILES))


# --------------------------------------------------------------------------- run directories


def run_dir(runs_dir: Path, run_id: int) -> Path:
    return runs_dir / str(run_id)


def write_run_dir(runs_dir: Path, run_id: int, files: dict[str, str]) -> Path:
    """Write every file to a temporary directory, then rename it into place in one step,
    so a half-written run is never visible."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=runs_dir, prefix=f".tmp-{run_id}-"))
    try:
        for name, text in files.items():
            with open(tmp / name, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        target = run_dir(runs_dir, run_id)
        if target.exists():
            # Only possible when the database was reset but old run folders were kept:
            # the folder belongs to a run that no longer exists.
            shutil.rmtree(target)
        os.replace(tmp, target)
        return target
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
