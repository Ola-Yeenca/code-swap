# Backend

FastAPI service for the Claude + Codex wrapper.

## Local Dev

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pytest
```

If local `pytest` is not available in the backend venv, you can run:

```bash
PYTHONPATH='backend:backend/.venv/lib/python3.13/site-packages' pytest backend/tests -q
```

## CLI

After install, use `code-swap`:

```bash
code-swap codex "hello"
code-swap claude "hello"
code-swap compare "Compare answers to this prompt"
code-swap models
```
