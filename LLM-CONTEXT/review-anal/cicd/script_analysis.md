# Build Scripts Analysis

## Overview

The `scripts/` directory contains a comprehensive automation framework that mirrors and extends CI/CD capabilities for local development. This analysis examines each script's purpose, implementation quality, and integration with the overall CI/CD pipeline.

---

## Core Scripts

### 1. scripts/test.py

**Purpose:** Comprehensive quality validation pipeline

**Complexity Analysis:**
- Main function: Well-refactored with helper functions
- Uses composition over complexity
- Clear separation of concerns

**Pipeline Stages:**

```python
1. Metadata synchronization (sync_metadata_module)
2. Bootstrap dev dependencies (bootstrap_dev)
3. Ruff format apply
4. Ruff format check (if STRICT_RUFF_FORMAT=true)
5. Ruff lint
6. Import-linter contracts
7. Pyright type checking
8. Bandit security scan
9. pip-audit vulnerability scan (guarded)
10. Pytest with coverage
11. Codecov upload (conditional)
```

**Key Features:**

#### Metadata Synchronization
```python
sync_metadata_module(PROJECT)
```
**Purpose:** Ensures `__init__conf__.py` matches `pyproject.toml`
**Why:** Single source of truth for version, author, etc.

#### Smart Coverage Handling
```python
if coverage == "on" or (coverage == "auto" and (os.getenv("CI") or os.getenv("CODECOV_TOKEN"))):
    # Run with coverage
else:
    # Run without coverage (faster local iteration)
```

**Modes:**
- `on`: Always run coverage
- `off`: Never run coverage
- `auto`: Run coverage in CI or if CODECOV_TOKEN set

#### Guarded pip-audit
```python
def _pip_audit_guarded() -> None:
    ignore_ids = _resolve_pip_audit_ignores()
    # Run with --ignore-vuln for known issues
    # Then verify no unexpected vulnerabilities
```

**Default Ignores:**
```python
_DEFAULT_PIP_AUDIT_IGNORES = ("GHSA-4xh5-x5gv-qwph",)
```

**Extensible:**
```bash
export PIP_AUDIT_IGNORE="GHSA-xxxx-xxxx-xxxx,GHSA-yyyy-yyyy-yyyy"
```

**Verification Logic:**
1. Run pip-audit with ignore list (human-readable output)
2. Run pip-audit with JSON output (parseable)
3. Parse JSON to extract vulnerabilities
4. Compare against allowlist
5. Fail if unexpected vulnerabilities found

**Benefits:**
- Documents known/accepted vulnerabilities
- Prevents regression to vulnerable versions
- Requires explicit acknowledgment of new vulnerabilities

#### Codecov Upload Logic
```python
def _upload_coverage_report(*, run_command: Callable[..., RunResult]) -> bool:
    if not Path("coverage.xml").is_file():
        return False

    if not os.getenv("CODECOV_TOKEN") and not os.getenv("CI"):
        click.echo("[codecov] CODECOV_TOKEN not configured; skipping...")
        return False

    uploader = shutil.which("codecovcli")
    if uploader is None:
        click.echo("[codecov] 'codecovcli' not found; install with 'pip install codecov-cli'")
        return False

    commit_sha = _resolve_commit_sha()
    branch = _resolve_git_branch()
    git_service = _resolve_git_service()
    slug = f"{PROJECT.repo_owner}/{PROJECT.repo_name}"

    args = [
        uploader, "upload-coverage",
        "--file", "coverage.xml",
        "--disable-search",
        "--fail-on-error",
        "--sha", commit_sha,
        "--name", f"local-{platform.system()}-{platform.python_version()}",
        "--flag", "local",
    ]
    if branch:
        args.extend(["--branch", branch])
    if git_service:
        args.extend(["--git-service", git_service])
    if slug:
        args.extend(["--slug", slug])

    result = run_command(args, env={"CODECOV_NO_COMBINE": "1"}, ...)
    return result.code == 0
```

**Git Integration:**
```python
def _resolve_commit_sha() -> str | None:
    sha = os.getenv("GITHUB_SHA")  # CI environment
    if sha:
        return sha.strip()
    # Fallback to git command
    proc = subprocess.run(["git", "rev-parse", "HEAD"], ...)
    return proc.stdout.strip() or None
```

