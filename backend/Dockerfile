# ─── Stage 1: generator venv ──────────────────────────────────────────────────
# Build the generator's virtualenv in its own stage so we don't need pip/build
# tools in the final image. The generator itself is a separate Python project
# (faker, neo4j driver only) and must be bundled here because
# app/services/scenario.py spawns generator/.venv/bin/python3 as a subprocess.
FROM python:3.12-slim AS generator-builder

WORKDIR /generator

COPY generator/requirements.txt ./
RUN python3 -m venv .venv && \
    .venv/bin/pip install --no-cache-dir -r requirements.txt

# ─── Stage 2: backend deps ────────────────────────────────────────────────────
FROM python:3.12-slim AS backend-builder

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY backend/pyproject.toml ./
RUN uv pip install --system --no-cache -e .

# ─── Stage 3: final image ─────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy installed backend packages from builder
COPY --from=backend-builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy backend application code
COPY backend/app ./app

# Copy generator source + its pre-built venv into the expected location.
# scenario.py looks for generator/ relative to its own file's grandparent
# directory: Path(__file__).resolve().parents[3] / "generator"
# With WORKDIR=/app and app code at /app/app, parents[3] resolves to /,
# so we place generator at /generator and override via GENERATOR_DIR env var.
COPY --from=generator-builder /generator/.venv /generator/.venv
COPY generator/ /generator/

EXPOSE 8000

# GENERATOR_DIR tells scenario.py where to find the generator.
ENV GENERATOR_DIR=/generator

# Shell form, not exec (JSON-array) form: Render (and most PaaS Docker
# runners) inject a `PORT` env var at container start and route traffic to
# it, which only a shell can expand — `CMD ["uvicorn", ..., "--port",
# "$PORT"]` would pass the literal string "$PORT" to uvicorn and fail to
# bind. Falls back to 8000 (this image's EXPOSE'd port) when PORT is unset,
# e.g. under plain `docker run`.
#
# `exec` matters here: without it, `/bin/sh -c "uvicorn ..."` stays PID 1 and
# does not reliably forward SIGTERM to the uvicorn child, so a platform
# shutdown/redeploy would wait out the shell's own handling (or Docker's
# SIGKILL grace period) instead of uvicorn shutting down cleanly. `exec`
# replaces the shell with the uvicorn process, so it becomes PID 1 itself and
# receives the signal directly — the standard fix for this exact tradeoff,
# confirmed against `docker build`'s own "JSON arguments recommended ... for
# OS signals" warning on the plain shell-form version of this line.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
