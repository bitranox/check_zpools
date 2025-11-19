# CI/CD Quick Reference - check_zpools

## Common Tasks

### Local Development

```bash
# Install dev dependencies
make dev

# Run full test suite
make test

# Quick iteration (no coverage)
STRICT_RUFF_FORMAT=false make test

# Verbose test output
TEST_VERBOSE=1 make test

# Run CLI
make run
```

### Version Management

```bash
# Bump version (patch: 2.1.8 → 2.1.9)
make bump-patch

# Bump minor version (2.1.8 → 2.2.0)
make bump-minor

# Bump major version (2.1.8 → 3.0.0)
make bump-major

# Manual version
make bump VERSION=2.2.0

# Check current version
make version-current
```

### Git Operations

```bash
# Safe push (runs tests first)
make push

# With custom commit message
COMMIT_MESSAGE="feat: add new feature" make push

# Push without triggering CI (not recommended)
git push origin master
```

### Release

```bash
# Full release workflow
make release

# What it does:
# 1. Validates version (X.Y.Z format)
# 2. Checks git working tree is clean
# 3. Runs full test suite
# 4. Creates tag vX.Y.Z
# 5. Pushes tag → triggers PyPI publish
# 6. Creates GitHub release
```

### Build

```bash
# Build wheel and sdist
make build

# Output: dist/check_zpools-X.Y.Z-py3-none-any.whl
#         dist/check_zpools-X.Y.Z.tar.gz
```

### Cleanup

```bash
# Remove artifacts
make clean

# Removes: __pycache__, .pytest_cache, .coverage*,
#          coverage.xml, dist/, build/, *.egg-info
```

---

## GitHub Actions Workflows

### CI Workflow

**Triggers:**
- Push to main/master
- Pull requests
- Daily at 3:17 AM UTC

**Matrix:**
- OS: Ubuntu, macOS, Windows
- Python: 3.13, 3.x
- Total: 6 jobs

**Steps:**
1. Ruff format + check
2. Ruff lint
3. Import-linter
4. Pyright type check
5. Bandit security scan
6. pip-audit vulnerability scan
7. Pytest with coverage
8. Codecov upload
9. Build wheel/sdist
10. Verify wheel installation
11. pipx/uv installation tests
12. Notebook execution

**Duration:** ~5 minutes (parallel)

### Release Workflow

**Triggers:**
- Push to v* tags
- GitHub release published
- Manual dispatch

**Steps:**
1. Verify PYPI_API_TOKEN
2. Build wheel/sdist
3. Publish to PyPI
4. Upload artifacts

**Duration:** ~1.5 minutes

### CodeQL Workflow

**Triggers:**
- Push to main/master
- Pull requests
- Weekly (Monday 8 AM UTC)

**Steps:**
1. Initialize CodeQL
2. Autobuild
3. Analyze
4. Upload results

**Duration:** ~4 minutes

---

## Environment Variables

### CI/CD

| Variable | Purpose | Required |
|----------|---------|----------|
| `CODECOV_TOKEN` | Codecov upload | CI/local |
| `PYPI_API_TOKEN` | PyPI publishing | Release |
| `GITHUB_TOKEN` | GitHub API | Auto-provided |
| `CI` | CI detection | Auto-set |
| `GITHUB_SHA` | Commit SHA | Auto-set |
| `GITHUB_REF_NAME` | Branch name | Auto-set |

### Development

| Variable | Purpose | Default |
|----------|---------|---------|
| `TEST_VERBOSE` | Verbose test output | false |
| `STRICT_RUFF_FORMAT` | Strict format check | true |
| `PIP_AUDIT_IGNORE` | Vulnerability allowlist | GHSA-4xh5-x5gv-qwph |
| `COMMIT_MESSAGE` | Default commit message | "chore: update" |

### Application

| Variable | Purpose | Example |
|----------|---------|---------|
| `CHECK_ZPOOLS_EMAIL_SMTP_HOSTS` | SMTP servers | smtp.gmail.com:587 |
| `CHECK_ZPOOLS_EMAIL_FROM_ADDRESS` | Sender address | noreply@example.com |
| `CHECK_ZPOOLS_EMAIL_SMTP_USERNAME` | SMTP username | user@example.com |
| `CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD` | SMTP password | (secret) |
| `CHECK_ZPOOLS_EMAIL_USE_STARTTLS` | Use STARTTLS | true |
| `CHECK_ZPOOLS_EMAIL_TIMEOUT` | SMTP timeout | 30.0 |