**Strengths:**
- ✅ Graceful degradation (no codecovcli → skip)
- ✅ CI-aware (uses GITHUB_SHA if available)
- ✅ Local-friendly (falls back to git commands)
- ✅ Git service detection (github/gitlab/bitbucket)
- ✅ Proper error handling

#### Environment Management
```python
def _build_default_env() -> dict[str, str]:
    pythonpath = os.pathsep.join(filter(None, [
        str(PROJECT_ROOT / "src"),
        os.environ.get("PYTHONPATH")
    ]))
    return os.environ | {"PYTHONPATH": pythonpath}
```

**Purpose:** Ensure src/ is always in PYTHONPATH for imports

#### Verbose Mode
```python
if verbose:
    click.echo(f"  $ {display}")
    if env:
        overrides = {k: v for k, v in env.items() if os.environ.get(k) != v}
        if overrides:
            env_view = " ".join(f"{k}={v}" for k, v in overrides.items())
            click.echo(f"    env {env_view}")
```

**Benefits:**
- Shows exact commands run
- Shows environment overrides
- Aids debugging

**Activation:**
```bash
export TEST_VERBOSE=1
make test
```

#### Coverage Cleanup
```python
def _prune_coverage_data_files() -> None:
    """Delete SQLite coverage data shards to keep the Codecov CLI simple."""
    for path in Path.cwd().glob(".coverage*"):
        if path.is_dir() or path.suffix == ".xml":
            continue
        try:
            path.unlink()
        except FileNotFoundError:
            continue
```

**Purpose:** Remove SQLite .coverage.* files that can cause conflicts

**Overall Assessment:**
- **Complexity:** Well-managed through helper functions
- **Maintainability:** Excellent (clear structure, good names)
- **Reliability:** High (error handling, fallbacks)
- **Grade:** A+

---

### 2. scripts/build.py

**Purpose:** Build wheel and sdist artifacts

**Implementation:**
```python
def build_artifacts() -> None:
    _purge_dist()  # Remove stale artifacts
    sync_metadata_module(PROJECT)  # Ensure metadata current
    click.echo("[build] Building wheel/sdist via python -m build")
    build_result = run(["python", "-m", "build"], check=False, capture=False)
    click.echo(f"[build] {_status('success') if build_result.code == 0 else _failure('failed')}")
    if build_result.code != 0:
        raise SystemExit(build_result.code)
```

**Key Steps:**
1. **Purge dist/ directory**
   - Prevents stale artifacts from reaching PyPI
   - Ensures clean slate

2. **Sync metadata module**
   - Generates `__init__conf__.py` from `pyproject.toml`
   - Ensures version/author/etc. are current

3. **Build with python -m build**
   - PEP 517 compliant
   - Produces wheel (.whl) and sdist (.tar.gz)

**Strengths:**
- ✅ Simple and focused
- ✅ Proper cleanup
- ✅ Clear status reporting
- ✅ Uses official build tool

**Output:**
```
dist/
├── check_zpools-2.1.8-py3-none-any.whl
└── check_zpools-2.1.8.tar.gz
```

**Overall Assessment:**
- **Complexity:** Simple (appropriate for task)
- **Reliability:** High
- **Grade:** A

---

### 3. scripts/release.py

**Purpose:** Orchestrate full release workflow

**Implementation:**
```python
def release(*, remote: str = "origin") -> None:
    version = read_version_from_pyproject(Path("pyproject.toml"))
    if not version or not _looks_like_semver(version):
        raise SystemExit("[release] Could not read version X.Y.Z from pyproject.toml")

    click.echo(f"[release] Target version {version}")
    click.echo("[release] project diagnostics: " + ", ".join(PROJECT.diagnostic_lines()))

    _ensure_clean()  # Verify clean working tree
    bootstrap_dev()  # Ensure dev tools available

    click.echo("[release] Running validation suite (python -m scripts.test)")
    run(["python", "-m", "scripts.test"], capture=False)

    git_delete_tag("v", remote=remote)  # Clean up stray 'v' tag

    branch = git_branch()
    click.echo(f"[release] Pushing branch {branch} to {remote}")
    git_push(remote, branch)

    tag = f"v{version}"
    if git_tag_exists(tag):
        click.echo(f"[release] Tag {tag} already exists locally")
    else:
        git_create_annotated_tag(tag, f"Release {tag}")

    click.echo(f"[release] Pushing tag {tag}")
    git_push(remote, tag)  # This triggers release.yml

    if gh_available():
        if gh_release_exists(tag):
            gh_release_edit(tag, tag, f"Release {tag}")
        else:
            click.echo(f"[release] Creating GitHub release {tag}")
            gh_release_create(tag, tag, f"Release {tag}")
    else:
        click.echo("[release] gh CLI not found; skipping GitHub release creation")

    click.echo(f"[release] Done: {tag} tagged and pushed.")
```

