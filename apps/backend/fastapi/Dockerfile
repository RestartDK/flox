FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

ENV UV_SYSTEM_PYTHON=1

COPY requirements.txt ./requirements.txt
RUN uv pip install --system -r requirements.txt

COPY pyproject.toml ./pyproject.toml
COPY shacklib/ ./shacklib/
COPY packages/ml/pyproject.toml ./packages/ml/pyproject.toml
COPY packages/ml/src/ ./packages/ml/src/
RUN touch README.md \
    && uv pip install --system --no-deps . \
    && uv pip install --system ./packages/ml \
    && rm README.md

COPY apps/backend/fastapi/ ./apps/backend/fastapi/

ENV PYTHONPATH=/app

WORKDIR /app/apps/backend/fastapi

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os, requests; requests.get(f'http://localhost:{os.getenv(\"PORT\", \"5000\")}/health', timeout=5)" || exit 1

RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

EXPOSE 5000

CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-5000}"]
