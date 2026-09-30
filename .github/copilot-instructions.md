# Copilot instructions for fides-gateway

## Package management

This project uses [uv](https://docs.astral.sh/uv/) for Python dependency and
environment management. Use `uv` for installing, syncing, running, and adding
dependencies (e.g., `uv sync`, `uv run <cmd>`, `uv add <pkg>`). Do not use
`pip`, `poetry`, or `python -m venv` directly.

## Formatting

This repository uses [black](https://black.readthedocs.io/) and CI enforces it
via `black --check .` (see
[continuous-integration.yml](workflows/continuous-integration.yml)). After
making any Python edits — and especially before committing — run:

```
black .
```

so the change passes CI. The configured target version is `py312` (see
`[tool.black]` in `pyproject.toml`). Apply this to both `gateway.py` and
`test_gateway.py`, plus any new Python files added under the repo root.