**Safety Checks:**

#### 1. Version Validation
```python
def _looks_like_semver(v: str) -> bool:
    return bool(re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", v))
```
**Ensures:** X.Y.Z format (no v prefix, no prerelease suffixes)

#### 2. Clean Working Tree
```python
def _ensure_clean() -> None:
    if run(["bash", "-lc", "! git diff --quiet || ! git diff --cached --quiet"], check=False).code == 0:
        raise SystemExit("[release] Working tree not clean. Commit or stash changes first.")
```
**Prevents:** Releasing with uncommitted changes

#### 3. Full Test Suite
```python
run(["python", "-m", "scripts.test"], capture=False)
```
**Ensures:** All quality checks pass before release

**Workflow Steps:**
```
1. Read version from pyproject.toml
2. Validate semver format
3. Check git working tree is clean
4. Bootstrap dev dependencies
5. Run full test suite
   ├─ Lint (Ruff)
   ├─ Type check (Pyright)
   ├─ Security (Bandit, pip-audit)
   ├─ Tests (pytest + coverage)
   └─ Codecov upload
6. Delete stray 'v' tag (local and remote)
7. Push current branch to origin
8. Create annotated tag vX.Y.Z
9. Push tag to origin → triggers .github/workflows/release.yml
   └─ Build wheel/sdist
   └─ Publish to PyPI
   └─ Upload artifacts
10. Create GitHub release (if gh CLI available)
```

**GitHub CLI Integration:**
```python
def gh_release_create(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "create", tag, "-t", title, "-n", body], check=False)

def gh_release_edit(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "edit", tag, "-t", title, "-n", body], check=False)

def gh_release_exists(tag: str) -> bool:
    return subprocess.call(
        ["bash", "-lc", f"gh release view {shlex.quote(tag)} >/dev/null 2>&1"],
        stdout=subprocess.DEVNULL
    ) == 0
```

**Graceful Degradation:**
- If `gh` not found, skips GitHub release creation
- Tag push still triggers release.yml workflow
- PyPI publish still happens

**Overall Assessment:**
- **Safety:** Excellent (multiple checks)
- **Automation:** High (minimal manual steps)
- **Reliability:** High (graceful degradation)
- **Grade:** A+

---

### 4. scripts/push.py

**Purpose:** Safe commit and push with validation

**Implementation:**
```python
def push(*, remote: str = "origin", message: str | None = None) -> None:
    metadata = get_project_metadata()
    sync_metadata_module(metadata)
    version = read_version_from_pyproject(Path("pyproject.toml")) or "unknown"

    click.echo("[push] project diagnostics: " + ", ".join(metadata.diagnostic_lines()))
    click.echo(f"[push] version={version}")

    branch = git_branch()
    click.echo(f"[push] branch={branch} remote={remote}")

    click.echo("[push] Running local checks (python -m scripts.test)")
    run(["python", "-m", "scripts.test"], capture=False)

    click.echo("[push] Committing and pushing (single attempt)")
    run(["git", "add", "-A"], capture=False)  # Stage all changes

    staged = run(["bash", "-lc", "! git diff --cached --quiet"], check=False)
    commit_message = _resolve_commit_message(message)

    if staged.code != 0:
        click.echo("[push] No staged changes detected; creating empty commit")

    run(["git", "commit", "--allow-empty", "-m", commit_message], capture=False)
    click.echo(f"[push] Commit message: {commit_message}")

    run(["git", "push", "-u", remote, branch], capture=False)
```

