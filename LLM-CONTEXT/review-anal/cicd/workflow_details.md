# GitHub Actions Workflow Details

## CI Workflow Analysis (.github/workflows/ci.yml)

### Trigger Configuration

```yaml
on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]
  schedule:
    - cron: '17 3 * * *'  # Daily at 3:17 AM UTC
```

**Analysis:**
- ✅ Runs on every push to main/master
- ✅ Runs on all PRs targeting main/master
- ✅ Daily scheduled run at off-peak hours (3:17 AM UTC)
- ✅ Odd minute (17) reduces queue congestion

### Job 1: test (Matrix)

**Matrix Configuration:**
```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python: ["3.13", "3.x"]
```

**Total Combinations:** 6 (3 OS × 2 Python versions)

**Fail-Fast:** Disabled to run all combinations even if one fails

**Environment Variables:**
```yaml
env:
  PYO3_USE_ABI3_FORWARD_COMPATIBILITY: "1"
```

**Steps Breakdown:**

#### 1. Checkout & Setup
```yaml
- uses: actions/checkout@v5
- uses: actions/setup-python@v6
  with:
    python-version: ${{ matrix.python }}
    cache: 'pip'
    cache-dependency-path: 'pyproject.toml'
```
**Purpose:** Get code and setup Python with caching

#### 2. Install uv
```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v7
  with:
    enable-cache: true
```
**Purpose:** Fast Python package installer

#### 3. Extract Metadata
```yaml
- name: Extract project metadata
  shell: python
  run: |
    import os, tomllib
    from pathlib import Path
    data = tomllib.loads(Path('pyproject.toml').read_text('utf-8'))
    project = data['project']['name']
    module = project.replace('-', '_')
    dash = project.replace('_', '-')
    scripts = list(data['project'].get('scripts', {}).keys())
    cli_bin = scripts[0] if scripts else dash
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as env:
        env.write(f"PROJECT_NAME={project}\n")
        env.write(f"PACKAGE_MODULE={module}\n")
        env.write(f"CLI_BIN={cli_bin}\n")
```
**Purpose:** Dynamic project metadata extraction
**Sets Environment Variables:**
- `PROJECT_NAME=check_zpools`
- `PACKAGE_MODULE=check_zpools`
- `CLI_BIN=check_zpools`

#### 4. Platform-Specific Setup

**Windows:**
```yaml
- name: Install make on Windows
  if: runner.os == 'Windows'
  shell: pwsh
  run: |
    choco install -y make
    echo "C:\\ProgramData\\chocolatey\\bin" >> $env:GITHUB_PATH
```

**Linux:**
```yaml
- name: Install journald prerequisites
  if: runner.os == 'Linux'
  shell: bash
  run: |
    sudo apt-get update
    sudo apt-get install -y python3-systemd
```

#### 5. Dependency Installation
```yaml
- name: Upgrade pip
  shell: bash
  run: python -m pip install --upgrade pip

- name: Install dev deps
  shell: bash
  run: uv pip install -e .[dev] --system

- name: Install Windows Event Log prerequisites
  if: runner.os == 'Windows'
  shell: bash
  run: uv pip install pywin32 --system
```

#### 6. Caching

**Ruff Cache:**
```yaml
- name: Cache ruff
  uses: actions/cache@v4
  with:
    path: .ruff_cache
    key: ruff-${{ runner.os }}-${{ hashFiles('**/*.py') }}
    restore-keys: |
      ruff-${{ runner.os }}-
```

**Pyright Cache:**
```yaml
- name: Cache pyright
  uses: actions/cache@v4
  with:
    path: .pyright
    key: pyright-${{ runner.os }}-py${{ matrix.python }}-${{ hashFiles('**/*.py', 'pyproject.toml') }}
    restore-keys: |
      pyright-${{ runner.os }}-py${{ matrix.python }}-
      pyright-${{ runner.os }}-
```

**Cache Strategy:**
- **Ruff:** OS-specific, invalidates on any .py file change
- **Pyright:** OS + Python version specific, invalidates on code or config change
- **Restore Keys:** Hierarchical fallback for cache hits

