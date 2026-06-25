# Claude Code Guidelines for check_zpools

## Session Initialization

When starting a new session, read and apply the following system prompt files from `/media/srv-main-softdev/projects/softwarestack/systemprompts`:

### Core Guidelines (Always Apply)
- `core_programming_solid.md`

### Bash-Specific Guidelines
When working with Bash scripts:
- use skill `bitranox:bash-reference` when in doubt of bash features or syntax
- `core_programming_solid.md`
- use skill `bitranox:bash-clean-architecture`
- `bash_clean_code.md`
- `bash_small_functions.md`

### Python-Specific Guidelines
When working with Python code:
- `core_programming_solid.md`
- `python_solid_architecture_enforcer.md`
- use skill `bitranox:python-clean-architecture`
- `python_clean_code.md`
- `python_small_functions_style.md`
- use skill `bitranox:python-use-modern-libraries`
- `python_lib_structure_template.md`

### Additional Guidelines
- `self_documenting.md`
- `self_documenting_template.md`
- `python_jupyter_notebooks.md`
- `python_testing.md`

## Project Structure

```
check_zpools/
├── .github/
│   └── workflows/              # GitHub Actions CI/CD workflows
├── docs/                       # Project documentation
│   └── systemdesign/           # System design documents
├── notebooks/                  # Jupyter notebooks for experiments
├── src/
│   └── check_zpools/           # Main Python package
│       ├── cli_commands/        # CLI command modules
│       │   └── commands/        # Individual command implementations
│       │       ├── alias_create.py
│       │       ├── alias_delete.py
│       │       ├── check.py
│       │       ├── config_deploy.py
│       │       ├── config_show.py
│       │       ├── daemon.py
│       │       ├── send_email.py
│       │       ├── send_notification.py
│       │       ├── service_install.py
│       │       ├── service_status.py
│       │       └── service_uninstall.py
│       ├── __init__.py          # Package initialization
│       ├── __init__conf__.py    # Static metadata constants (synced from pyproject.toml)
│       ├── __main__.py          # Module entry point (python -m check_zpools)
│       ├── alert_state.py       # Alert deduplication state management
│       ├── alerting.py          # Email alert formatting and sending
│       ├── alias_manager.py     # Shell alias creation/removal
│       ├── behaviors.py         # Orchestration layer (CLI ↔ domain)
│       ├── cli.py               # CLI group and root command wiring
│       ├── cli_email_handlers.py # Shared email validation for CLI commands
│       ├── cli_errors.py        # Centralized CLI error handlers
│       ├── cli_traceback.py     # Traceback state management utilities
│       ├── config.py            # Layered configuration loader
│       ├── config_deploy.py     # Config file deployment to system dirs
│       ├── config_show.py       # Config display for CLI
│       ├── daemon.py            # Long-running monitoring daemon
│       ├── defaultconfig.toml   # Bundled default configuration
│       ├── formatters.py        # Output formatting (JSON, text, bytes)
│       ├── logging_setup.py     # Centralized logging initialization
│       ├── mail.py              # SMTP email adapter
│       ├── models.py            # Domain models (PoolStatus, CheckResult, etc.)
│       ├── monitor.py           # Pool health/capacity threshold checking
│       ├── py.typed             # PEP 561 marker
│       ├── service_install.py   # Systemd service lifecycle management
│       ├── zfs_client.py        # ZFS subprocess command adapter
│       └── zfs_parser.py        # ZFS JSON output parser
├── tests/                       # Test suite
│   ├── conftest.py              # Shared fixtures and OS markers
│   ├── test_alert_state.py
│   ├── test_alerting.py
│   ├── test_alias_manager.py
│   ├── test_behaviors.py
│   ├── test_cli.py
│   ├── test_cli_commands_integration.py
│   ├── test_cli_errors.py
│   ├── test_cli_traceback.py
│   ├── test_config.py
│   ├── test_config_deploy.py
│   ├── test_daemon.py
│   ├── test_formatters.py
│   ├── test_logging_setup.py
│   ├── test_mail.py
│   ├── test_metadata.py
│   ├── test_models.py
│   ├── test_module_entry.py
│   ├── test_monitor.py
│   ├── test_service_status.py
│   └── test_zfs_parser.py
├── CLAUDE.md                    # Claude Code guidelines (this file)
├── CHANGELOG.md                 # Version history
├── CODE_ARCHITECTURE.md         # Architecture documentation
├── CONTRIBUTING.md              # Contribution guidelines
├── DEVELOPMENT.md               # Development setup guide
├── INSTALL.md                   # Installation instructions
├── LICENSE                      # MIT license
├── Makefile                     # Make targets for common tasks
├── README.md                    # Project overview
├── SECURITY.md                  # Security policy
├── codecov.yml                  # Codecov configuration
└── pyproject.toml               # Project metadata & dependencies
```

