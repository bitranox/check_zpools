"""Public package surface exposing greeting, failure, metadata, and configuration."""

from __future__ import annotations

from .behaviors import (
    CANONICAL_GREETING,
    emit_greeting,
    noop_main,
    raise_intentional_failure,
)
from .__init__conf__ import print_info
from .config import get_config

__all__ = [
    "CANONICAL_GREETING",
    "emit_greeting",
    "get_config",
    "noop_main",
    "print_info",
    "raise_intentional_failure",
]
