"""In-process SMTP server used as a real delivery target in tests.

Purpose
-------
Give the mail tests a genuine SMTP endpoint instead of a mock. ``btx_lib_mail``
drives the connection at the smtplib/socket level (capability probing, BDAT or
DATA framing, raw ``sendall``), so a stand-in built from ``MagicMock`` only ever
matches whichever internals that library happens to use today. A real server
speaks the protocol, which keeps these tests working across library releases and
lets them assert what was actually delivered rather than just a return value.

Why not aiosmtpd
----------------
It cannot serve the macOS CI runners, which run Homebrew Python 3.14: the
listening socket accepts the connection but the protocol never writes its 220
greeting, so every client times out waiting for it. Its own ``Controller`` hits
the same wall from the inside and reports "SMTP server started, but not
responding". This server is a few dozen lines of stdlib ``socketserver`` and
behaves identically on every OS and Python we support.

It implements only what a client needs to hand us a message: EHLO/HELO, AUTH
PLAIN and LOGIN, MAIL, RCPT, DATA, BDAT (RFC 3030), RSET, NOOP and QUIT. It has
no TLS, so tests must set ``use_starttls=False``.

Usage
-----
Prefer the ``smtp_sink`` / ``authenticating_smtp_sink`` fixtures in
``conftest.py``; use :func:`running_smtp_sink` directly only when a test needs a
sink with non-default settings.
"""

from __future__ import annotations

import base64
import socket
import socketserver
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from email import message_from_bytes
from email.message import Message
from typing import cast

# Credentials the authenticating sink accepts. Tests that exercise the
# authenticated path must send exactly these.
SINK_USERNAME = "testuser"
SINK_PASSWORD = "testpass"  # nosec B105 - test-only fixture credential, not a real secret

# Ceiling for the server thread to wind down on the way out. Shutdown is
# near-instant; this only stops a wedged thread from hanging the suite forever.
SINK_SHUTDOWN_TIMEOUT = 30.0