#### 7. Test Suite Execution
```yaml
- name: Run full test suite (lint, types, tests, coverage, codecov)
  shell: bash
  env:
    TEST_VERBOSE: "1"
  run: make test
```

**What This Runs:**
1. Ruff format apply
2. Ruff format check (if STRICT_RUFF_FORMAT=true)
3. Ruff lint
4. Import-linter
5. Pyright
6. Bandit
7. pip-audit
8. Pytest with coverage
9. Codecov upload (if token available)

#### 8. Build & Verification
```yaml
- name: Build wheel/sdist
  shell: bash
  run: python -m build

- name: Verify wheel install in clean env
  shell: bash
  run: |
    python -m venv .venv_wheel
    . .venv_wheel/bin/activate 2>/dev/null || . .venv_wheel/Scripts/activate 2>/dev/null
    pip install dist/*.whl
    "$CLI_BIN" --version 2>/dev/null || python -m "$PACKAGE_MODULE" --version
```

**Purpose:**
- Ensure package builds correctly
- Verify wheel installs in clean environment
- Confirm CLI entry point works

### Job 2: pipx-uv

**Platform:** Ubuntu only
**Python:** 3.13

**Purpose:** Verify installation methods used by end users

**Steps:**

1. **Build wheel**
```bash
python -m pip install --upgrade pip build
python -m build
```

2. **Test pipx installation**
```bash
python -m pip install pipx
pipx install dist/*.whl
"$CLI_BIN" --version 2>/dev/null || python -m "$PACKAGE_MODULE" --version
```

3. **Test uv tool installation**
```bash
uv tool install .
"$CLI_BIN" --version 2>/dev/null || python -m "$PACKAGE_MODULE" --version
```

**Validation:**
- Confirms package installable via pipx
- Confirms package installable via uv tool
- Verifies CLI command works after installation

### Job 3: notebooks

**Platform:** Ubuntu only
**Python:** 3.13

**Purpose:** Ensure example notebooks remain executable

**Steps:**

1. **Install notebook runner**
```bash
python -m pip install --upgrade pip
pip install nbclient nbformat ipykernel jupyter_client
python -m ipykernel install --user --name python3 --display-name "Python 3"
```

2. **Execute notebook**
```python
from pathlib import Path
import nbformat
from nbclient import NotebookClient

nb_path = Path('notebooks/Quickstart.ipynb')
if not nb_path.exists():
    raise SystemExit(f"Notebook not found: {nb_path}")

notebook = nbformat.read(nb_path, as_version=4)
client = NotebookClient(
    notebook,
    timeout=900,
    kernel_name='python3',
    allow_errors=False,
)
client.execute()

out_path = Path('notebooks/Quickstart-executed.ipynb')
nbformat.write(notebook, out_path)
print(f"Executed notebook written to: {out_path}")
```

**Configuration:**
- Timeout: 900 seconds (15 minutes)
- Allow errors: False (strict execution)
- Kernel: python3

**Benefits:**
- Prevents example rot
- Ensures documentation accuracy
- Validates API stability

---

## Release Workflow Analysis (.github/workflows/release.yml)

### Trigger Configuration

```yaml
on:
  release:
    types: [published]
  push:
    tags:
      - 'v*'
  workflow_dispatch: {}
```

**Triggers:**
1. **Release published:** GitHub release created via UI or API
2. **Tag push:** Any tag starting with 'v' (e.g., v2.1.8)
3. **Manual dispatch:** Triggered manually via GitHub UI

**Recommended Flow:**
```bash
make release  # Creates tag + GitHub release → triggers workflow
```

### Job: build-and-publish

**Platform:** Ubuntu latest
**Permissions:**
```yaml
permissions:
  contents: read  # Minimal permissions (security best practice)
```

**Steps:**

#### 1. Verify PyPI Token
```bash
if [ -z "${{ secrets.PYPI_API_TOKEN }}" ]; then
  echo "::error title=Missing PyPI token::Set the PYPI_API_TOKEN secret..."
  exit 1
fi
```

