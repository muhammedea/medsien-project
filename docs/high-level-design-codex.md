# High-level design

The root `docker-compose.yml` starts two services. Each subproject owns its Dockerfile and dependencies.

| Subproject | Stack | Responsibility |
| --- | --- | --- |
| `frontend/` | Vite, React, TypeScript | Manage servers, trigger runs, view summaries, and download traces through `/api`. |
| `backend/` | Python, FastAPI, SQLite | Serve the API, persist server settings and run records, and execute simulations. The API and CLI call the same [simulation engine](engine-design.md). |

## Storage

Compose bind-mounts `./data` at `/data` in the backend. The host directory is excluded from Git.

- **SQLite** at `/data/servers.sqlite3` holds a `servers` table for editable server settings and a `runs` table with one row per completed run (`run_id` primary key, completion time, artifact directory). The backend seeds the server settings from the supplied fixture on first initialization.
- **Run files** live in `/data/runs/<run_id>/`. Each directory contains the input snapshots (`servers.json`, `requests.csv`, `config.json`), the generated `run.jsonl`, and `summary.json`.

## Run lifecycle

1. FastAPI snapshots the current server settings, request data, and effective configuration. It derives the run ID from a SHA-256 hash of those inputs using a fixed serialization and file order. Identical inputs reuse the same result.
2. The engine simulates the snapshot. The backend writes the artifacts to a temporary directory on the same volume and atomically renames it into place when complete.
3. The backend records the completed run in SQLite and returns its summary and trace URL. Retrying a run can register an already-published directory if a previous attempt stopped before the database commit. Later server edits apply to future snapshots.