## Versioning & Releases

- **Single Source of Truth**: Package version is in `pyproject.toml` (`[project].version`)
- **Version Bumps**: update `pyproject.toml` , `CHANGELOG.md` and update the constants in `src/../__init__conf__.py` according to `pyproject.toml`  
    - Automation rewrites `src/check_zpools/__init__conf__.py` from `pyproject.toml`, so runtime code imports generated constants instead of querying `importlib.metadata`.
    - After updating project metadata (version, summary, URLs, authors) run `make test` to regenerate the metadata module before committing.
- **Release Tags**: Format is `vX.Y.Z` (push tags for CI to build and publish)

## Common Make Targets

| Target            | Description                                                                     |
|-------------------|---------------------------------------------------------------------------------|
| `build`           | Build wheel/sdist artifacts                                                     |
| `bump`            | Bump version (VERSION=X.Y.Z or PART=major\|minor\|patch) and update changelog  |
| `bump-major`      | Increment major version ((X+1).0.0)                                            |
| `bump-minor`      | Increment minor version (X.Y.Z → X.(Y+1).0)                                    |
| `bump-patch`      | Increment patch version (X.Y.Z → X.Y.(Z+1))                                    |
| `clean`           | Remove caches, coverage, and build artifacts (includes `dist/` and `build/`)   |
| `dev`             | Install package with dev extras                                                |
| `help`            | Show make targets                                                              |
| `install`         | Editable install                                                               |
| `menu`            | Interactive TUI menu                                                           |
| `push`            | Commit changes and push to GitHub (no CI monitoring)                           |
| `release`         | Tag vX.Y.Z, push, sync packaging, run gh release if available                  |
| `run`             | Run module entry (`python -m ... --help`)                                      |
| `test`            | Lint, format, type-check, run tests with coverage, upload to Codecov           |
| `version-current` | Print current version from `pyproject.toml`                                    |

## Coding Style & Naming Conventions

Follow the guidelines in `python_clean_code.md` for all Python code.

## Architecture Overview

- use skill `bitranox:python-clean-architecture` when designing and implementing features.

## Security & Configuration

- `.env` files are for local tooling only (CodeCov tokens, etc.)
- **NEVER** commit secrets to version control
- Rich logging should sanitize payloads before rendering

## Documentation & Translations

### Web Documentation
- Update only English docs under `/website/docs`
- Other languages are translated automatically
- When in doubt, ask before modifying non-English documentation

### App UI Strings (i18n)
- Update only `sources/_locales/en` for string changes
- Other languages are translated automatically
- When in doubt, ask before modifying non-English locales

## Commit & Push Policy

### Pre-Push Requirements
- **Always run `make test` before pushing** to avoid lint/test breakage
- Ensure all tests pass and code is properly formatted

### Post-Push Monitoring
- Monitor GitHub Actions for errors after pushing
- Attempt to correct any CI/CD errors that appear

## Claude Code Workflow

When working on this project:
1. Read relevant system prompts at session start
2. Apply appropriate coding guidelines based on file type
3. Run `make test` before commits
4. Follow versioning guidelines for releases
5. Monitor CI after pushing changes

## Code Quality

Deliberately accepted items — do not flag in future reviews:

- **Pyright `reportUnknown*` suppressions**: External libraries (pydantic, rich_click, lib_log_rich, lib_cli_exit_tools) lack source-resolvable types in the build environment, causing cascading `Unknown` warnings. The 5 `reportUnknown*` and `reportMissingTypeArgument` rules are set to `"none"` to suppress this noise. Re-evaluate if type stubs become available for these libraries.
- **No dedicated test file for `zfs_client.py`**: Indirect coverage through `test_daemon.py`, `test_behaviors.py`, and `test_cli_commands_integration.py` is sufficient. The module is exercised via integration paths rather than isolated unit tests.
- **No dedicated test file for `config_show.py`**: Indirect coverage through `test_cli.py` is sufficient. Display formatting is exercised via CLI integration paths.