**Purpose:**
- Fail fast if token not configured
- Provides helpful error message
- Prevents silent failures

#### 2. Setup & Build
```bash
python -m pip install --upgrade pip
uv pip install build --system
python -m build
```

**Output:**
- `dist/*.whl` (wheel)
- `dist/*.tar.gz` (sdist)

#### 3. Publish to PyPI
```yaml
- name: Publish to PyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    password: ${{ secrets.PYPI_API_TOKEN }}
    attestations: false
    skip-existing: true
```

**Configuration:**
- **attestations: false** - Disabled (could enable for provenance)
- **skip-existing: true** - Prevents errors on re-runs (idempotent)

**Security:**
- Uses official PyPA GitHub Action
- Token stored as secret (encrypted at rest)
- Rolling major tag (@release/v1) for latest features

#### 4. Upload Artifacts
```yaml
- name: Upload artifacts
  uses: actions/upload-artifact@v5
  with:
    name: dist
    path: dist/*
```

**Purpose:**
- Preserves build artifacts
- Allows download from GitHub UI
- Useful for debugging release issues

**Retention:** Default (90 days)

---

## CodeQL Workflow Analysis (.github/workflows/codeql.yml)

### Trigger Configuration

```yaml
on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]
  schedule:
    - cron: '0 8 * * 1'  # Weekly on Monday at 8 AM UTC
```

**Frequency:**
- Every push to main/master
- Every PR
- Weekly scheduled scan (Monday 8 AM UTC)

### Job: analyze

**Platform:** Ubuntu latest

**Permissions:**
```yaml
permissions:
  actions: read
  contents: read
  security-events: write  # Required for CodeQL results upload
```

**Matrix:**
```yaml
strategy:
  fail-fast: false
  matrix:
    language: [ 'python' ]
```

**Steps:**

#### 1. Initialize CodeQL
```yaml
- name: Initialize CodeQL
  uses: github/codeql-action/init@v4
  with:
    languages: ${{ matrix.language }}
```

**Purpose:**
- Sets up CodeQL analysis
- Downloads language databases
- Configures queries

#### 2. Autobuild
```yaml
- name: Autobuild
  uses: github/codeql-action/autobuild@v4
```

**Purpose:**
- Automatically builds Python code
- Extracts code structure
- Prepares for analysis

#### 3. Analyze
```yaml
- name: Perform CodeQL Analysis
  uses: github/codeql-action/analyze@v4
  with:
    category: "/language:${{ matrix.language }}"
```

**Purpose:**
- Runs security queries
- Identifies vulnerabilities
- Uploads results to GitHub Security tab

**What CodeQL Detects:**
- SQL injection
- Code injection
- Path traversal
- XSS vulnerabilities
- Insecure deserialization
- Hardcoded credentials
- Weak cryptography
- And more...

**Results:**
- Viewable in GitHub Security → Code scanning alerts
- Integrated with PR checks
- Email notifications on new findings

---

## Workflow Performance Analysis

### Build Times (Estimated)

**CI Workflow (per matrix job):**
- Checkout: 5s
- Python setup: 30s (with cache: 10s)
- uv setup: 10s
- Dependencies: 60s (with cache: 20s)
- Ruff: 5s (with cache: 2s)
- Pyright: 30s (with cache: 10s)
- Import-linter: 5s
- Bandit: 10s
- pip-audit: 15s
- Pytest: 30s
- Build: 15s
- Wheel install: 10s

**Total per job:** ~4-5 minutes (with cache)
**Total for all 6 jobs:** ~5 minutes (parallel execution)

**Release Workflow:**
- Setup: 30s
- Build: 15s
- PyPI publish: 20s
- Artifact upload: 10s

**Total:** ~1.5 minutes

**CodeQL Workflow:**
- Setup: 30s
- Initialize: 60s
- Autobuild: 30s
- Analyze: 120s

**Total:** ~4 minutes

### Cache Hit Rates (Expected)

**Scenario 1: Small code change**
- pip cache: 100% hit
- ruff cache: 90% hit (changed files invalidate)
- pyright cache: 95% hit

