"""FastAPI application. Skeleton only: server CRUD and runs come in a later step
(see docs/high-level-design.md, "API")."""

from fastapi import FastAPI

import engine

app = FastAPI(title="Load Balancer Simulation API", version=engine.__version__)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_version": engine.__version__}
