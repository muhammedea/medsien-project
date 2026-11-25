# Medsien Deterministic Load Balancer

A deterministic, tick-based simulation of a load balancer that spreads requests across servers with different CPU, memory and rate limits. Given the same `servers.json`, `requests.csv` and configuration, it always produces the same `run.jsonl` trace. A React dashboard manages the servers and starts simulation runs.

> **Status:** design phase. The documents under `docs/` are complete; the engine, API and frontend are not implemented yet. The commands below describe the target setup.

## How to run

Requires only Docker with Docker Compose.

```bash
docker compose up --build
```

- Dashboard: http://localhost:8080
- API docs: http://localhost:8000/docs
- Data (SQLite database and run traces) is stored in `./data/`.

### CLI

```bash
docker compose run --rm backend python -m engine.cli \
  --servers fixtures/servers.json --requests fixtures/requests.csv \
  --out /data/run.jsonl [--mode exclusive|shared] [--max-wait N] [--max-queue N]
```

The trace is written to `./data/run.jsonl` on the host. Re-running the command overwrites it.

### Validate and test

```bash
docker compose run --rm backend python validator/validate_run.py \
  --servers fixtures/servers.json --requests fixtures/requests.csv --run /data/run.jsonl
docker compose run --rm backend pytest
```

## Execution modes

| | `exclusive` (default) | `shared` |
| --- | --- | --- |
| Requests per server | One at a time | Any number, while their total memory fits |
| CPU | The running request gets all of it | Split evenly among the running requests each tick (exact fractions) |
| Runtime | `ceil(work_units / cpu_units_per_tick)` | Depends on how many requests share the server |
| Validator | Passes the provided `validate_run.py` | Needs `validate_run.py --mode shared` |

`exclusive` matches the provided validator and is the default, as agreed with Medsien. `shared` implements the concurrent model from Section 4 of the assignment.

## Scheduling in brief

- **Tick order:** arrivals, then finishes, then scheduling.
- **Queue:** first in, first out, but later requests may skip ahead of one that can't be placed yet.
- **Server choice:** the server where the request would finish soonest; ties go to the lowest `server_id`.
- **Overload:**
  - requests too large for every server are dropped at arrival;
  - optional `max_wait_ticks` and `max_queue_length` limits drop more, each drop with a recorded reason.

Details are in the [engine design](docs/engine-design.md).

## Documentation

- [High-level design](docs/high-level-design.md): architecture, API, storage, run lifecycle
- [Engine design](docs/engine-design.md): execution models, scheduling, rate limiting, determinism, assumptions
- [DEVLOG](DEVLOG.md): development log, including how AI was used (prompts and verification)
- [AGENTS.md](AGENTS.md): guidance for AI coding agents working in this repository
