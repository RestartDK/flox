FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

ENV UV_SYSTEM_PYTHON=1
ENV PYTHONUNBUFFERED=1

COPY packages/ml/pyproject.toml ./packages/ml/pyproject.toml
COPY packages/ml/src/ ./packages/ml/src/

RUN uv pip install --system ./packages/ml

COPY ml/ ./ml/

HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()" || exit 1

EXPOSE 8000

RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

CMD ["uvicorn", "ml.inference:app", "--host", "0.0.0.0", "--port", "8000"]
