# AGENTS.md

Take-home assignment: a deterministic load balancer **simulation**. Servers and requests are configuration data, simulated tick by tick; there are no real worker processes and no real traffic. The assignment and its sample data are in `project-info/`.

## Read first

- `docs/high-level-design.md`: services, layout, API, storage, run lifecycle.
- `docs/engine-design.md`: tick order, execution models, scheduling, overload, determinism rules.
- `DEVLOG.md`: decisions and AI usage so far.

## Layout

- `backend/engine/`: the simulation library. Standard library only.
  - `simulate()` is pure: no I/O, no clocks, no randomness.
  - File access is limited to `loaders.py`, `output.py` and `cli.py`.
- `backend/api/`: the FastAPI app. It may import `engine`; `engine` never imports `api`.
- `backend/validator/validate_run.py`: the trace validator.
- `frontend/`: Vite + React + TypeScript.
- `project-info/`: original assignment files. **Never modify them.**

## Commands

Local development (run from `backend/`, using uv):

```
uv sync
uv run pytest
uv run python -m engine.cli --servers fixtures/servers.json --requests fixtures/requests.csv --out run.jsonl
uv run uvicorn api.main:app --reload
```

Docker (what reviewers use):

```
docker compose up --build                     # app at :8080, API at :8000
docker compose run --rm backend pytest
```

If engine output changes, regenerate `examples/run.jsonl` (a test checks that it's up to date):

```
uv run python -m engine.cli --servers fixtures/servers.json --requests fixtures/requests.csv --out ../examples/run.jsonl --quiet
```

## Rules that must hold

- **Validator:** `exclusive` mode (the default) must pass the original `validate_run.py`, unchanged. Without `--mode shared`, the validator must behave exactly like the original.
- **Determinism:**
  - Use only the fixed orders: requests by `(t, CSV row)`, servers by `server_id`, finishes by `request_id`.
  - No floats in the engine (use `int` or `Fraction`).
  - No randomness, clocks or set iteration.
  - Running the same input twice must give byte-identical output.
- **Lifecycle:** every request ends as `ARRIVED → STARTED → FINISHED` or `ARRIVED → DROPPED`.
- **Input validation:** only the engine's loaders validate input. The API maps their errors to `422`.

## Working conventions

- Behavior changes come with tests. The tests run the validator on generated traces.
- When a design decision changes, update the matching doc in `docs/` in the same change.
- Leave optional features (extra strategies, metrics, auto-scaling, visualization) for later unless asked.
- Don't edit `DEVLOG.md`; the author writes it.
