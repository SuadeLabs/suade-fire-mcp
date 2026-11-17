# Contributing

## Development setup

```bash
git clone --branch v26.10 https://github.com/SuadeLabs/fire.git
git clone https://github.com/SuadeLabs/suade-fire-mcp.git
cd suade-fire-mcp
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"          # includes the ruff and black versions CI pins
export FIRE_REPO_ROOT=/absolute/path/to/fire
```

A source checkout has no bundled FIRE data, so `FIRE_REPO_ROOT` is always required during
development.

## Checks

```bash
pytest
ruff check . && black --check .
```

CI runs these on Python 3.10, 3.12 and 3.13 against the FIRE release pinned by
`ARG FIRE_VERSION` in the `Dockerfile`, which is the single source of truth for the FIRE
version. A non-blocking job also runs the tests against FIRE `master`, and a `package` job
builds and smoke-tests the release wheel.

## Layout

- `fire_mcp/server.py`: `create_server()`, transports and `/health`
- `fire_mcp/tools.py`, `resources.py`, `prompts.py`: the MCP surface. Thin wrappers that
  validate arguments and shape results.
- `fire_mcp/catalog.py`, `search.py`, `validation.py`, `batch.py`, `examples.py`, `docs.py`,
  `refs.py`, `loader.py`: the logic over FIRE's files
- `fire_mcp/repo.py`: where FIRE data is read from (`FIRE_REPO_ROOT`, then the bundled copy)
- `scripts/vendor_fire.py`, `scripts/check_wheel.py`: release packaging

When you change a tool, keep its parameter descriptions and its result types accurate. Models
read them, and the tests check every parameter has a description and every result matches its
output schema.

## Building a release wheel locally

```bash
python scripts/vendor_fire.py /absolute/path/to/fire --version v26.10
python -m build
```

`fire_mcp/_fire/` is gitignored. Delete it afterwards, or it will be used in place of
`FIRE_REPO_ROOT` when that is unset.

## Releasing

1. Open a PR bumping `version` in `pyproject.toml` **and** both `version` fields in
   `server.json` (a test checks they match). Merge it with a merge commit.
2. Tag the merge commit `vX.Y.Z` and push the tag. `.github/workflows/release.yml` then runs
   CI and publishes:
   - the Docker image to `ghcr.io/suadelabs/suade-fire-mcp` (`:latest` only for full releases)
   - the wheel and sdist to PyPI, via trusted publishing (environment `pypi`)
   - the MCP Registry entry (full releases only)

The tag must match the package version. PyPI never accepts the same version twice, so a bad
release needs a new version number.

To bump FIRE, change `ARG FIRE_VERSION` in the `Dockerfile`, the release-tag mentions in
`README.md` and here, and check the `fire-master` CI job has been passing.
