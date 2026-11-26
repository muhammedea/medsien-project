"""Command-line entry point: python -m engine.cli (or python -m engine)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence

from . import __version__
from .loaders import load_config, load_requests, load_servers, validate_config
from .models import EXECUTION_MODES, PLACEMENT_NAMES, InputError, SimulationConfig
from .output import write_jsonl
from .simulator import simulate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m engine.cli",
        description="Run the deterministic load balancer simulation and write run.jsonl.",
    )
    p.add_argument("--servers", required=True, help="path to servers.json")
    p.add_argument("--requests", required=True, help="path to requests.csv")
    p.add_argument("--out", default="run.jsonl", help="output trace path (overwritten; default: run.jsonl)")
    p.add_argument("--config", help="JSON file with SimulationConfig fields; flags below override it")
    p.add_argument("--mode", choices=EXECUTION_MODES, help="execution model (default: exclusive)")
    p.add_argument("--placement", choices=PLACEMENT_NAMES, help="placement strategy (default: earliest_finish)")
    p.add_argument("--max-wait", type=int, metavar="N", help="drop requests that waited N ticks without starting")
    p.add_argument("--max-queue", type=int, metavar="N", help="drop newest queued requests beyond N")
    p.add_argument("--quiet", action="store_true", help="do not print the summary")
    p.add_argument("--version", action="version", version=f"engine {__version__}")
    return p


def resolve_config(args: argparse.Namespace) -> SimulationConfig:
    config = load_config(args.config) if args.config else SimulationConfig()
    overrides = {
        "execution_mode": args.mode,
        "placement": args.placement,
        "max_wait_ticks": args.max_wait,
        "max_queue_length": args.max_queue,
    }
    config = dataclasses.replace(config, **{k: v for k, v in overrides.items() if v is not None})
    return validate_config(config)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = resolve_config(args)
        servers = load_servers(args.servers)
        requests = load_requests(args.requests)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    result = simulate(servers, requests, config)
    write_jsonl(result.events, args.out)

    if not args.quiet:
        print(f"wrote {len(result.events)} events to {args.out}")
        print(json.dumps(result.summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
