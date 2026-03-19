FROM python:3.12-slim

WORKDIR /app

# System deps - layer rarely changes
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install inference dependencies only.
COPY docker/requirements.ml.txt ./docker/requirements.ml.txt
RUN pip install --no-cache-dir -r docker/requirements.ml.txt

# Install local shared library without pulling full project dependencies.
COPY pyproject.toml ./pyproject.toml

# Copy local library and reinstall it without re-downloading external deps
COPY shacklib/ ./shacklib/
RUN pip install --no-cache-dir --no-deps .

# Copy application source last - most frequently changed
COPY ml/ ./ml/
COPY src/ ./src/

# Ensure weights directory exists
RUN mkdir -p /app/ml/models/weights

HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()" || exit 1

EXPOSE 8000

RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

WORKDIR /app/ml
CMD ["uvicorn", "inference:app", "--host", "0.0.0.0", "--port", "8000"]