---

## File Locations

### Configuration Files

```
.github/
├── workflows/
│   ├── ci.yml           # Main CI pipeline
│   ├── release.yml      # PyPI publishing
│   └── codeql.yml       # Security scanning
├── dependabot.yml       # Dependency updates
└── (no CODEOWNERS yet)

.devcontainer/
├── devcontainer.json    # VS Code/Codespaces config
└── settings.json        # VS Code settings

codecov.yml              # Codecov configuration
pyproject.toml           # Project metadata + tool config
Makefile                 # Task runner
.env.example             # Environment variable template
.env                     # Local secrets (git-ignored)
```

### Generated Files

```
src/check_zpools/
└── __init__conf__.py    # Auto-generated from pyproject.toml

dist/                    # Build artifacts
├── *.whl               # Wheel distribution
└── *.tar.gz            # Source distribution

.coverage*              # Coverage data files
coverage.xml            # Coverage report (for Codecov)

.ruff_cache/            # Ruff cache
.pyright/               # Pyright cache
```

---

## Security

### Secrets Management

**Never commit:**
- `.env` files with real values
- API tokens
- Passwords
- Private keys

**Use:**
- GitHub Secrets for CI/CD tokens
- `.env` for local development (git-ignored)
- Environment variables for production

**Current Secrets:**
1. `PYPI_API_TOKEN` (GitHub Secrets)
2. `CODECOV_TOKEN` (optional, loaded from .env)
3. Email SMTP password (application config)

### Vulnerability Scanning

**Tools:**
- CodeQL (weekly + on push/PR)
- Bandit (every test run)
- pip-audit (every test run)

**Allowlist:**
```bash
export PIP_AUDIT_IGNORE="GHSA-4xh5-x5gv-qwph"
```

**Process:**
1. pip-audit detects vulnerability
2. Assess if it affects this project
3. If safe: Add to allowlist + document
4. If unsafe: Update dependency ASAP

---

## Coverage

### Targets

| Level | Minimum | Target | Config |
|-------|---------|--------|--------|
| Local | 60% | - | pyproject.toml |
| CI | 70% | 70% | codecov.yml |

### Commands

```bash
# Run with coverage
make test

# Coverage report only
make coverage

# Upload to Codecov (requires token)
CODECOV_TOKEN=xxx make test
```

### Exclusions

**Not Covered:**
- tests/
- scripts/
- `__init__conf__.py` (auto-generated)

---

## Troubleshooting

### Tests Failing Locally

```bash
# Clean caches
make clean

# Reinstall dependencies
make dev

# Run with verbose output
TEST_VERBOSE=1 make test

# Skip strict format check (quick iteration)
STRICT_RUFF_FORMAT=false make test
```

### GitHub Actions Failing

**Check:**
1. Workflow logs in GitHub UI
2. Specific job/step that failed
3. Environment differences (OS, Python version)

**Common Issues:**
- Platform-specific imports (use `if sys.platform == ...`)
- Missing system dependencies (journald, pywin32)
- Flaky tests (add retry logic or skip in CI)

### Release Issues

**PyPI token error:**
```
::error title=Missing PyPI token::Set the PYPI_API_TOKEN secret...
```
**Fix:** Add secret in GitHub Settings → Secrets

**Tag already exists:**
```bash
# Delete local tag
git tag -d vX.Y.Z

# Delete remote tag
git push origin :refs/tags/vX.Y.Z

# Recreate
make release
```

**Clean tree check failed:**
```
[release] Working tree not clean. Commit or stash changes first.
```
**Fix:**
```bash
git status  # Check what's changed
git add -A && git commit -m "..."  # or
git stash  # or
git checkout -- .  # (careful!)
```

### Coverage Upload Failing

**codecovcli not found:**
```bash
pip install codecov-cli
```

**Token not set:**
```bash
# Create .env file
echo "CODECOV_TOKEN=your-token-here" > .env

# Or export
export CODECOV_TOKEN=your-token-here
```

---

## Best Practices

### Before Pushing

```bash
# Always run tests first
make test

# Use safe push (includes tests)
make push
```

