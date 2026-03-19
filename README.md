# Flox

**Real-time fault intelligence for HVAC actuators.** Flox ingests live telemetry from Belimo actuators — torque, motor position, temperature, signal quality — runs continuous fault classification, and surfaces actionable insights through a facility dashboard and a conversational AI operations agent.

Built for facility managers, system integrators, and HVAC installers who need to move from reactive maintenance to data-driven operations.

---

### Frontend

![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=white&labelColor=20232A)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?style=flat-square&logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![Radix UI](https://img.shields.io/badge/shadcn%2Fui-000000?style=flat-square&logo=radixui&logoColor=white)
![Bun](https://img.shields.io/badge/Bun-1.2-FBF0DF?style=flat-square&logo=bun&logoColor=black)

### Backend

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-37814A?style=flat-square&logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![uv](https://img.shields.io/badge/uv-DE5FE9?style=flat-square)

### Intelligence

![Anthropic](https://img.shields.io/badge/Claude-Operations_Agent-191919?style=flat-square&logo=anthropic&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?style=flat-square&logo=pytorch&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat-square&logo=scikitlearn&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-189AB4?style=flat-square)

### Infrastructure

![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat-square&logo=docker&logoColor=white)
![Nx](https://img.shields.io/badge/Nx-143055?style=flat-square&logo=nx&logoColor=white)

---

## What it does

Belimo actuators collect rich internal signals during operation — torque demand, motor position feedback, internal temperature, and control signal quality — but this data is rarely used beyond basic device status.

Flox closes that gap:

1. **Telemetry ingest** — actuator signals are ingested in real time and persisted with full history per variable per device.
2. **Fault classification** — a Celery worker runs a continuous diagnosis cycle. Heuristic rules detect known failure modes (stiction, high-torque anomaly, temperature drift, signal loss). An optional ML inference server extends this with trained classifiers.
3. **Fault propagation** — device-level faults roll up through the node hierarchy (actuator → AHU → plant), so system-level health reflects the worst downstream condition.
4. **Facility dashboard** — a live map view shows zone health, device positions, and active faults across the building. An issues panel lists all open faults ranked by severity, with energy waste and estimated cost impact per fault.
5. **Operations agent** — a Claude-powered agent answers natural-language questions about faults, runs diagnosis on demand, retrieves fault history, and can execute corrective actions with explicit operator approval before any write is committed.

---

## Fault types detected

| Kind | Condition | Severity |
|---|---|---|
| `stiction_suspected` | Torque >= 22 Nm on an actuator | Critical |
| `high_torque_anomaly` | Torque >= 16 Nm | Warning |
| `temperature_drift` | Internal temperature >= 52 °C | Warning |
| `signal_loss` | Control signal <= 0.2 | Critical |
| `weak_signal` | Control signal <= 0.45 | Warning |

ML-based classifiers (when enabled) extend coverage beyond rule thresholds.

---

## Quick start

```bash
cp .env.example .env      # set NAME, ANTHROPIC_API_KEY, and database credentials
make init                 # create venv, sync Python deps, link env files
make up                   # start postgres, redis, fastapi backend, classifier worker
make dev                  # start Vite frontend at http://localhost:3000
```

The frontend connects to the FastAPI backend at `/api/status`. If the backend is not running the dashboard will show a connection error.

```bash
make doctor               # verify toolchain
make help                 # list all targets
```

---

## Data pipeline

```
Actuator  →  POST /api/ingest        (FastAPI)
              ↓
          ingest_node()              (shacklib/diagnosis_engine.py)
              writes telemetry history + latest values to Postgres
              ↓
          Celery beat (classifier)   (apps/worker/)
              runs run_diagnosis_cycle() every N seconds
              applies heuristic classifier per node
              attaches / updates / resolves faults
              propagates status up the node tree
              ↓
          GET /api/status            (FastAPI)
              reconstructs full facility payload from Postgres
              ↓
          React dashboard            (apps/webapp/)
              map view + issues panel + device telemetry charts
```

---

## Repository layout

```
apps/
  webapp/             Vite + React + Tailwind — facility map, issues dashboard,
                      device telemetry charts, AI agent panel
  backend/
    fastapi/          REST API — telemetry ingest, status, fault resolution,
                      agent chat, document upload
  worker/             Celery beat worker — runs the classification loop

ml/
  models/             Model architecture and training loop
  data/               ETL pipeline and processed artifacts
  inference.py        FastAPI ML inference server (optional profile)
  configs/            YAML hyperparameter configs

shacklib/
  diagnosis_engine.py Fault classification, state management, payload builders
  agent.py            Claude integration (ask / stream / Agent)
  backend_state.py    Postgres read/write with relational + legacy JSONB sync
  node_simulator.py   Actuator signal simulator for development and testing
  mock_facility.py    Seed data — zones, AHU units, device templates
  logger.py           Structured JSON logger with optional Loki push
  scraper.py          Web scraper utility

database/             SQL init files (auto-run by Postgres on first start)
docker/               Per-service Dockerfiles
scripts/              Utility scripts (seed, migration helpers)
```

---

## Operations agent

The agent is powered by Claude and has access to platform tools: querying live device status, fetching fault history for a specific node, running the diagnosis cycle, and resolving faults.

Destructive actions require explicit operator approval before execution. The frontend surfaces an approval prompt; the agent does not proceed until the operator confirms.

```python
# The agent is exposed at POST /api/agent/chat
# The frontend sends the full conversation history on each turn.
# Tool events are returned alongside the reply so the UI can display what ran.
```

To interact via the UI, open the **Operations Agent** panel and type a question. Use `@NODE_ID` to attach a specific device to your message. Quick prompts are generated automatically from the current top fault.

Example prompts:

- `Give me a live system overview and top active faults.`
- `Why is node BEL-VLV-003 reporting stiction_suspected?`
- `Show fault history for node BEL-AHU-001.`
- `Run diagnosis for BEL-VLV-003 now.`
- `Resolve fault fault-a3b2c1d0 with note "validated on site".`

---

## Environment variables

Copy `.env.example` to `.env` and fill in the values relevant to your deployment.

| Variable | Description |
|---|---|
| `NAME` | Project name, used as Docker container prefix |
| `ANTHROPIC_API_KEY` | Required for the operations agent |
| `BACKEND_PORT` | FastAPI listen port (default: 5000) |
| `POSTGRES_*` | Database connection settings |
| `REDIS_PORT` | Redis port |
| `ML_URL` | URL of the ML inference service |
| `CLASSIFIER_INTERVAL_SECONDS` | How often the classifier runs (default: 5) |
| `BACKEND_STARTUP_SEED_MODE` | Seed mode on startup: `always` or `once` |
| `VITE_REQUIRE_AUTH` | Enable Supabase session auth on the frontend |
| `LOKI_PORT` / `GRAFANA_PORT` | Enable remote log aggregation |

---

## Make targets

| Target | Description |
|---|---|
| `make init` | First-time setup: venv, deps, env linking |
| `make dev` | Start Vite frontend |
| `make up` | Start core services (postgres, redis, backend, classifier, worker) |
| `make down` | Stop all services |
| `make run.backend` | Start FastAPI backend only |
| `make run.worker` | Start Celery worker only |
| `make run.ml` | Start ML inference server |
| `make lift.ml` | Core services + ML inference |
| `make lift.sim` | Core services + node simulator |
| `make lift.logging` | Add Loki + Grafana log stack |
| `make lift.mlflow` | Add MLflow experiment tracking |
| `make etl` | Run ETL pipeline |
| `make train` | Run model training |
| `make fmt` | Format Python with black |
| `make lint` | Lint with ruff |
| `make type` | Type-check with mypy |
| `make test` | Run pytest |
| `make clean` | Remove caches and build artifacts |
| `make doctor` | Verify toolchain (Python, uv, Bun, Docker) |

---

## Optional services

| Profile | Services | Command |
|---|---|---|
| _(default)_ | postgres, redis, backend, classifier, worker | `make up` |
| `ml` | + ML inference | `make lift.ml` |
| `sim` | + node simulator | `make lift.sim` |
| `minio` | + MinIO object storage | `make lift.minio` |
| `tensorboard` | + TensorBoard | `make lift.tensorboard` |
| `mlflow` | + MLflow | `make lift.mlflow` |
| `logging` | + Loki + Grafana | `make lift.logging` |
| `database` | + MongoDB | `make lift.database` |

---

## Database schema

Application state is stored in normalized Postgres tables. A legacy JSONB snapshot in `backend_state` (`id = 1`) is maintained for backward compatibility. `read_state()` reconstructs the full JSON contract; `update_state()` writes both representations atomically.

```mermaid
erDiagram
    backend_nodes {
        TEXT id PK
        TEXT label
        TEXT type
        TEXT status
        DOUBLE position
        TEXT latest_fault_id
        TEXT updated_at
    }

    backend_node_latest_telemetry {
        TEXT node_id FK
        TEXT metric
        JSONB value
    }

    backend_node_history {
        TEXT node_id FK
        TEXT metric
        INTEGER ordinal
        TEXT point_time
        JSONB value
    }

    backend_faults {
        TEXT id PK
        TEXT node_id
        TEXT state
        TEXT kind
        DOUBLE probability
        TEXT summary
        TEXT recommended_action
        TEXT opened_at
        TEXT resolved_by
        TEXT note
    }

    backend_catalog_device_templates {
        TEXT id PK
        TEXT name
        TEXT model
        TEXT type
        TEXT zone_id
    }

    backend_agent_audit_log {
        BIGINT ordinal PK
        JSONB payload
    }

    backend_nodes ||--o{ backend_node_latest_telemetry : "latest telemetry"
    backend_nodes ||--o{ backend_node_history : "history"
    backend_nodes ||--o{ backend_faults : "faults"
    backend_catalog_device_templates ||--o| backend_catalog_fault_meta : "impact metadata"
    backend_agent_meta ||--o{ backend_agent_audit_log : "audit log"
```

---

## Python logging

```python
from shacklib import get_logger

logger = get_logger("classifier")
logger.info("diagnosis cycle complete", extra={"processed": 8, "open_faults": 2})
```

Logs are written as structured JSON to console and `./logs/`. Set `LOKI_PORT` and run `make lift.logging` to push logs to Loki. Grafana is available at `http://localhost:$GRAFANA_PORT` — add a Loki data source at `http://loki:3100`.

---

## Frontend auth

Disabled by default. To enable Supabase session auth:

```env
VITE_REQUIRE_AUTH=true
VITE_SUPABASE_URL=https://<project>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-key>
```

All routes are gated automatically when auth is enabled.
