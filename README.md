# Medsien Deterministic Load Balancer

A deterministic, tick-based simulation of a load balancer that spreads requests across servers with different CPU, memory and rate limits. Given the same `servers.json`, `requests.csv` and configuration, it always produces the same `run.jsonl` trace. A React dashboard manages the servers and starts simulation runs.

> **Status:**
> - **Done:** the engine and CLI (both execution modes), the API (server CRUD, runs, downloads, events, timeline), the dashboard (servers, run history, new run, run details with timeline, tick inspector and load charts) and the Docker setup.
> - **Next:** `--mode shared` for the validator, and optional features.
>
> An example trace generated from the fixtures is in [examples/run.jsonl](examples/run.jsonl).

## How to run

Requires only Docker with Docker Compose.

```bash
docker compose up --build
```

- Dashboard: http://localhost:8080. Open **Runs → Run the sample** (or **New run → Run simulation** with the defaults) to reproduce the assignment's sample run, then **Download run.jsonl**.
- API docs: http://localhost:8000/docs
- Data (SQLite database and run traces) is stored in `./data/`.

### CLI

```bash
docker compose run --rm backend python -m engine.cli \
  --servers fixtures/servers.json --requests fixtures/requests.csv \
  --out /data/run.jsonl
```

Optional flags:
- `--mode exclusive` (default) or `--mode shared`;
- `--max-wait N`: drop requests that have waited N ticks without starting;
- `--max-queue N`: keep at most N requests waiting;
- `--config config.json`: read these settings from a file; flags given on the command line override it.

The trace is written to `./data/run.jsonl` on the host. Re-running the command overwrites it.

### Validate and test

```bash
docker compose run --rm backend python validator/validate_run.py \
  --servers fixtures/servers.json --requests fixtures/requests.csv --run /data/run.jsonl
docker compose run --rm backend pytest
```

## Local development (without Docker)

You need [uv](https://docs.astral.sh/uv/) for the backend and Node.js 22 or newer for the frontend.

```bash
cd backend
uv sync                                   # creates .venv (Python 3.14, per .python-version)
uv run pytest                             # tests
uv run python -m engine.cli --servers fixtures/servers.json \
  --requests fixtures/requests.csv --out run.jsonl
uv run python validator/validate_run.py --servers fixtures/servers.json \
  --requests fixtures/requests.csv --run run.jsonl
uv run uvicorn api.main:app --reload      # API on :8000

cd frontend
npm install
npm run dev                               # http://localhost:5173, /api forwarded to :8000
```

## Execution modes

| | `exclusive` (default) | `shared` |
| --- | --- | --- |
| Requests per server | One at a time | Any number, while their total memory fits |
| CPU | The running request gets all of it | Split evenly among the running requests each tick (exact fractions) |
| Runtime | `ceil(work_units / cpu_units_per_tick)` | Depends on how many requests share the server |
| Validator | Passes the provided `validate_run.py` | The provided validator rejects it. Tests check memory, rate limits and request lifecycles; a `--mode shared` validator option is planned. |

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
- [UI requirements](docs/ui-requirements.md): screens, the run upload flow, and the run visualization
- [DEVLOG](DEVLOG.md): development log, including how AI was used (prompts and verification)
- [AGENTS.md](AGENTS.md): guidance for AI coding agents working in this repository
