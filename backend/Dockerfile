# syntax=docker/dockerfile:1

# MyLabData backend image: FastAPI + embedded DuckDB, with the prebuilt React
# bundle baked in so the SPA and /api/v1 share a single origin.
#
# The build context MUST be the repository root, so that both backend/ and
# frontend/dist/ are available:
#
#   cd frontend && npm run build                       # produce frontend/dist
#   docker build -f backend/Dockerfile -t mylabdata:local .
#
# The data root is never baked into the image; bind-mount it at runtime:
#
#   docker run -v /data/mylabdata:/data -p 127.0.0.1:8000:8000 mylabdata:local

FROM python:3.12-slim

# uv, pinned to the version used during development (see backend/uv.lock).
COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install the locked runtime dependencies only (no dev extras, no project
# package). Keeping this layer ahead of the source copy lets it stay cached
# when only application code changes.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source (imported via `--app-dir src`).
COPY backend/src ./src

# Prebuilt React SPA, served by FastAPI at the same origin as /api/v1.
COPY frontend/dist ./frontend/dist
# The bundle is copied from the host as-is, and Windows scp creates 0700
# directories. Make it readable for the unprivileged runtime user.
RUN chmod -R a+rX /app/frontend/dist

# Runtime configuration. Tuned for a small (1 GiB) host: DuckDB is capped low
# and spills to $MLD_DATA_ROOT/Temp instead of being killed by the OOM reaper.
ENV MLD_DATA_ROOT=/data \
    MLD_FRONTEND_DIST_DIRECTORY=/app/frontend/dist \
    MLD_HOST=0.0.0.0 \
    MLD_PORT=8000 \
    MLD_LOG_LEVEL=INFO \
    MLD_MEMORY_LIMIT=512MB \
    MLD_THREADS=1 \
    MLD_QUERY_WORKERS=1 \
    MLD_PRESERVE_INSERTION_ORDER=false

# Run unprivileged. APP_UID defaults to the first Ubuntu user (1000) so the
# bind-mounted data directory stays writable.
ARG APP_UID=1000
RUN useradd --uid "${APP_UID}" --create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000

# DuckDB is an embedded single-writer engine: exactly one worker process.
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
