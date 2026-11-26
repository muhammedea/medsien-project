# Medsien Deterministic Load Balancer

A deterministic, tick-based simulation of a load balancer that spreads requests across servers with different CPU, memory and rate limits. Given the same `servers.json`, `requests.csv` and configuration, it always produces the same `run.jsonl` trace. A React dashboard manages the servers and starts simulation runs.

> **Status:**
> - **Done:** the engine and CLI (both execution modes), validators for both modes, the API (server CRUD, runs, downloads, events, timeline), the dashboard (servers, run history, new run, run details with timeline, tick inspector and load charts) and the Docker setup.
> - **Next:** optional features (more placement strategies, auto-scaling).
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

For a trace made with `--mode shared`, use `validator/validate_run_shared.py` with the same arguments. `validate_run.py` is the provided validator, unchanged, and checks `exclusive` traces.

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
| Validator | `validate_run.py` (the provided one, unchanged) | `validate_run_shared.py`. The provided validator rejects these traces because runs overlap. |

`exclusive` matches the provided validator and is the default, as agreed with Medsien. `shared` implements the concurrent model from Section 4 of the assignment.

## Scheduling in brief

- **Tick order:** arrivals, then finishes, then scheduling.
- **Queue:** first in, first out, but later requests may skip ahead of one that can't be placed yet.
- **Server choice:** the server where the request would finish soonest; ties go to the lowest `server_id`.
- **Overload:**
  - requests too large for every server are dropped at arrival;
  - optional `max_wait_ticks` and `max_queue_length` limits drop more, each drop with a recorded reason.

Details are in the [engine design](docs/engine-design.md).

## Rate limiting strategy

`rate_limit_per_sec` limits how many requests may **start** on a server in one tick (1 tick = 1 second).

- **What counts:** only `REQUEST_STARTED` events. Requests already running, finishes and drops don't count, so the limit caps how fast new work is admitted, not how much work runs at once. Memory (and, in `exclusive` mode, the one-request-at-a-time rule) limits that.
- **Fixed window per tick:** each server's start counter resets to 0 at the start of every scheduling step. Unused starts are not carried over to the next tick; there is no token bucket or burst allowance.
- **Checked during placement:** a server that has used up its starts for this tick is not a candidate. The request goes to another server that can take it, or stays in the queue. Hitting a rate limit never drops a request by itself; it only does so through the overload limits (`max_wait_ticks`, `max_queue_length`).
- **Skip-ahead still applies:** the queue scan continues past a request that couldn't be placed, so a later request may still start on a server that has starts left.
- **Retry on the next tick:** when a request is held back only by a rate limit, the engine visits the next tick (instead of jumping to the next arrival or finish), because the counters reset there.
- **By mode:** in `exclusive` mode a busy server can't start anything else, so the limit can never be reached; it is still enforced. In `shared` mode it matters: a server with free memory still starts at most `rate_limit_per_sec` requests per tick.
- **Verified:** both validators count starts per server per tick and reject a trace that goes over the limit.

Example: s1 has `rate_limit_per_sec = 2` and 1024 MB in `shared` mode. Five 100 MB requests arrive at t=0. If s1 is the only server, two start at t=0, two at t=1 and one at t=2, even though all five would fit in memory at once.

## Documentation

- [High-level design](docs/high-level-design.md): architecture, API, storage, run lifecycle
- [Engine design](docs/engine-design.md): execution models, scheduling, rate limiting, determinism, assumptions
- [UI requirements](docs/ui-requirements.md): screens, the run upload flow, and the run visualization
- [DEVLOG](DEVLOG.md): development log, including how AI was used (prompts and verification)
- [AGENTS.md](AGENTS.md): guidance for AI coding agents working in this repository