**Scenario 2: Dependency update**
- pip cache: 0% hit
- ruff cache: 100% hit
- pyright cache: 50% hit (pyproject.toml changed)

**Scenario 3: Major refactor**
- pip cache: 100% hit
- ruff cache: 0% hit
- pyright cache: 0% hit

### Optimization Opportunities

1. **Skip redundant jobs on docs-only changes**
```yaml
paths-ignore:
  - '**.md'
  - 'docs/**'
```

2. **Conditional notebook execution**
```yaml
- name: Check for notebook changes
  id: notebook_changes
  run: |
    if git diff --name-only ${{ github.event.before }} ${{ github.sha }} | grep 'notebooks/'; then
      echo "changed=true" >> $GITHUB_OUTPUT
    fi
- name: Execute notebooks
  if: steps.notebook_changes.outputs.changed == 'true'
  run: ...
```

3. **Separate lint/test jobs**
```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: make lint

  test:
    needs: lint
    strategy:
      matrix: ...
```

**Trade-off:** Faster feedback vs. reduced total runtime

---

## Workflow Security Analysis

### Secret Management

**Secrets Used:**
1. `PYPI_API_TOKEN` (release.yml)
2. `CODECOV_TOKEN` (test.py via environment)

**Best Practices:**
- ✅ Secrets stored encrypted
- ✅ Never logged or exposed
- ✅ Verified before use
- ✅ Minimal permissions

**Potential Improvement:**
- Migrate to OIDC trusted publishing (eliminates PYPI_API_TOKEN)

### Permissions

**Minimal Permissions:**
```yaml
# release.yml
permissions:
  contents: read  # Only read access

# codeql.yml
permissions:
  actions: read
  contents: read
  security-events: write  # Only what's needed
```

**Best Practice:** ✅ Follows principle of least privilege

### Supply Chain Security

**Current Measures:**
1. Pin action versions (v4, v5, v6, v7)
2. Use official actions (GitHub, PyPA, Astral)
3. pip-audit in test suite
4. Dependabot for updates

**Potential Improvements:**
1. Pin actions to commit SHA (stricter)
2. Enable provenance attestations
3. Generate SBOM

### Code Injection Risks

**Analysis:**
- ✅ No `${{ github.event.issue.title }}` in run commands
- ✅ No user input directly in shell commands
- ✅ Environment variables properly quoted

**Status:** No code injection vulnerabilities detected

---

## Comparison with Alternative CI Systems

### GitHub Actions vs. Alternatives

| Feature | GitHub Actions | GitLab CI | CircleCI | Jenkins |
|---------|---------------|-----------|----------|---------|
| **Integration** | Native | Native | 3rd party | 3rd party |
| **Matrix builds** | ✅ Excellent | ✅ Good | ✅ Good | ⚠️ Manual |
| **Caching** | ✅ Built-in | ✅ Built-in | ✅ Built-in | ⚠️ Plugins |
| **Security scanning** | ✅ CodeQL | ✅ SAST | ❌ External | ❌ External |
| **Cost (public)** | ✅ Free | ✅ Free | ⚠️ Limited | ❌ Self-host |
| **Artifact storage** | ✅ Built-in | ✅ Built-in | ✅ Built-in | ⚠️ Plugins |
| **Windows support** | ✅ Excellent | ⚠️ Limited | ✅ Good | ✅ Good |
| **macOS support** | ✅ Excellent | ⚠️ Limited | ✅ Good | ⚠️ Manual |

**Verdict:** GitHub Actions is the optimal choice for this project

### Why GitHub Actions Works Well Here

1. **Native Integration:** No external service setup
2. **Matrix Builds:** Clean syntax for multi-platform testing
3. **Marketplace:** Rich ecosystem (setup-python, setup-uv, etc.)
4. **Security:** CodeQL built-in
5. **Cost:** Free for public repositories
6. **Performance:** Caching is effective
7. **Developer Experience:** Logs integrated in PR view

---

**Analysis Complete**
**Workflow Status:** EXCELLENT
**Security Posture:** STRONG
**Performance:** OPTIMIZED
