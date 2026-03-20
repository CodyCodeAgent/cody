---
name: python
description: Python development best practices, testing with pytest, virtual environments, and package management.
---

# Python Development Skill

## When to use
- Writing or reviewing Python code
- Setting up Python projects (pyproject.toml, setup.py)
- Running tests with pytest or unittest
- Managing virtual environments (venv, virtualenv)
- Installing packages with pip or uv

## Best practices
- Use type hints for function signatures
- Prefer `pathlib.Path` over `os.path`
- Use `pytest` for testing, with fixtures and parametrize
- Follow PEP 8 style conventions
- Use virtual environments to isolate dependencies
- Prefer f-strings over `.format()` or `%` formatting

## Common commands
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint
ruff check .
```
