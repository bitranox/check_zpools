"""CLI command implementations extracted from cli.py.

Each command module contains the full implementation logic,
leaving cli.py as a thin orchestration layer.
"""

from __future__ import annotations

from .check import check_command
from .config_deploy import config_deploy_command
from .config_show import config_show_command
from .daemon import daemon_command
from .send_email import send_email_command
from .send_notification import send_notification_command
from .service_install import service_install_command
from .service_status import service_status_command
from .service_uninstall import service_uninstall_command

__all__ = [
    "send_email_command",
    "send_notification_command",
    "config_deploy_command",
    "service_install_command",
    "service_uninstall_command",
    "service_status_command",
    "check_command",
    "daemon_command",
    "config_show_command",
]