**Commit Message Resolution:**
```python
def _resolve_commit_message(message: str | None) -> str:
    default_message = os.environ.get("COMMIT_MESSAGE", "chore: update").strip() or "chore: update"

    # 1. Explicit argument
    if message is not None:
        return message.strip() or default_message

    # 2. Environment variable
    env_message = os.environ.get("COMMIT_MESSAGE")
    if env_message is not None:
        final = env_message.strip() or default_message
        click.echo(f"[push] Using commit message from COMMIT_MESSAGE: {final}")
        return final

    # 3. Interactive prompt (if TTY available)
    if sys.stdin.isatty():
        return click.prompt("[push] Commit message", default=default_message)

    # 4. Try /dev/tty for non-interactive with TTY
    try:
        with open("/dev/tty", "r+", encoding="utf-8", errors="ignore") as tty:
            tty.write(f"[push] Commit message [{default_message}]: ")
            tty.flush()
            response = tty.readline()
    except OSError:
        click.echo("[push] Non-interactive input; using default commit message")
        return default_message
    except KeyboardInterrupt:
        raise SystemExit("[push] Commit aborted by user")

    response = response.strip()
    return response or default_message
```

**Message Priority:**
1. Function argument (`--message`)
2. Environment variable (`COMMIT_MESSAGE`)
3. Interactive prompt (if stdin is TTY)
4. TTY fallback (for SSH sessions)
5. Default (`"chore: update"`)

**Usage Modes:**
```bash
# Interactive
make push

# Environment variable
COMMIT_MESSAGE="feat: add new feature" make push

# CLI argument
python -m scripts.push --message "fix: resolve bug"
```

**Safety Features:**
- ✅ Syncs metadata before commit
- ✅ Runs full test suite before push
- ✅ Stages all changes (git add -A)
- ✅ Allows empty commits (useful for CI trigger)
- ✅ Sets upstream branch (-u)

**Overall Assessment:**
- **Safety:** Excellent (tests before push)
- **Flexibility:** High (multiple message sources)
- **Developer Experience:** Excellent (interactive + scriptable)
- **Grade:** A

---

### 5. scripts/bump_version.py

**Purpose:** Semver version bumping and CHANGELOG updates

**Implementation:**
```python
def bump_semver(current: str, part: str) -> str:
    major, minor, patch = (int(token) for token in (current.split(".") + ["0", "0"])[:3])
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "minor":
        minor, patch = minor + 1, 0
    else:  # patch
        patch += 1
    return f"{major}.{minor}.{patch}"
```

**Examples:**
```python
bump_semver("1.2.3", "patch")  # → "1.2.4"
bump_semver("1.2.3", "minor")  # → "1.3.0"
bump_semver("1.2.3", "major")  # → "2.0.0"
```

**pyproject.toml Update:**
```python
def _write_new_version(pyproject: Path, version: str) -> str:
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("version not found in pyproject.toml")

    previous = match.group(1)
    replacement = text[:match.start(1)] + version + text[match.end(1):]
    pyproject.write_text(replacement, encoding="utf-8")

    print(f"[bump] pyproject.toml: {previous} -> {version}")
    return previous
```

**CHANGELOG Update:**
```python
def _update_changelog(changelog: Path, version: str) -> None:
    today = _dt.date.today().isoformat()
    entry = f"## [{version}] - {today}\n\n- _Describe changes here._\n\n"

    if changelog.exists():
        lines = changelog.read_text(encoding="utf-8").splitlines(True)
        # Find first existing version section
        insert_idx = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
        lines[insert_idx:insert_idx] = [entry]
        changelog.write_text("".join(lines), encoding="utf-8")
    else:
        changelog.write_text("# Changelog\n\n" + entry, encoding="utf-8")

    print(f"[bump] CHANGELOG.md: inserted section for {version}")
```

**CHANGELOG Format:**
```markdown
# Changelog

## [2.1.9] - 2025-11-20

- _Describe changes here._

## [2.1.8] - 2025-11-19

- Existing changes...
```

**Wrapper Scripts:**
```python
# scripts/bump_patch.py
bump(part="patch")

# scripts/bump_minor.py
bump(part="minor")

# scripts/bump_major.py
bump(part="major")

# scripts/bump.py
bump(version="X.Y.Z")  # or part="major|minor|patch"
```

**Overall Assessment:**
- **Correctness:** High (proper semver logic)
- **Usability:** Excellent (multiple interfaces)
- **Automation:** High (CHANGELOG update)
- **Grade:** A

---

### 6. scripts/_utils.py

**Purpose:** Shared automation utilities

**Size:** 782 lines (comprehensive)

**Key Components:**

