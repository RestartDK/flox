FROM python:3.12-slim

WORKDIR /app

# System deps - layer rarely changes
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install external dependencies only - layer cached until pyproject.toml changes.
# Stub files satisfy setuptools' package discovery without real source,
# so external deps are downloaded once and reused across source-only rebuilds.
COPY pyproject.toml ./
RUN touch README.md \
    && mkdir -p shacklib && touch shacklib/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf shacklib README.md

# Copy local library and reinstall it without re-downloading external deps
COPY shacklib/ ./shacklib/
RUN pip install --no-cache-dir --no-deps .

# Copy application source last - most frequently changed
COPY apps/backend/fastapi/ ./apps/backend/fastapi/

WORKDIR /app/apps/backend/fastapi

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os, requests; requests.get(f\"http://localhost:{os.getenv('PORT', '5000')}/health\", timeout=5)" || exit 1

RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

EXPOSE 5000

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-5000}"]