_SINK_DOMAIN = "sink.test"
_MAX_LINE = 65536


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
    require_auth: bool = False
    delivered: list[DeliveredMail] = field(default_factory=list)
    logins: list[tuple[str, str]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        """Forget everything recorded so far.

        One sink serves the whole test session rather than standing a server up
        per test, so each test clears it before running.
        """
        with self._lock:
            self.delivered.clear()
            self.logins.clear()

    def record_mail(self, mail: DeliveredMail) -> None:
        """Record a delivered message. Called from a connection thread."""
        with self._lock:
            self.delivered.append(mail)

    def check_login(self, username: str, password: str) -> bool:
        """Record a login attempt and report whether the credentials match."""
        with self._lock:
            self.logins.append((username, password))
        return username == SINK_USERNAME and password == SINK_PASSWORD

    @property
    def only_mail(self) -> DeliveredMail:
        """Return the single delivered mail, failing loudly if there is not exactly one."""
        if len(self.delivered) != 1:
            raise AssertionError(f"expected exactly one delivered mail, got {len(self.delivered)}")
        return self.delivered[0]


def _address_in(argument: str) -> str:
    """Pull the bare address out of a ``MAIL FROM:``/``RCPT TO:`` argument."""
    _, _, address = argument.partition(":")
    return address.strip().strip("<>")


class _SinkRequestHandler(socketserver.StreamRequestHandler):
    """Serve one SMTP conversation, appending any accepted mail to the sink."""

    @property
    def sink(self) -> SmtpSink:
        """Return the sink this connection records into.

        Narrowing the inherited ``server`` attribute itself would conflict with
        its declared type, so the cast lives here instead.
        """
        return cast("_SinkServer", self.server).sink

    def handle(self) -> None:
        self._sender = ""
        self._recipients: list[str] = []
        self._authenticated = not self.sink.require_auth

        self._reply(f"220 {_SINK_DOMAIN} sink ready")
        while True:
            line = self.rfile.readline(_MAX_LINE)
            if not line:
                return
            command, _, argument = line.decode("utf-8", "replace").strip().partition(" ")
            if not self._dispatch(command.upper(), argument.strip()):
                return

    def _dispatch(self, command: str, argument: str) -> bool:
        """Run one command. Returns False when the connection should close."""
        if command == "QUIT":
            self._reply("221 Bye")
            return False
        if command in ("EHLO", "HELO"):
            self._greet(command, argument)
        elif command == "AUTH":
            self._authenticate(argument)
        elif command == "MAIL":
            self._begin_envelope(argument)
        elif command == "RCPT":
            self._add_recipient(argument)
        elif command == "DATA":
            self._receive_data()
        elif command == "BDAT":
            self._receive_chunk(argument)
        elif command == "RSET":
            self._sender, self._recipients = "", []
            self._reply("250 OK")
        elif command == "NOOP":
            self._reply("250 OK")
        else:
            self._reply(f"500 Unrecognized command: {command}")
        return True

    def _greet(self, command: str, argument: str) -> None:
        if command == "HELO":
            self._reply(f"250 {_SINK_DOMAIN}")
            return
        extensions = ["8BITMIME", "SMTPUTF8", "CHUNKING"]
        if self.sink.require_auth:
            # Only mechanisms this server implements; advertising CRAM-MD5 would
            # make smtplib prefer a challenge we cannot answer.
            extensions.append("AUTH PLAIN LOGIN")
        self._reply_multiline(f"{_SINK_DOMAIN}", extensions + ["HELP"])

    def _authenticate(self, argument: str) -> None:
        mechanism, _, initial = argument.partition(" ")
        mechanism = mechanism.upper()
        if mechanism == "PLAIN":
            encoded = initial or self._challenge("")
            self._finish_auth(*_decode_plain(encoded))
        elif mechanism == "LOGIN":
            username = _b64_decode(initial or self._challenge("VXNlcm5hbWU6"))
            password = _b64_decode(self._challenge("UGFzc3dvcmQ6"))
            self._finish_auth(username, password)
        else:
            self._reply("504 Unrecognized authentication type")

    def _challenge(self, prompt: str) -> str:
        self._reply(f"334 {prompt}".rstrip())
        return self.rfile.readline(_MAX_LINE).decode("utf-8", "replace").strip()

    def _finish_auth(self, username: str, password: str) -> None:
        if self.sink.check_login(username, password):
            self._authenticated = True
            self._reply("235 2.7.0 Authentication successful")
        else:
            self._reply("535 5.7.8 Authentication credentials invalid")

    def _begin_envelope(self, argument: str) -> None:
        if not self._authenticated:
            self._reply("530 5.7.0 Authentication required")
            return
        self._sender = _address_in(argument)
        self._recipients = []
        self._reply("250 OK")

    def _add_recipient(self, argument: str) -> None:
        if not self._authenticated:
            self._reply("530 5.7.0 Authentication required")
            return
        self._recipients.append(_address_in(argument))
        self._reply("250 OK")

    def _receive_data(self) -> None:
        self._reply("354 End data with <CR><LF>.<CR><LF>")
        lines: list[bytes] = []
        while True:
            line = self.rfile.readline(_MAX_LINE)
            if not line or line in (b".\r\n", b".\n"):
                break
            # RFC 5321 dot-stuffing: a leading '.' was doubled by the sender.
            lines.append(line[1:] if line.startswith(b"..") else line)
        self._accept_message(b"".join(lines))
        self._reply("250 OK")

    def _receive_chunk(self, argument: str) -> None:
        size_text, _, marker = argument.partition(" ")
        payload = self.rfile.read(int(size_text)) or b""
        self._chunks = getattr(self, "_chunks", b"") + payload
        if marker.strip().upper() == "LAST":
            self._accept_message(self._chunks)
            self._chunks = b""
        self._reply("250 OK")

    def _accept_message(self, raw: bytes) -> None:
        self.sink.record_mail(
            DeliveredMail(
                sender=self._sender,
                recipients=tuple(self._recipients),
                message=message_from_bytes(raw),
            )
        )

    def _reply(self, text: str) -> None:
        self.wfile.write(text.encode("utf-8") + b"\r\n")
        self.wfile.flush()

    def _reply_multiline(self, first: str, rest: list[str]) -> None:
        lines = [f"250-{first}"] + [f"250-{item}" for item in rest[:-1]] + [f"250 {rest[-1]}"]
        self.wfile.write(("\r\n".join(lines) + "\r\n").encode("utf-8"))
        self.wfile.flush()


def _b64_decode(value: str) -> str:
    return base64.b64decode(value.encode("ascii")).decode("utf-8", "replace")


def _decode_plain(encoded: str) -> tuple[str, str]:
    """Split an AUTH PLAIN payload (``\\0user\\0password``) into its parts."""
    parts = base64.b64decode(encoded.encode("ascii")).split(b"\x00")
    if len(parts) < 3:
        return "", ""
    return parts[1].decode("utf-8", "replace"), parts[2].decode("utf-8", "replace")


class _SinkServer(socketserver.ThreadingTCPServer):
    """Threaded TCP server carrying the sink its handlers record into."""

    allow_reuse_address = True
    daemon_threads = True
    # A client that vanishes mid-conversation must not wedge its thread.
    timeout = SINK_SHUTDOWN_TIMEOUT

    def __init__(self, sink: SmtpSink, handler: Callable[..., socketserver.BaseRequestHandler]) -> None:
        self.sink = sink
        # Port 0 lets the OS assign a free port, which we read back after
        # binding. Nothing else can claim it in between.
        super().__init__(("127.0.0.1", 0), handler)

    def handle_error(self, request: object, client_address: object) -> None:
        """Swallow per-connection errors.

        A test that asserts a failure path (a rejected login, a client hanging
        up) would otherwise print a traceback from the serving thread and make a
        passing run look broken.
        """


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
    sink = SmtpSink(host="", require_auth=require_auth)
    server = _SinkServer(sink, _SinkRequestHandler)
    sink.host = f"127.0.0.1:{server.server_address[1]}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield sink
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=SINK_SHUTDOWN_TIMEOUT)


def _free_port() -> int:
    """Reserve and release a loopback port, returning its number."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextmanager
def unreachable_smtp_host() -> Generator[str]:
    """Yield a loopback host:port with nothing listening on it.

    Gives the failure-path tests a real connection refusal instead of a mocked
    exception, so they prove how the library and our wrapper handle the real
    error rather than one we invented.
    """
    yield f"127.0.0.1:{_free_port()}"