### Before Releasing

```bash
# 1. Bump version
make bump-patch

# 2. Update CHANGELOG.md
#    Edit the "Describe changes here" section

# 3. Commit changes
git add -A
git commit -m "chore: bump version to X.Y.Z"

# 4. Run release
make release
```

### Code Changes

```bash
# 1. Make changes
# 2. Run tests
make test

# 3. If tests pass, commit
git add -A
git commit -m "feat: description"

# 4. Push safely
make push
```

### Dependency Updates

```bash
# 1. Update pyproject.toml
# 2. Reinstall
make dev

# 3. Run tests
make test

# 4. If vulnerabilities found
#    Check if they affect this project
#    Add to allowlist if safe:
export PIP_AUDIT_IGNORE="GHSA-xxxx-xxxx-xxxx"
make test

# 5. Commit
git add pyproject.toml
git commit -m "deps: update dependencies"
```

---

## Performance Tips

### Faster Local Testing

```bash
# Skip coverage (faster)
COVERAGE=off make test

# Skip strict format check
STRICT_RUFF_FORMAT=false make test

# Both
COVERAGE=off STRICT_RUFF_FORMAT=false make test
```

### Cache Warming

```bash
# First run: slow (no cache)
make test

# Second run: faster (warm cache)
make test
```

### CI Optimization

**Workflow already optimized with:**
- Dependency caching (pip, ruff, pyright)
- Matrix parallelization
- Smart cache keys
- Platform-specific setup

---

## Integration with IDEs

### VS Code

**DevContainer:**
1. Install "Remote - Containers" extension
2. Open folder in VS Code
3. Click "Reopen in Container"
4. Auto-installs dependencies
5. Jupyter kernel ready

**Local Development:**
```json
// .vscode/settings.json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.linting.enabled": true,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

### PyCharm

**Setup:**
1. Open project
2. Settings → Project → Python Interpreter
3. Add interpreter → Virtualenv → Existing
4. Select .venv/bin/python
5. Settings → Tools → Python Integrated Tools
6. Default test runner: pytest

**Run Configuration:**
- Script: `scripts/test.py`
- Working directory: project root

---

## Useful Links

### Documentation

- [CLAUDE.md](/media/srv-main-softdev/projects/tools/check_zpools/CLAUDE.md) - Development guidelines
- [DEVELOPMENT.md](/media/srv-main-softdev/projects/tools/check_zpools/DEVELOPMENT.md) - Setup instructions
- [CONTRIBUTING.md](/media/srv-main-softdev/projects/tools/check_zpools/CONTRIBUTING.md) - Contribution guide
- [CHANGELOG.md](/media/srv-main-softdev/projects/tools/check_zpools/CHANGELOG.md) - Version history

### External

- [GitHub Repository](https://github.com/bitranox/check_zpools)
- [PyPI Package](https://pypi.org/project/check-zpools/)
- [Codecov Dashboard](https://codecov.io/gh/bitranox/check_zpools)
- [GitHub Actions](https://github.com/bitranox/check_zpools/actions)

### Tools

- [Ruff](https://docs.astral.sh/ruff/) - Linter and formatter
- [Pyright](https://github.com/microsoft/pyright) - Type checker
- [pytest](https://docs.pytest.org/) - Testing framework
- [Codecov](https://docs.codecov.com/) - Coverage reporting
- [GitHub Actions](https://docs.github.com/actions) - CI/CD platform

---

## Cheat Sheet

### Quick Commands

```bash
# Essential
make test          # Run all checks
make push          # Commit + push safely
make release       # Tag + publish

# Version bumps
make bump-patch    # X.Y.Z → X.Y.(Z+1)
make bump-minor    # X.Y.Z → X.(Y+1).0
make bump-major    # X.Y.Z → (X+1).0.0

# Utilities
make clean         # Remove artifacts
make build         # Build distributions
make dev           # Install dev deps
make run           # Run CLI
```

### Critical Paths

**Development:**
```
Edit code → make test → make push
```

**Release:**
```
make bump-patch → Edit CHANGELOG.md → make release
```

**Emergency fix:**
```
Fix code → make test → git commit → git push → make bump-patch → make release
```

---

**Last Updated:** 2025-11-19
**Version:** 2.1.8
**Status:** Production-Ready ✅
