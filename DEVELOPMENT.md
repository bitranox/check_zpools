# Development

## Make Targets

| Target            | Description                                                                                |
|-------------------|--------------------------------------------------------------------------------------------|
| `help`            | Show help                                                                                  |
| `install`         | Install package editable                                                                   |
| `dev`             | Install package with dev extras                                                            |
| `test`            | Lint, type-check, run tests with coverage, upload to Codecov                               |
| `run`             | Run module CLI (requires dev install or src on PYTHONPATH)                                 |
| `version-current` | Print current version from pyproject.toml                                                  |
| `bump`            | Bump version (updates pyproject.toml and CHANGELOG.md)                                     |
| `bump-patch`      | Bump patch version (X.Y.Z -> X.Y.(Z+1))                                                    |
| `bump-minor`      | Bump minor version (X.Y.Z -> X.(Y+1).0)                                                    |
| `bump-major`      | Bump major version ((X+1).0.0)                                                             |
| `clean`           | Remove caches, build artifacts, and coverage                                               |
| `push`            | Run tests, prompt for/accept a commit message, create (allow-empty) commit, push to remote |
| `build`           | Build wheel/sdist artifacts via `python -m build`                                          |
| `menu`            | Interactive TUI to run targets and edit parameters (requires dev dep: textual)             |

### Target Parameters (env vars)

- **Global**
  - `PY` (default: `python3`) — interpreter used to run scripts
  - `PIP` (default: `pip`) — pip executable used by bootstrap/install

- **install**
  - No specific parameters (respects `PY`, `PIP`).

- **dev**
  - No specific parameters (respects `PY`, `PIP`).

- **test**
  - `COVERAGE=on|auto|off` (default: `on`) — controls pytest coverage run and Codecov upload
  - `SKIP_BOOTSTRAP=1` — skip auto-install of dev tools if missing
  - `TEST_VERBOSE=1` — echo each command executed by the test harness
  - Also respects `CODECOV_TOKEN` when uploading to Codecov

- **run**
  - No parameters via `make` (always shows `--help`). For custom args: `python scripts/run_cli.py -- <args>`.

- **version-current**
  - No parameters

- **bump**
  - `VERSION=X.Y.Z` — explicit target version
  - `PART=major|minor|patch` — semantic part to bump (default if `VERSION` not set: `patch`)

- **bump-patch** / **bump-minor** / **bump-major**
  - No parameters; shorthand for `make bump PART=...`

- **clean**
  - No parameters

- **push**
  - `REMOTE=<name>` (default: `origin`) — git remote to push to
  - `COMMIT_MESSAGE="..."` — optional commit message used by the automation; if unset, the target prompts (or uses the default `chore: update` when non-interactive).

- **build**
  - No parameters via `make`. Advanced: call the script directly, e.g. `python scripts/build.py --no-conda --no-nix`.

- **release**
  - `REMOTE=<name>` (default: `origin`) — git remote to push to
  - Advanced (via script): `python scripts/release.py --retries 5 --retry-wait 3.0`

## Interactive Menu (Textual)

`make menu` launches a Textual-powered TUI to browse targets, edit parameters, and run them with live output.

Install dev extras if you haven’t:

```bash
pip install -e .[dev]
```

Run the menu:

```bash
make menu
```

### Target Details

- `test`: single entry point for local CI — runs ruff lint + format check, pyright, pytest (including doctests) with coverage (enabled by default), and uploads coverage to Codecov if configured (reads `.env`).
  - Auto-bootstrap: `make test` will try to install dev tools (`pip install -e .[dev]`) if `ruff`/`pyright`/`pytest` are missing. Set `SKIP_BOOTSTRAP=1` to skip this behavior.
- `build`: creates wheel/sdist artifacts.
- `version-current`: prints current version from `pyproject.toml`.
- `bump`: updates `pyproject.toml` version and inserts a new section in `CHANGELOG.md`. Use `VERSION=X.Y.Z make bump` or `make bump-minor`/`bump-major`/`bump-patch`.
- Additional scripts (`pipx-*`, `uv-*`, `which-cmd`, `verify-install`) provide install/run diagnostics.

## Development Workflow

```bash
make test                 # ruff + pyright + pytest + coverage (default ON)
SKIP_BOOTSTRAP=1 make test  # skip auto-install of dev deps
COVERAGE=off make test       # disable coverage locally
COVERAGE=on make test        # force coverage and generate coverage.xml/codecov.xml
```

**Automation notes**

- `make push` prompts for a commit message (or reads `COMMIT_MESSAGE="..."`) and always pushes, creating an empty commit when there are no staged changes. The Textual menu (`make menu → push`) shows the same prompt via an input field.

### Versioning & Metadata

- Single source of truth for package metadata is `pyproject.toml` (`[project]`).
- The library reads its own installed metadata at runtime via `importlib.metadata` (see `src/check_zpool_status/__init__conf__.py`).
- Do not duplicate the version in code; bump only `pyproject.toml` and update `CHANGELOG.md`.
- Console script name is discovered from entry points; defaults to `check_zpool_status`.

### Dependency Auditing

- `make test` invokes `pip-audit` twice (with and without ignores). The default ignore list currently suppresses `GHSA-4xh5-x5gv-qwph` because the underlying transitive dependency ships a fix only in a pre-release build. Track upstream and remove the ignore as soon as a stable patch is available; in the meantime the audit still fails the run if any additional vulnerabilities appear.

### CI & Publishing

GitHub Actions workflows are included:

