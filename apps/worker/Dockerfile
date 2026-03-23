FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

ENV UV_SYSTEM_PYTHON=1

COPY apps/worker/requirements.docker.txt ./requirements.docker.txt
RUN uv pip install --system -r requirements.docker.txt

COPY pyproject.toml ./pyproject.toml
COPY shacklib/ ./shacklib/
RUN uv pip install --system --no-deps .

RUN mkdir -p ./worker/
COPY apps/worker/ ./worker/

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os, redis; redis.from_url(os.environ['REDIS_URL']).ping()" || exit 1

RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

CMD ["celery", "-A", "worker.worker:app", "worker", "-B", "--loglevel=info", "--schedule=/tmp/celerybeat-schedule"]
