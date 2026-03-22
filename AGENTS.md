# Flox - Agent Instructions

Scaffold for any project: webapp, API, ML pipeline, scraper, worker, CLI, or SDK. Turborepo + Bun for JS tasks; `uv` for Python. Deploy production workloads with Dokploy (Docker); use Docker Compose locally only when you need Postgres, Redis, and other backing services on your machine.

## Project Layout

```
apps/webapp/          Vite + React + Tailwind (Bun, auth optional)
apps/webapp-minimal/  Streamlit prototype (optional; not wired in this repo)
apps/backend/fastapi/ FastAPI server
apps/backend/flask/   Flask server
apps/worker/          Celery worker (Redis broker)
apps/simulator/       Node simulator
ml/                   PyTorch ML pipeline (arch, train, inference, etl)
shacklib/             Shared Python library: logger, scraper, agent
src/                  Simple scripts / CLI
```

## Rules for Agents

- **Bootstrap:** `uv sync && bun install` (or `bun run bootstrap` from repo root). Creates/uses root `.venv` and installs all workspace packages.
- **Dev (webapp only):** `bun run dev` (Turborepo → Vite on port 3000).
- **Dev (web + API + worker + ML inference):** `bun run dev:stack` (parallel long-running tasks).
- **Build / lint / typecheck / test:** `bun run build`, `bun run lint`, `bun run typecheck`, `bun run test`.
- **ML:** `bun run etl`, `bun run train` (train depends on etl in `turbo.json`).
- **Python formatting:** `bun run fmt` (Black).
- **Local infra (optional):** `bun run compose:up` / `bun run compose:down` for core `docker compose` services. `turbo run dev` does not start Postgres or Redis; use Compose or point `.env` at hosted services.
- **Env files:** Symlink or copy root `.env` to `apps/webapp/.env`, `apps/worker/.env`, and `ml/.env` if those apps expect a local `.env`.
- Python deps: root `pyproject.toml` + `uv.lock`. JS: Bun workspaces; add packages with `bun add` from the relevant workspace directory (or `-w` / `--filter` patterns per Bun docs).
- Do not create rogue files or test scripts outside the established structure.
- All shared Python utilities go in `shacklib/`. Import from there, never duplicate logic.
- No emojis in code, comments, or logs.

## AI / Agent SDK

`ANTHROPIC_API_KEY` is required for AI features. `shacklib.agent` provides:

```python
from shacklib import ask, stream, Agent

ask("prompt")            # blocking one-shot
stream("prompt")         # iterator of text chunks
Agent(system="...").chat("prompt")  # multi-turn
```

For full agentic loops with file/bash tools, use the Claude Agent SDK:
```bash
pip install claude-agent-sdk
```
```python
from claude_agent_sdk import query, ClaudeAgentOptions
async for msg in query(prompt="...", options=ClaudeAgentOptions(allowed_tools=["Read","Bash"])):
    print(msg)
```

## Slash Commands (.claude/commands/)

Use in Claude Code sessions (type `/`):
- `/plan` - plan an implementation within this boilerplate
- `/build` - implement a feature end-to-end
- `/api` - scaffold a backend endpoint
- `/page` - scaffold a webapp page
- `/review` - review recent changes
- `/ship` - commit staged changes
