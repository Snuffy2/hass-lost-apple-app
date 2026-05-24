# Development

Create or refresh the local Python 3.14 virtual environment:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[test]"
```

Run the project checks from the repository root with the repo-local venv:

```bash
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy app/src tests
./.venv/bin/pytest
```

## Release workflow notes

Container images for the Lost Apple App are built from:
- `app/lost_apple/Dockerfile`
- repository root as Docker build context

The publish workflow is `.github/workflows/release.yml`.

- It runs:
  - on pushes to `main`
  - on published or edited GitHub releases
  - on `workflow_dispatch` with an image tag input
- It publishes a multi-platform image to `ghcr.io/snuffy2/hass-lost-apple-app`.
- It tags images as:
  - `edge` for pushes to `main`
  - the release semver and `latest` for non-prerelease GitHub releases
  - the raw `workflow_dispatch` input for manual runs
