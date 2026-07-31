"""Public package surface exposing metadata and configuration."""

from __future__ import annotations

from .__init__conf__ import print_info
from .config import get_config

__all__ = [
    "get_config",
    "print_info",
]
