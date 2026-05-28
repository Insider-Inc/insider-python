# Releasing `insider-python`

This repository uses GitHub Actions + PyPI Trusted Publishing.

## One-time setup

Do this once in PyPI and TestPyPI:

1. Create project `insider-python` on both registries.
2. Configure Trusted Publishing for repo:
   - Owner: `Insider-Inc`
   - Repository: `insider-python`
   - Workflow: `publish.yml`
   - Environment: _(leave empty unless you enforce one)_
3. Repeat for TestPyPI with the same repository/workflow.

If Trusted Publishing is configured, no API token secrets are needed.

## Release process

### 1) Prepare release commit

1. Update version in `pyproject.toml`.
2. Ensure changelog/release notes are updated.
3. Run local checks:

```bash
python -m pip install -e ".[dev]"
pytest -q
python -m build
python -m twine check dist/*
```

4. Commit and push to `main`.

### 2) Publish to TestPyPI

Run workflow manually:

- Actions -> `Publish SDK` -> `Run workflow`
- Choose target: `testpypi`

Validate install in a clean environment:

```bash
python -m venv .venv-test-install
source .venv-test-install/bin/activate
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple insider-python
python -c "import insider; print(insider.__version__)"
```

### 3) Publish to PyPI

1. Tag release:

```bash
git tag -a sdk-python-v0.1.0 -m "Release insider-python v0.1.0"
git push origin sdk-python-v0.1.0
```

2. Tag push triggers `Publish SDK` workflow to production PyPI.

### 4) Post-release checks

```bash
python -m venv .venv-prod-install
source .venv-prod-install/bin/activate
pip install insider-python
python -c "import insider; print(insider.__version__)"
```

## Failure policy

- If TestPyPI publish/install fails: fix and rerun, do not tag production.
- If PyPI publish fails: fix pipeline and publish same built version only if no
  artifact was accepted; otherwise bump version and release again.
