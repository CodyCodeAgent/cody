---
name: python
description: Manage Python projects, virtual environments, dependencies, testing with pytest, linting with ruff, and packaging. Use when working with Python code.
metadata:
  author: cody
  version: "1.0"
compatibility: Requires python3, pip
---

# Python Project Management

Manage Python projects, virtual environments, dependencies, and common tooling.

## Prerequisites

- Python must be installed: `python3 --version`
- pip must be installed: `pip3 --version`

## Project Setup

### Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate    # Linux/macOS
# .venv\Scripts\activate     # Windows
```

### Modern project with pyproject.toml
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "requests>=2.28.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.7.0",
]

[project.scripts]
myapp = "my_project.cli:main"
```

### Install in development mode
```bash
pip install -e ".[dev]"
```

## Dependency Management

### Install dependencies
```bash
pip install requests
pip install -r requirements.txt
```

### Freeze dependencies
```bash
pip freeze > requirements.txt
```

### Using pip-tools (recommended)
```bash
pip install pip-tools
pip-compile requirements.in          # Generate requirements.txt from .in
pip-sync requirements.txt            # Sync environment to match
```

## Testing

### pytest
```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific file
python3 -m pytest tests/test_auth.py -v

# Run by name pattern
python3 -m pytest tests/ -k "login" -v

# With coverage
python3 -m pytest tests/ --cov=my_project --cov-report=term-missing

# Run async tests (with pytest-asyncio)
python3 -m pytest tests/ -v  # asyncio_mode = "auto" in pyproject.toml
```

### Common pytest configuration (pyproject.toml)
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

## Linting & Formatting

### Ruff (fast Python linter + formatter)
```bash
# Check for issues
ruff check .
ruff check . --fix        # Auto-fix

# Format code
ruff format .
```

### Configuration (pyproject.toml)
```toml
[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
```

### Type checking with mypy
```bash
mypy my_project/
```

## Common Patterns

### FastAPI project
```bash
pip install fastapi uvicorn
uvicorn main:app --reload --port 8000
```

### CLI with Click
```bash
pip install click
```

### Database with SQLAlchemy
```bash
pip install sqlalchemy alembic
alembic init migrations
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

## Packaging & Distribution

### Build
```bash
pip install build
python -m build
```

### Publish to PyPI
```bash
pip install twine
twine upload dist/*
```

## Environment Variables

### Using python-dotenv
```bash
pip install python-dotenv
```

```python
from dotenv import load_dotenv
load_dotenv()  # Loads .env file
```

## Notes

- Always use virtual environments (venv or conda)
- Prefer `pyproject.toml` over `setup.py` for new projects
- Use `ruff` instead of flake8/isort/black (faster, all-in-one)
- Pin exact versions in production: `pip freeze > requirements.txt`
- Use `python3 -m pytest` instead of bare `pytest` to ensure correct Python
- Add `__pycache__/`, `.venv/`, `*.pyc`, `.mypy_cache/` to `.gitignore`
