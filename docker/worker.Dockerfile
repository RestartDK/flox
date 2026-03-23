FROM python:3.12-slim

WORKDIR /app

# System deps - layer rarely changes
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install runtime dependencies for worker/classifier.
# Keep this list lean to avoid downloading ML/GPU packages.
COPY docker/requirements.worker.txt ./docker/requirements.worker.txt
RUN pip install --no-cache-dir -r docker/requirements.worker.txt

# Install local shared library without pulling full project dependencies.
COPY pyproject.toml ./pyproject.toml

# Copy local library and reinstall it without re-downloading external deps
COPY shacklib/ ./shacklib/
RUN pip install --no-cache-dir --no-deps .

# Copy application source last - most frequently changed
RUN mkdir -p ./worker/
COPY apps/worker/ ./worker/
COPY src/ ./src/

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os, redis; redis.from_url(os.environ['REDIS_URL']).ping()" || exit 1

RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app
CMD ["celery", "-A", "worker.worker:app", "worker", "-B", "--loglevel=info", "--schedule=/tmp/celerybeat-schedule"]
