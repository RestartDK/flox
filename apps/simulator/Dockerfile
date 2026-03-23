FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

ENV UV_SYSTEM_PYTHON=1

RUN uv pip install --system numpy pandas

COPY pyproject.toml ./pyproject.toml
COPY shacklib/ ./shacklib/
RUN uv pip install --system --no-deps .

COPY ml/data/anomaly_dataset.csv ./ml/data/anomaly_dataset.csv
COPY apps/simulator/ ./apps/simulator/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "apps/simulator/run.py"]