#### A. Data Structures
```python
@dataclass
class RunResult:
    code: int
    out: str
    err: str

@dataclass
class ProjectMetadata:
    name: str
    description: str
    slug: str
    repo_url: str
    repo_host: str
    repo_owner: str
    repo_name: str
    homepage: str
    import_package: str
    coverage_source: str
    scripts: dict[str, str]
    metadata_module: Path
    version: str
    summary: str
    author_name: str
    author_email: str
    shell_command: str
```

#### B. Subprocess Wrapper
```python
def run(
    cmd: Sequence[str] | str,
    *,
    check: bool = True,
    capture: bool = True,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    dry_run: bool = False,
) -> RunResult:
    # Shell vs. list handling
    # Dry-run support
    # Structured result
    # Error handling
```

**Benefits:**
- Consistent error handling
- Structured results (not CompletedProcess)
- Dry-run support for testing
- Shell command support

#### C. Metadata Extraction
```python
def get_project_metadata(pyproject: Path = Path("pyproject.toml")) -> ProjectMetadata:
    """Extract project metadata from pyproject.toml with caching."""
    # Refactored from D-grade (29 complexity, 101 lines)
    # to A-grade (4 complexity, ~40 lines) via helper functions
```

**Refactored Helpers:**
```python
_extract_project_name()       # Complexity: A (2)
_extract_description()         # Complexity: A (2)
_parse_repository_url()        # Complexity: A (4)
_extract_urls()                # Complexity: A (2)
_derive_summary()              # Complexity: A (4)
_extract_author_field()        # Complexity: A (2)
_parse_authors_list()          # Complexity: A (5)
_extract_author_info()         # Complexity: A (2)
_determine_shell_command()     # Complexity: A (2)
_build_metadata_module_path()  # Complexity: A (1)
```

**Original:** D (29), 101 lines
**Refactored:** A (4), ~40 lines + helpers
**Improvement:** ✅ Excellent refactoring

#### D. Metadata Module Generation
```python
def sync_metadata_module(project: ProjectMetadata) -> None:
    """Write __init__conf__.py so the constants mirror pyproject.toml."""
    content = _render_metadata_module(project)
    module_path = project.metadata_module
    module_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        existing = module_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        existing = ""

    if existing == content:
        return  # No changes needed

    module_path.write_text(content, encoding="utf-8")
```

**Generated Module:**
```python
# src/check_zpools/__init__conf__.py (auto-generated)
name = "check_zpools"
title = "Zpool Monitoring Daemon"
version = "2.1.8"
homepage = "https://github.com/bitranox/check_zpools"
author = "bitranox"
author_email = "bitranox@gmail.com"
shell_command = "check_zpools"

LAYEREDCONF_VENDOR: str = "bitranox"
LAYEREDCONF_APP: str = "Check Zpools"
LAYEREDCONF_SLUG: str = "check_zpools"

def print_info() -> None:
    """Print the summarised metadata block used by the CLI info command."""
    # ... implementation ...
```

**Benefits:**
- Single source of truth (pyproject.toml)
- No runtime metadata queries (importlib.metadata)
- Faster imports
- lib_layered_config integration

#### E. Git Helpers
```python
def git_branch() -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True).out.strip()

def git_delete_tag(name: str, *, remote: str | None = None) -> None:
    run(["git", "tag", "-d", name], check=False, capture=True)
    if remote:
        run(["git", "push", remote, f":refs/tags/{name}"], check=False)

def git_tag_exists(name: str) -> bool:
    return subprocess.call(
        ["bash", "-lc", f"git rev-parse -q --verify {shlex.quote('refs/tags/' + name)} >/dev/null"],
        stdout=subprocess.DEVNULL,
    ) == 0

def git_create_annotated_tag(name: str, message: str) -> None:
    run(["git", "tag", "-a", name, "-m", message])

def git_push(remote: str, ref: str) -> None:
    run(["git", "push", remote, ref])
```

#### F. GitHub CLI Helpers
```python
def gh_available() -> bool:
    return cmd_exists("gh")

def gh_release_exists(tag: str) -> bool:
    return subprocess.call(
        ["bash", "-lc", f"gh release view {shlex.quote(tag)} >/dev/null 2>&1"],
        stdout=subprocess.DEVNULL
    ) == 0

def gh_release_create(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "create", tag, "-t", title, "-n", body], check=False)

def gh_release_edit(tag: str, title: str, body: str) -> None:
    run(["gh", "release", "edit", tag, "-t", title, "-n", body], check=False)
```

