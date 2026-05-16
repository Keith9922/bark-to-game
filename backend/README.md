# bark-to-game backend

FastAPI service for audio analysis, translation, and Claude Agent SDK orchestration.

Phase 0 is a minimal scaffold (health endpoint only). Real modules land in later phases.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
```

## Run

```bash
uv run fastapi dev bark_to_game/main.py
```

Server: http://localhost:8000 · OpenAPI: http://localhost:8000/docs

## Quality gates

```bash
uv run pytest          # tests
uv run ruff check .    # lint
uv run ruff format --check .  # format
uv run mypy bark_to_game  # types
```
