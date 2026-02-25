# CI/CD Pipeline Management

Set up and manage CI/CD pipelines with GitHub Actions, GitLab CI, and general automation workflows.

## Cody CI/CD Templates

Cody provides ready-to-use GitHub Actions templates in the `templates/github-actions/` directory:

- **ai-code-review.yml** — AI-powered code review on every PR
- **ai-fix-issues.yml** — Auto-fix issues labeled `ai-fix`, opens a PR
- **ai-test-gen.yml** — Generate tests for changed files in a PR

### Install a template
```bash
mkdir -p .github/workflows
cp templates/github-actions/ai-code-review.yml .github/workflows/
```

### Required secret
All templates require `ANTHROPIC_API_KEY` in GitHub repository secrets:
```bash
gh secret set ANTHROPIC_API_KEY
```

## GitHub Actions

### Workflow basics
```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v
```

### Common patterns

#### Matrix builds
```yaml
strategy:
  matrix:
    python-version: ["3.9", "3.10", "3.11", "3.12"]
    os: [ubuntu-latest, macos-latest]
```

#### Caching dependencies
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
```

#### Run on specific file changes
```yaml
on:
  push:
    paths:
      - 'src/**'
      - 'tests/**'
      - 'pyproject.toml'
```

#### Deploy on tag
```yaml
on:
  push:
    tags:
      - 'v*'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_TOKEN }}
```

## GitLab CI

### Basic pipeline
```yaml
# .gitlab-ci.yml
stages:
  - test
  - build
  - deploy

test:
  stage: test
  image: python:3.11
  script:
    - pip install -e ".[dev]"
    - pytest tests/ -v

build:
  stage: build
  script:
    - python -m build
  artifacts:
    paths:
      - dist/

deploy:
  stage: deploy
  script:
    - twine upload dist/*
  only:
    - tags
```

## Integrating Cody into CI/CD

### Code review in CI
```yaml
- name: AI Review
  run: cody run "Review code quality and report issues" > review.md
```

### Auto-fix lint errors
```yaml
- name: AI Fix
  run: cody run "Fix all ruff lint warnings in src/"
```

### Generate changelog
```yaml
- name: Changelog
  run: |
    COMMITS=$(git log --oneline $(git describe --tags --abbrev=0)..HEAD)
    cody run "Generate a changelog from these commits: ${COMMITS}" > CHANGELOG.md
```

## Notes

- Always pin action versions (e.g., `actions/checkout@v4`, not `@main`)
- Store secrets in GitHub Settings > Secrets, never in workflow files
- Use `permissions` to follow least-privilege principle
- Use `concurrency` to cancel redundant runs:
  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: true
  ```