#### G. Bootstrap Dev Dependencies
```python
def bootstrap_dev() -> None:
    needs_dev_install = False

    # Check if dev tools are available
    if not (cmd_exists("ruff") and cmd_exists("pyright")):
        needs_dev_install = True
    else:
        try:
            from importlib import import_module
            import_module("pytest_asyncio")
        except ModuleNotFoundError:
            needs_dev_install = True

    # Upgrade pip first (security)
    pip_upgrade = run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        check=False,
        capture=True,
    )

    # Handle SHA256 verification errors in CI
    if pip_upgrade.code != 0:
        combined_output = f"{pip_upgrade.out}\n{pip_upgrade.err}".lower()
        ci_token = os.getenv("CI", "").strip().lower()
        is_ci = ci_token in {"1", "true", "yes"}
        sha_error = "sha256" in combined_output and "hash" in combined_output

        if is_ci and sha_error:
            print("[bootstrap] pip upgrade failed due to SHA256 verification; continuing on CI")
        else:
            # Print output and fail
            raise SystemExit("pip upgrade failed; see output above")

    # Install dev dependencies if needed
    if needs_dev_install:
        print("[bootstrap] Installing dev dependencies via 'pip install -e .[dev]'")
        install_cmd = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
        if sys.platform.startswith("linux"):
            install_cmd.insert(4, "--break-system-packages")
        run(install_cmd)

    # Try to install sqlite3 if missing
    try:
        from importlib import import_module
        import_module("sqlite3")
    except Exception:
        sqlite_cmd = [sys.executable, "-m", "pip", "install", "pysqlite3-binary"]
        if sys.platform.startswith("linux"):
            sqlite_cmd.insert(4, "--break-system-packages")
        run(sqlite_cmd, check=False)
```

**Features:**
- ✅ Smart detection (only install if needed)
- ✅ Pip upgrade with SHA256 error handling
- ✅ Linux --break-system-packages support
- ✅ SQLite3 fallback (coverage dependency)

**Overall Assessment:**
- **Quality:** Excellent refactoring (D→A grade)
- **Functionality:** Comprehensive utilities
- **Maintainability:** High (helper functions)
- **Grade:** A+

---

## Script Integration Analysis

### Dependency Graph

```
Makefile
├── test → scripts.test
│   ├── _utils.bootstrap_dev()
│   ├── _utils.sync_metadata_module()
│   └── (runs all quality checks)
│
├── push → scripts.push
│   ├── _utils.sync_metadata_module()
│   ├── scripts.test (via subprocess)
│   └── git commands
│
├── build → scripts.build
│   ├── _utils.sync_metadata_module()
│   └── python -m build
│
├── release → scripts.release
│   ├── _utils.bootstrap_dev()
│   ├── scripts.test (via subprocess)
│   ├── git commands (_utils helpers)
│   └── gh commands (_utils helpers)
│
└── bump → scripts.bump → scripts.bump_version.py
```

### Common Patterns

1. **Metadata Synchronization**
   - Always run before test/build/push
   - Ensures `__init__conf__.py` is current
   - Single source of truth

2. **Test Suite Integration**
   - push runs test before commit
   - release runs test before tag
   - Prevents broken code from reaching remote

3. **Helper Function Usage**
   - All scripts use `_utils.run()` for subprocesses
   - Consistent error handling
   - Structured results

4. **Git Operations**
   - Centralized in `_utils.py`
   - Proper error handling
   - Shell escaping (shlex.quote)

---

## Performance Analysis

### Script Execution Times (Estimated)

| Script | Cold | Warm (cache) | Notes |
|--------|------|--------------|-------|
| test.py | 120s | 30s | Most expensive (all checks) |
| build.py | 15s | 10s | Quick (just build) |
| release.py | 150s | 60s | Includes test + git ops |
| push.py | 130s | 40s | Includes test + git ops |
| bump*.py | <1s | <1s | Just file edits |

**Optimization Opportunities:**

1. **Parallel Linting**
```python
# Currently sequential:
ruff format
ruff check
pyright
bandit

# Could parallelize:
with ThreadPoolExecutor() as executor:
    futures = [
        executor.submit(run_ruff_format),
        executor.submit(run_ruff_check),
        executor.submit(run_pyright),
        executor.submit(run_bandit),
    ]
    for future in as_completed(futures):
        result = future.result()
        if result.code != 0:
            # Handle error
```

**Trade-off:** More complex vs. ~20s savings

