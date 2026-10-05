"""Provide the ``python -m check_zpools`` entry point.

Runs :func:`check_zpools.cli.main`, the function the console script runs, so
exit codes, traceback handling and log runtime shutdown are identical however
the CLI is started.
"""

from __future__ import annotations

from . import cli

if __name__ == "__main__":
    raise SystemExit(cli.main())
