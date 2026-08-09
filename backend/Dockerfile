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
# RELOAD should be "false" in production; set to "true" only for dev containers.
ENV GENERATOR_DIR=/generator

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
