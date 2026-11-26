FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app

# Dependencies first, for layer caching. Dev dependencies (pytest) are included so
# `docker compose run --rm backend pytest` works without a local Python setup.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

COPY . .

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
