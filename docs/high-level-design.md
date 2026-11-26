# High-level design

Two services, started by the root `docker-compose.yml`. Each subproject owns its Dockerfile and dependencies. The simulation logic itself is described in the [engine design](engine-design.md).

```
browser ──> frontend (nginx :8080) ──/api──> backend (FastAPI :8000) ──> engine (pure Python)
             static React build                 SQLite + run files in /data
```

| Subproject | Stack | Responsibility |
| --- | --- | --- |
| `frontend/` | Vite, React, TypeScript, nginx | Manage servers, start runs, view summaries, download traces. nginx serves the built app and forwards `/api` to the backend, so the browser talks to one origin and no CORS setup is needed. |
| `backend/` | Python 3.12, FastAPI, SQLAlchemy, SQLite | API, storage, and running simulations. The API and the CLI call the same `engine.simulate()`. |

## Repository layout

```
backend/
  engine/        # pure simulation library, stdlib only, no web or database code
  api/           # FastAPI app: routes, schemas, storage, run service
  validator/     # validate_run.py (copy of the provided one; gains a --mode shared option later)
  fixtures/      # default servers.json + requests.csv (copied from project-info/)
  tests/
  Dockerfile
  pyproject.toml
frontend/
  src/
  Dockerfile     # multi-stage: build with Node, serve with nginx
  nginx.conf
docs/            # design documents
project-info/    # original assignment files, read-only
data/            # runtime volume (gitignored)
docker-compose.yml
```

**Dependency rule:** `api` imports `engine`; `engine` imports nothing from `api`. This keeps the engine testable on its own and easy to extend during the interview.

## API

| Method and path | Purpose |
| --- | --- |
| `GET /api/servers` | List servers, sorted by id |
| `POST /api/servers` | Create a server |
| `PUT /api/servers/{id}` | Edit a server. The id itself can't be changed. |
| `DELETE /api/servers/{id}` | Delete a server |
| `POST /api/runs` | Start a run. Multipart form with a `config` field (JSON) and an optional `requests` CSV file; without the file, the default fixture is used. Returns the run id and summary. |
| `GET /api/runs` | List past runs |
| `GET /api/runs/{id}` | A run's summary and config |
| `GET /api/runs/{id}/run.jsonl` | Download the trace |

Input is validated in one place, the engine's loaders. The API turns their `InputError` into a `422` response, so the CLI and the API apply exactly the same rules.

**Workload limit:** runs happen right away, inside the HTTP request.
- The engine's running time grows with the number of events, not with simulated time (see engine design §4).
- The API therefore limits the size of uploaded request files (configurable maximum size and row count) and returns `413` when a file is too large.
- The CLI has no limit.

## Storage

Compose bind-mounts `./data` on the host to `/data` in the backend. A bind mount is used instead of a named volume so generated traces can be opened directly on the host. `data/` is excluded from Git.

- **SQLite** at `/data/app.sqlite3`:
  - a `servers` table for the editable server settings;
  - a `runs` table with one row per run: an auto-increment `id`, `created_at`, `status` (`pending`, `completed` or `failed`), config, summary counts, `input_hash`, `trace_hash` and `engine_version`.
  - On first start, the `servers` table is filled from `fixtures/servers.json`.
- **Run files** in `/data/runs/<id>/`:
  - the inputs used: `servers.json`, `requests.csv`, `config.json`;
  - the outputs: `run.jsonl`, `summary.json`.

SQLAlchemy keeps a later move to Postgres down to a change of connection string. There is no Redis: runs finish in milliseconds and happen right away in the request, so there's nothing to queue or cache.

## Run lifecycle

1. **Snapshot.** The backend gathers the current servers (sorted by id), the request data and the effective config, and turns them into a fixed text form. `input_hash` is the SHA-256 of that text.
2. **Create the record.** A `runs` row is inserted with `status = pending`, and the database assigns the next `id`.
3. **Simulate and write.** The engine runs on the snapshot. The backend writes the files to a temporary directory under `/data` and renames it to `/data/runs/<id>/` in one step, so a half-written run is never visible.
4. **Finish.** The row is updated with the summary, `trace_hash` (the SHA-256 of `run.jsonl`) and `status = completed`. If anything fails, the status is set to `failed` instead.

**Versioning:** every run, including a repeat of the same inputs, gets a new numbered version, and nothing is cached. Runs finish in milliseconds, so reusing results wouldn't save anything.

**Showing determinism:** this is the spec's "same inputs → same `run.jsonl`" rule, stored in a form that's easy to check. Runs with the same `input_hash` **and** the same `engine_version` must have the same `trace_hash`. A test checks this, and the dashboard can point out identical runs.
- `engine_version` is `engine.__version__`, set by hand in `backend/engine/__init__.py`; increase it whenever engine output changes. It's recorded only for traceability, never used to reuse results.
- Without it, an intended change to engine behavior would look like a determinism failure when old runs are compared with new ones.

Editing servers only affects later runs. Past runs keep the server snapshot they were made with, so they can still be explained and reproduced.

## Running

Everything runs through Docker. No local Python or Node setup is required.

| Task | Command |
| --- | --- |
| Start the app | `docker compose up --build`, then open http://localhost:8080 (API docs at http://localhost:8000/docs) |
| Run the CLI | `docker compose run --rm backend python -m engine.cli --servers fixtures/servers.json --requests fixtures/requests.csv --out /data/run.jsonl` |
| Validate a trace | `docker compose run --rm backend python validator/validate_run.py --servers fixtures/servers.json --requests fixtures/requests.csv --run /data/run.jsonl` |
| Run the tests | `docker compose run --rm backend pytest` |