- `.github/workflows/ci.yml` — lint/type/test, build wheel/sdist, and verify pipx and uv installs (CI-only; no local install required).
- `.github/workflows/release.yml` — on tags `v*.*.*`, builds artifacts and publishes to PyPI when `PYPI_API_TOKEN` secret is set.

To publish a release:
1. Bump `pyproject.toml` version and update `CHANGELOG.md`.
2. Tag the commit (`git tag v0.1.1 && git push --tags`).
3. Ensure `PYPI_API_TOKEN` secret is configured in the repo.
4. Release workflow uploads wheel/sdist to PyPI.

### Local Codecov uploads

- `make test` (with coverage enabled) generates `coverage.xml` and `codecov.xml`, then attempts to upload via the Codecov CLI or the bash uploader.
- For private repos, set `CODECOV_TOKEN` (see `.env.example`) or export it in your shell.
- For public repos, a token is typically not required.
- Because Codecov requires a revision, the test harness commits (allow-empty) immediately before uploading. Remove or amend that commit after the run if you do not intend to keep it.

## Testing

### Test Philosophy

Tests follow a narrative, behavior-driven style:

- **Naming Convention**: `test_when_<condition>_<outcome>()` — describes behavior explicitly
- **Focus**: Each test case validates a single behavior
- **Readability**: Test names serve as specifications
- **Markers**: OS-specific tests use pytest markers (`@pytest.mark.os_agnostic`, `@pytest.mark.os_windows`, etc.)

### Running Tests

**Basic test run:**
```bash
make test
```

This executes the full test pipeline:
1. Ruff format (apply + check)
2. Ruff lint
3. Import-linter contracts
4. Pyright type-check
5. Bandit security scan
6. pip-audit vulnerability check
7. Pytest with coverage (doctests enabled)
8. Codecov upload

**Quick iterations:**
```bash
# Run tests without coverage
COVERAGE=off make test

# Skip auto-bootstrap of dev dependencies
SKIP_BOOTSTRAP=1 make test

# Run specific test file
python -m pytest tests/test_cli.py -v

# Run tests matching pattern
python -m pytest -k "test_when_hello" -v

# Show print statements during tests
python -m pytest tests/test_cli.py -v -s
```

### Coverage Requirements

- **Local Target**: 60% minimum (enforced by `pytest --cov-fail-under=60`)
- **CI Target**: 70% minimum (enforced by GitHub Actions)
- **Current Coverage**: ~75% (see badge in README.md)

**Note**: The mismatch between local (60%) and CI (70%) targets is intentional:
- Local 60% allows rapid iteration during development
- CI 70% ensures production quality before merge

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_cli.py              # CLI command behavior
├── test_behaviors.py        # Core business logic
├── test_alerting.py         # Email alerting
├── test_alert_state.py      # Alert state management
├── test_daemon.py           # Daemon mode
├── test_models.py           # Data models
├── test_monitor.py          # Pool monitoring
├── test_zfs_client.py       # ZFS command execution
├── test_zfs_parser.py       # ZFS output parsing
├── test_formatters.py       # Output formatters
└── test_*.py                # Additional test modules
```

### Writing Tests

**Example test structure:**
```python
def test_when_pool_is_healthy_no_issues_are_reported():
    """Verify healthy pools generate no alerts.

    Given: A pool with ONLINE health and low capacity
    When: The monitor checks the pool
    Then: No issues are returned
    """
    # Arrange
    pool = create_healthy_pool()
    monitor = PoolMonitor(config)

    # Act
    result = monitor.check_pool(pool)

    # Assert
    assert len(result.issues) == 0
```

**Key principles:**
- Use descriptive names that explain the scenario
- Follow Given/When/Then structure in docstrings
- Keep tests focused on one behavior
- Use fixtures for common setup (defined in `conftest.py`)
- Mock external dependencies (ZFS commands, SMTP, filesystem)

### Fixtures

Common fixtures from `conftest.py`:

- `temp_dir`: Temporary directory (auto-cleanup)
- `mock_zfs_client`: Mocked ZFS command execution
- `sample_pool_status`: Pre-configured pool status data
- `email_config`: Test email configuration
- `monitor_config`: Test monitor configuration

### Doctests

All public functions include docstring examples that run as tests:

```python
def parse_capacity(capacity_str: str) -> float:
    """Parse ZFS capacity percentage.

    >>> parse_capacity("45.2%")
    45.2
    >>> parse_capacity("100%")
    100.0
    """
    return float(capacity_str.rstrip('%'))
```

Run doctests: `pytest --doctest-modules src/`

### Coverage Reports

**Generate HTML coverage report:**
```bash
python -m pytest --cov=src/check_zpools --cov-report=html
# Open htmlcov/index.html in browser
```

**View terminal coverage:**
```bash
python -m pytest --cov=src/check_zpools --cov-report=term-missing -vv
```

### Test Markers

Use markers to categorize tests:

```python
@pytest.mark.os_agnostic
def test_when_config_is_loaded_it_parses_toml():
    """Cross-platform configuration test."""
    ...

@pytest.mark.requires_zfs
def test_when_zpool_command_runs_it_returns_status():
    """Test requiring actual ZFS installation."""
    ...
```

Run specific markers: `pytest -m os_agnostic -v`

### Continuous Integration

GitHub Actions runs tests on:
- **Platforms**: Ubuntu, macOS, Windows
- **Python Versions**: 3.13, 3.14 (latest available)
- **Checks**: Lint, type-check, security scan, tests, coverage upload

See `.github/workflows/ci.yml` for full CI pipeline configuration.
