"""Who may use a served viewer: the token link, sessions, TLS and ``--allow``.

Every server, also one on the loopback interface, asks for a token. The URL
printed at startup carries it (``/?token=…``); a correct token gets a session
cookie and a redirect to the same address without it. Scripts may send it as
``Authorization: token …`` instead. Jupyter works the same way.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import ssl
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

TOKEN_ENV = "STOMS_TOKEN"
TOKEN_FILE_ENV = "STOMS_TOKEN_FILE"
# Tokens chosen by the user: without lockout or delays, only a long random
# token is safe to guess against. token_urlsafe(32) has 43 characters.
MIN_TOKEN_LENGTH = 32
# The session cookie's name ends in the port: browsers keep cookies apart
# by host name, not by port, so two viewers on one computer need two names.
SESSION_COOKIE = "stoms_session"
# Sessions one server keeps; the oldest goes first. A browser that opens the
# link again keeps its session, so only cookie-less clients add many.
MAX_SESSIONS = 1000
# Seconds a name lookup may take at startup (slow DNS, e.g. on a VPN).
LOOKUP_TIMEOUT = 1.0
# Seconds a client may take for the TLS handshake.
HANDSHAKE_TIMEOUT = 10

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class AccessError(ValueError):
    """Access options that cannot be used (token, ``--allow``, certificates)."""


@dataclass(frozen=True)
class AccessOptions:
    """How a server lets people in.

    ``token`` None takes it from ``STOMS_TOKEN``/``STOMS_TOKEN_FILE``, or makes
    a random one. ``allow`` empty lets every address connect. ``uploads`` None
    allows "+ Add structures" on loopback binds only. ``certfile`` (with an
    optional ``keyfile``) turns on HTTPS; ``tls`` is its context when the
    caller has already loaded it (so a key's passphrase is asked once).
    """

    token: str | None = None
    allow: tuple[Network, ...] = ()
    uploads: bool | None = None
    certfile: Path | None = None
    keyfile: Path | None = None
    tls: ssl.SSLContext | None = field(default=None, compare=False)


def make_token_command() -> str:
    return (
        'uv run python -c "import secrets; print(secrets.token_urlsafe(32))"'
    )


def resolve_token(environ: Mapping[str, str] | None = None) -> str:
    """The token from ``STOMS_TOKEN`` or the file ``STOMS_TOKEN_FILE`` names,
    or a new random one."""
    environ = os.environ if environ is None else environ
    value, file = environ.get(TOKEN_ENV), environ.get(TOKEN_FILE_ENV)
    if value and file:
        raise AccessError(f"set {TOKEN_ENV} or {TOKEN_FILE_ENV}, not both")
    if file:
        try:
            value = Path(file).read_text().strip()
        except OSError as error:
            raise AccessError(
                f"cannot read {TOKEN_FILE_ENV} ({file}): {error.strerror}"
            ) from error
        source = f"the file {TOKEN_FILE_ENV} names"
    else:
        source = TOKEN_ENV
    if not value:
        return secrets.token_urlsafe(32)
    return check_token(value, source)


def check_token(value: str, source: str = "the token") -> str:
    if (
        len(value) < MIN_TOKEN_LENGTH
        or not value.isprintable()
        or " " in value
    ):
        raise AccessError(
            f"the token in {source} must be at least {MIN_TOKEN_LENGTH} "
            "characters without spaces; make one with: " + make_token_command()
        )
    return value


def parse_allow(text: str) -> tuple[Network, ...]:
    """``"10.0.0.0/8,192.168.1.7"`` → the networks (one address is a /32)."""
    networks = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError as error:
            raise AccessError(f"--allow: {error}") from error
    if not networks:
        raise AccessError("--allow needs at least one address range")
    return tuple(networks)


def address_allowed(address: str, allow: tuple[Network, ...]) -> bool:
    """Whether a client address lies in one of ``allow`` (all if empty)."""
    if not allow:
        return True
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in network for network in allow)


def is_loopback(host: str) -> bool:
    """Whether binding ``host`` keeps the server on this computer."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_wildcard(host: str) -> bool:
    return host in ("", "0.0.0.0", "::")


def tls_context(certfile: Path, keyfile: Path | None) -> ssl.SSLContext:
    """A server context for the user's certificate, TLS 1.2 or newer."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(certfile, keyfile)
    except FileNotFoundError as error:
        raise AccessError(
            f"certificate or key not found: {error.filename}"
        ) from error
    except (OSError, ssl.SSLError) as error:
        raise AccessError(
            f"cannot use the certificate {certfile}"
            + (f" with the key {keyfile}" if keyfile else "")
            + f": {error}"
        ) from error
    return context


def certificate_names(certfile: Path) -> list[str]:
    """The DNS names (then IP addresses) the certificate is valid for.

    The standard library decodes a certificate only through this private
    helper; if it is missing, the caller falls back to the host name.
    """
    try:
        decoded = ssl._ssl._test_decode_cert(str(certfile))  # type: ignore[attr-defined]
    except (AttributeError, OSError, ssl.SSLError, ValueError):
        return []
    names = [v for k, v in decoded.get("subjectAltName", ()) if k == "DNS"]
    addresses = [
        v for k, v in decoded.get("subjectAltName", ()) if k == "IP Address"
    ]
    if not names and not addresses:
        for rdn in decoded.get("subject", ()):
            names += [v for k, v in rdn if k == "commonName"]
    return [n for n in names if "*" not in n] + addresses


T = TypeVar("T")


def with_timeout(
    lookup: Callable[[], T], default: T, timeout: float = LOOKUP_TIMEOUT
) -> T:
    """``lookup()``, or ``default`` when it fails or takes too long.

    Name lookups cannot be cancelled; a slow one finishes in a daemon thread
    while the server starts without its answer.
    """
    result: list[T] = []

    def run() -> None:
        with contextlib.suppress(OSError):
            result.append(lookup())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    return result[0] if result else default


def resolves(name: str) -> bool:
    """Whether ``name`` resolves on this computer (within LOOKUP_TIMEOUT)."""
    return with_timeout(lambda: bool(socket.getaddrinfo(name, None)), False)


class LateNames:
    """Names found by a slow lookup (``socket.getfqdn`` asks DNS), run in a
    daemon thread so the server starts without waiting; empty until done."""

    def __init__(self, lookup: Callable[[], tuple[str, ...]]) -> None:
        self.names: tuple[str, ...] = ()

        def run() -> None:
            with contextlib.suppress(OSError):
                self.names = tuple(n for n in lookup() if n)

        threading.Thread(target=run, daemon=True).start()


def machine_addresses() -> list[str]:
    """This computer's IPv4 addresses that others may reach it by.

    The address of the default route comes first (found by "connecting" a
    UDP socket, which sends nothing), then those the host name resolves to.
    """
    found: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1: never routed
            found.append(probe.getsockname()[0])
        except OSError:
            pass
    infos = with_timeout(
        lambda: socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET),
        [],
    )
    for info in infos:
        address = str(info[4][0])
        if address not in found:
            found.append(address)
    return [a for a in found if not ipaddress.ip_address(a).is_loopback] or [
        "127.0.0.1"
    ]


def cookie_value(header: str | None, name: str) -> list[str]:
    """The values of the cookies called ``name`` in a Cookie header.

    Split by hand: SimpleCookie gives up on cookies of other local services
    that are not RFC 6265 tokens (spaces, JSON), and the session gets lost.
    """
    values = []
    for pair in (header or "").split(";"):
        key, equals, value = pair.strip().partition("=")
        if equals and key.strip() == name:
            values.append(value.strip().strip('"'))
    return values


class Gate:
    """The token and the sessions of one running server (in memory only)."""

    def __init__(self, token: str) -> None:
        self.token = token
        # Set to SESSION_COOKIE + "_<port>" once the server has its port.
        self.cookie_name = SESSION_COOKIE
        # The part of linked-page addresses that lets their files in: a
        # sandboxed page's own requests carry no SameSite cookie. Derived
        # from the token, so links survive a restart with STOMS_TOKEN.
        self.linked_key = hmac.new(
            token.encode(), b"stoms linked pages", hashlib.sha256
        ).hexdigest()[:32]
        # Insertion-ordered, so the oldest session is dropped first.
        self._sessions: dict[str, None] = {}
        self._lock = threading.Lock()

    def token_matches(self, value: str) -> bool:
        return hmac.compare_digest(value.encode(), self.token.encode())

    def linked_key_matches(self, value: str) -> bool:
        return hmac.compare_digest(value.encode(), self.linked_key.encode())

    def new_session(self) -> str:
        session = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[session] = None
            while len(self._sessions) > MAX_SESSIONS:
                del self._sessions[next(iter(self._sessions))]
        return session

    def has_session(self, cookie: str | None) -> bool:
        """Whether the Cookie header carries one of this server's sessions.

        A dictionary lookup: the session IDs are 256-bit random values, so
        its timing tells a guesser nothing useful.
        """
        values = cookie_value(cookie, self.cookie_name)
        with self._lock:
            return any(value in self._sessions for value in values)

    def admits(self, cookie: str | None, authorization: str | None) -> bool:
        """Whether a request carries a session cookie or the token."""
        if authorization:
            scheme, _, value = authorization.partition(" ")
            if scheme.lower() == "token" and self.token_matches(value.strip()):
                return True
        return self.has_session(cookie)

    def cookie(self, session: str, secure: bool) -> str:
        """The Set-Cookie value; Lax so links from linked pages (an opaque
        origin) still open the viewer, while cross-site POSTs stay without."""
        value = f"{self.cookie_name}={session}; HttpOnly; SameSite=Lax; Path=/"
        return value + "; Secure" if secure else value