2. **Skip Tests on Docs-Only Changes**
```python
def files_changed() -> list[str]:
    result = run(["git", "diff", "--name-only", "HEAD^", "HEAD"], capture=True)
    return result.out.splitlines()

def should_run_tests() -> bool:
    changed = files_changed()
    return any(not f.endswith('.md') and not f.startswith('docs/') for f in changed)
```

**Trade-off:** Safety vs. speed

---

## Security Analysis

### Secret Handling

**Good Practices:**
- ✅ Secrets loaded from environment, not hardcoded
- ✅ .env files excluded from git
- ✅ Clear warnings in .env.example

**Used Secrets:**
1. `CODECOV_TOKEN` - Loaded in test.py
2. `PYPI_API_TOKEN` - Used in release.yml
3. `CHECK_ZPOOLS_EMAIL_SMTP_PASSWORD` - Application config

**Loading Mechanism:**
```python
def _ensure_codecov_token() -> None:
    if os.getenv("CODECOV_TOKEN"):
        _refresh_default_env()
        return

    env_path = Path(".env")
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        if key.strip() == "CODECOV_TOKEN":
            token = value.strip().strip("\"'")
            if token:
                os.environ.setdefault("CODECOV_TOKEN", token)
                _refresh_default_env()
            break
```

**Security Assessment:**
- ✅ Safe (reads from .env, never writes secrets)
- ✅ Environment variable takes precedence
- ✅ No secret logging

### Command Injection Risks

**Analysis:**
```python
# Safe: Uses list of arguments
run(["git", "push", remote, branch])

# Potentially unsafe: Shell string
run(["bash", "-lc", f"gh release view {shlex.quote(tag)} >/dev/null 2>&1"])
                                    ^^^^^^^^^^^^^^^^
# Safe: Uses shlex.quote()
```

**shlex.quote() Usage:**
```python
import shlex

# All user input is quoted:
git_tag_exists(name: str):
    return subprocess.call(
        ["bash", "-lc", f"git rev-parse -q --verify {shlex.quote('refs/tags/' + name)} >/dev/null"],
        ...
    )
```

**Security Assessment:**
- ✅ No command injection vulnerabilities
- ✅ Proper input sanitization
- ✅ Minimal shell usage

---

## Recommendations

### Immediate Improvements

1. **Add Type Hints to _utils.py**
   - Current: Partial type hints
   - Target: Full type coverage
   - Benefit: Better IDE support, type safety

2. **Document Environment Variables**
   - Create: docs/environment_variables.md
   - List all used variables
   - Document defaults and behavior

3. **Add Script Tests**
   - Create: tests/test_scripts/
   - Test: metadata extraction, version bumping, etc.
   - Coverage: Increase confidence in automation

### Future Enhancements

4. **Parallel Lint Execution**
   - Implement: ThreadPoolExecutor for independent checks
   - Benefit: ~20s time savings
   - Risk: Increased complexity

5. **Smart Test Skipping**
   - Implement: File change detection
   - Benefit: Faster push on docs-only changes
   - Risk: Could skip needed tests

6. **Enhanced Release Notes**
   - Extract CHANGELOG.md entries
   - Include in GitHub release
   - Benefit: Better release documentation

---

## Conclusion

### Script Quality Summary

| Script | Complexity | Safety | Maintainability | Grade |
|--------|-----------|--------|-----------------|-------|
| test.py | Well-managed | High | Excellent | A+ |
| build.py | Simple | High | Excellent | A |
| release.py | Moderate | Excellent | Excellent | A+ |
| push.py | Moderate | Excellent | Excellent | A |
| bump_version.py | Simple | High | Good | A |
| _utils.py | Well-refactored | High | Excellent | A+ |

### Overall Assessment

The scripts/ directory demonstrates **professional-grade automation** with:

**Strengths:**
- Comprehensive functionality
- Strong safety guarantees
- Excellent refactoring (D→A grade)
- Clear separation of concerns
- Good error handling
- Graceful degradation

**Areas for Enhancement:**
- Type hint coverage (partial)
- Test coverage (scripts not tested)
- Performance optimization (parallelization)
- Documentation (environment variables)

**Final Grade: A+ (Excellent)**

The automation framework is production-ready, maintainable, and provides excellent developer experience. The suggested improvements are optional enhancements that would elevate an already excellent system.

---

**Analysis Complete**
