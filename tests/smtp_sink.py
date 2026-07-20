"""In-process SMTP server used as a real delivery target in tests.

Purpose
-------
Give the mail tests a genuine SMTP endpoint instead of a mock. ``btx_lib_mail``
drives the connection at the smtplib/socket level (capability probing, BDAT or
DATA framing, raw ``sendall``), so a stand-in built from ``MagicMock`` only ever
matches whichever internals that library happens to use today. A real server
speaks the protocol, which keeps these tests working across library releases and
lets them assert what was actually delivered rather than just a return value.

Usage
-----
Prefer the ``smtp_sink`` / ``authenticating_smtp_sink`` fixtures in
``conftest.py``; use :func:`running_smtp_sink` directly only when a test needs a
sink with non-default settings.
"""

from __future__ import annotations

import socket
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from email import message_from_bytes
from email.message import Message
from typing import Any

from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword

# Credentials the authenticating sink accepts. Tests that exercise the
# authenticated path must send exactly these.
SINK_USERNAME = "testuser"
SINK_PASSWORD = "testpass"  # nosec B105 - test-only fixture credential, not a real secret

# aiosmtpd spends this budget on BOTH starting the event-loop thread and then
# probing that the server answers: respond_timeout = ready_timeout - startup.
# Its 5s default assumes a developer laptop; on a loaded CI runner startup alone
# can consume nearly all of it, leaving the probe to time out against a server
# that is in fact healthy.
SINK_READY_TIMEOUT = 30.0


@dataclass(frozen=True)
class DeliveredMail:
    """One message as the server received it, parsed back into a MIME object."""

    sender: str
    recipients: tuple[str, ...]
    message: Message

    @property
    def subject(self) -> str:
        """Return the decoded ``Subject`` header, or an empty string when absent."""
        return str(self.message.get("Subject", ""))

    def text_part(self) -> str:
        """Return the ``text/plain`` body."""
        return self._part_of_subtype("plain")

    def html_part(self) -> str:
        """Return the ``text/html`` body, or an empty string when the mail has none."""
        return self._part_of_subtype("html")

    def _part_of_subtype(self, subtype: str) -> str:
        for part in self.message.walk():
            if part.get_content_maintype() == "text" and part.get_content_subtype() == subtype:
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(part.get_content_charset() or "utf-8")
        return ""


@dataclass
class SmtpSink:
    """A running SMTP server plus the mail and logins it has seen."""

    host: str
    delivered: list[DeliveredMail] = field(default_factory=list)
    logins: list[tuple[str, str]] = field(default_factory=list)

    def reset(self) -> None:
        """Forget everything recorded so far.

        A sink is shared across a test session (starting a server per test is
        what overruns aiosmtpd's readiness budget on slow CI runners), so each
        test clears it before running.
        """
        self.delivered.clear()
        self.logins.clear()

    @property
    def only_mail(self) -> DeliveredMail:
        """Return the single delivered mail, failing loudly if there is not exactly one."""
        if len(self.delivered) != 1:
            raise AssertionError(f"expected exactly one delivered mail, got {len(self.delivered)}")
        return self.delivered[0]


class _RecordingHandler:
    """aiosmtpd handler that accepts every message and records it."""

    def __init__(self, sink: SmtpSink) -> None:
        self._sink = sink

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:
        self._sink.delivered.append(
            DeliveredMail(
                sender=envelope.mail_from,
                recipients=tuple(envelope.rcpt_tos),
                message=message_from_bytes(envelope.content),
            )
        )
        return "250 Message accepted for delivery"


def _free_port() -> int:
    """Reserve and release a loopback port, returning its number.

    The tiny race between release and the server binding is unavoidable with
    aiosmtpd, whose controller cannot report back an OS-assigned port.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _make_authenticator(sink: SmtpSink) -> Any:
    """Build an aiosmtpd authenticator that records logins and checks credentials."""

    def authenticate(server: Any, session: Any, envelope: Any, mechanism: str, auth_data: Any) -> AuthResult:
        # Every rejection must carry handled=False. AuthResult.handled defaults to
        # True, which tells aiosmtpd the authenticator already wrote the status
        # line; it then sends nothing and the client blocks until its socket
        # timeout instead of seeing "535 Authentication credentials invalid".
        if not isinstance(auth_data, LoginPassword):
            return AuthResult(success=False, handled=False)
        username = auth_data.login.decode()
        password = auth_data.password.decode()
        sink.logins.append((username, password))
        if username == SINK_USERNAME and password == SINK_PASSWORD:
            return AuthResult(success=True)
        return AuthResult(success=False, handled=False)

    return authenticate


@contextmanager
def running_smtp_sink(*, require_auth: bool = False) -> Generator[SmtpSink]:
    """Run an SMTP sink on loopback for the duration of the block.

    Parameters
    ----------
    require_auth:
        When True the server advertises AUTH over the plain connection and
        rejects anything but :data:`SINK_USERNAME` / :data:`SINK_PASSWORD`.

    Yields
    ------
    SmtpSink:
        Sink whose ``host`` goes straight into ``EmailConfig.smtp_hosts``.
    """
    port = _free_port()
    sink = SmtpSink(host=f"127.0.0.1:{port}")
    controller_options: dict[str, Any] = {}
    if require_auth:
        # The sink never offers STARTTLS, so AUTH has to be allowed in the clear.
        controller_options["authenticator"] = _make_authenticator(sink)
        controller_options["auth_require_tls"] = False

    controller = Controller(
        _RecordingHandler(sink),
        hostname="127.0.0.1",
        port=port,
        ready_timeout=SINK_READY_TIMEOUT,
        **controller_options,
    )
    controller.start()
    try:
        yield sink
    finally:
        controller.stop()


@contextmanager
def unreachable_smtp_host() -> Generator[str]:
    """Yield a loopback host:port with nothing listening on it.

    Gives the failure-path tests a real connection refusal instead of a mocked
    exception, so they prove how the library and our wrapper handle the real
    error rather than one we invented.
    """
    yield f"127.0.0.1:{_free_port()}"
