"""Who may use a served viewer: token link, sessions, TLS, --allow, uploads."""

import base64
import http.client
import ipaddress
import json
import shutil
import socket
import ssl
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from ase import Atoms
from web_access_helpers import TEST_TOKEN, bare_opener

from stoms.atomsledger import AtomsLedger, Provenance, StructureSourceSpec
from stoms.cli import main
from stoms.web import AccessError, AccessOptions, create_server
from stoms.web.access import (
    MIN_TOKEN_LENGTH,
    address_allowed,
    certificate_names,
    parse_allow,
    resolve_token,
)
from stoms.web.server import ViewerServer, host_allowed

XYZ = b"1\n\nH 0 0 0\n"


@pytest.fixture
def ledger(tmp_path: Path) -> AtomsLedger:
    ledger = AtomsLedger(tmp_path / "access.ledger")
    ledger.add_structure(
        Atoms("H2"),
        StructureSourceSpec(kind="generated", name="t"),
        Provenance(created_by="t", purpose="access"),
    )
    return ledger


def _start(server: ViewerServer) -> str:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def _stop(server: ViewerServer) -> None:
    server.shutdown()
    server.server_close()


@pytest.fixture
def served(ledger: AtomsLedger) -> Iterator[str]:
    server = create_server(ledger, "access.ledger", port=0)
    base = _start(server)
    yield base
    _stop(server)


def _open(url: str, **kwargs: Any) -> Any:
    """Open without the token; HTTP errors come back as responses."""
    try:
        return bare_opener().open(Request(url, **kwargs))
    except HTTPError as error:
        return error


def _upload(url: str, opener: Any = None) -> Any:
    body = json.dumps(
        {"name": "h.xyz", "data": base64.b64encode(XYZ).decode()}
    ).encode()
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"token {TEST_TOKEN}",
        },
    )
    try:
        return (opener or bare_opener()).open(request)
    except HTTPError as error:
        return error


# ------------------------------------------------------------------ the gate


@pytest.mark.parametrize("path", ["/", "/index.html", "/app.js"])
def test_pages_without_a_session_say_how_to_get_in(served, path) -> None:
    response = _open(served + path)
    assert response.status == 401
    assert response.headers["Content-Type"].startswith("text/html")
    assert b"Open the link that was printed" in response.read()


def test_api_without_a_session_answers_401_in_json(served) -> None:
    response = _open(f"{served}/api/aggregations")
    assert response.status == 401
    assert "link printed" in json.load(response)["error"]


def test_symmetry_endpoint_follows_the_same_access_rules(
    served, ledger
) -> None:
    [structure] = ledger.find_structures()
    url = f"{served}/api/structures/{structure.id}/symmetry?tolerance=0.01"
    # No session: refused in JSON, as every API path.
    response = _open(url)
    assert response.status == 401
    assert "link printed" in json.load(response)["error"]
    # A script with the token gets the answer (with spglib: H2 has no 3D
    # cell; without: the install hint).
    request = Request(url, headers={"Authorization": f"token {TEST_TOKEN}"})
    with bare_opener().open(request) as answer:
        assert answer.status == 200
        data = json.load(answer)
    assert data.get("applicable") is False or data["available"] is False


def test_posts_need_a_session_too(served) -> None:
    response = _open(
        f"{served}/api/structures?token={TEST_TOKEN}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    # The token logs in by GET links only.
    assert response.status == 401


def test_token_link_logs_in_and_drops_the_token(served) -> None:
    response = _open(f"{served}/?view=1&token={TEST_TOKEN}")
    assert response.status == 303
    # The fragment is not repeated: the browser keeps the one it opened.
    assert response.headers["Location"] == "/?view=1"
    cookie = response.headers["Set-Cookie"]
    name_value, *attributes = [part.strip() for part in cookie.split(";")]
    port = served.rsplit(":", 1)[1]
    assert name_value.startswith(f"stoms_session_{port}=")
    assert TEST_TOKEN not in name_value
    assert set(attributes) == {"HttpOnly", "SameSite=Lax", "Path=/"}
    session = {"Cookie": name_value}
    assert _open(f"{served}/api/aggregations", headers=session).status == 200
    assert _open(f"{served}/app.js", headers=session).status == 200
    # Another session ID is not one.
    forged = {"Cookie": f"stoms_session_{port}=" + "A" * 43}
    assert _open(f"{served}/api/aggregations", headers=forged).status == 401


def test_wrong_token_gets_no_session(served) -> None:
    response = _open(f"{served}/?token=wrong")
    assert response.status == 401
    assert "Set-Cookie" not in response.headers


def test_scripts_may_send_the_token_as_a_header(served) -> None:
    good = {"Authorization": f"token {TEST_TOKEN}"}
    bad = {"Authorization": "token wrong"}
    assert _open(f"{served}/api/aggregations", headers=good).status == 200
    assert _open(f"{served}/api/aggregations", headers=bad).status == 401
    bearer = {"Authorization": f"Bearer {TEST_TOKEN}"}
    assert _open(f"{served}/api/aggregations", headers=bearer).status == 401


@pytest.mark.parametrize("path", ["/", f"/?token={TEST_TOKEN}", "/api/ledger"])
def test_no_response_passes_the_address_on(served, path) -> None:
    assert _open(served + path).headers["Referrer-Policy"] == "no-referrer"
    with urlopen(f"{served}/api/ledger") as response:
        assert response.headers["Referrer-Policy"] == "no-referrer"


def test_server_reports_urls_with_its_token(ledger) -> None:
    server = create_server(
        ledger, "x", port=0, access=AccessOptions(token="t" * 40)
    )
    try:
        port = server.server_address[1]
        assert server.token == "t" * 40
        assert server.urls("#/x") == [
            f"http://127.0.0.1:{port}/?token={'t' * 40}#/x"
        ]
        assert server.browser_url() == server.urls()[0]
        assert server.warnings() == []
    finally:
        server.server_close()


# ----------------------------------------------------------- stable tokens


def test_token_comes_from_the_environment_or_a_file(tmp_path: Path) -> None:
    token = "s" * MIN_TOKEN_LENGTH
    assert resolve_token({"STOMS_TOKEN": token}) == token
    file = tmp_path / "token"
    file.write_text(f"{token}\n")
    assert resolve_token({"STOMS_TOKEN_FILE": str(file)}) == token
    made = resolve_token({})
    assert len(made) >= 43 and made != resolve_token({})


@pytest.mark.parametrize(
    "environ, message",
    [
        ({"STOMS_TOKEN": "short"}, "at least 32 characters"),
        ({"STOMS_TOKEN": "x" * 31 + " y"}, "without spaces"),
        ({"STOMS_TOKEN": "x" * 40, "STOMS_TOKEN_FILE": "f"}, "not both"),
        ({"STOMS_TOKEN_FILE": "/no/such/token"}, "cannot read"),
    ],
)
def test_unusable_tokens_are_refused(environ, message) -> None:
    with pytest.raises(AccessError, match=message):
        resolve_token(environ)


def test_same_token_keeps_linked_page_addresses(ledger) -> None:
    first = create_server(ledger, "x", port=0)
    second = create_server(ledger, "x", port=0)
    other = create_server(
        ledger, "x", port=0, access=AccessOptions(token="o" * 40)
    )
    try:
        assert first.token == second.token == TEST_TOKEN
        assert first.gate.linked_key == second.gate.linked_key
        assert other.gate.linked_key != first.gate.linked_key
        assert TEST_TOKEN not in first.gate.linked_key
    finally:
        for server in (first, second, other):
            server.server_close()


def test_cli_refuses_a_weak_token(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "a.ledger"
    AtomsLedger(path)
    monkeypatch.setenv("STOMS_TOKEN", "secret")
    assert main(["--ledger", str(path), "serve", "--port", "0"]) == 1
    err = capsys.readouterr().err
    assert "at least 32 characters" in err
    assert "secrets.token_urlsafe" in err


# --------------------------------------------------------------- --allow


def test_allow_parses_ranges_and_addresses() -> None:
    assert parse_allow("10.0.0.0/8, 192.168.1.7") == (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("192.168.1.7/32"),
    )
    for text in ("", "10.0.0.0/33", "nonsense"):
        with pytest.raises(AccessError):
            parse_allow(text)
    allow = parse_allow("10.0.0.0/8")
    assert address_allowed("10.1.2.3", allow)
    assert address_allowed("::ffff:10.1.2.3", allow)
    assert not address_allowed("192.168.1.1", allow)
    assert address_allowed("192.168.1.1", ())


def test_addresses_outside_allow_get_no_answer(ledger) -> None:
    refused = create_server(
        ledger,
        "x",
        port=0,
        access=AccessOptions(allow=parse_allow("10.0.0.0/8")),
    )
    allowed = create_server(
        ledger,
        "x",
        port=0,
        access=AccessOptions(allow=parse_allow("10.0.0.0/8,127.0.0.0/8")),
    )
    base_refused, base_allowed = _start(refused), _start(allowed)
    try:
        with pytest.raises(
            (ConnectionError, http.client.HTTPException, OSError)
        ):
            urlopen(f"{base_refused}/api/ledger", timeout=5)
        with urlopen(f"{base_allowed}/api/ledger", timeout=5) as response:
            assert response.status == 200
    finally:
        _stop(refused)
        _stop(allowed)


def test_cli_refuses_bad_ranges(tmp_path, capsys) -> None:
    path = tmp_path / "a.ledger"
    AtomsLedger(path)
    assert (
        main(["--ledger", str(path), "serve", "--allow", "10.0.0.0/33"]) == 1
    )
    assert "--allow" in capsys.readouterr().err


# --------------------------------------------- shared binds and uploads


def test_uploads_work_on_loopback(served) -> None:
    with urlopen(f"{served}/api/ledger") as response:
        assert json.load(response)["can_add"] is True
    assert _upload(f"{served}/api/structures").status == 200


def test_shared_servers_refuse_uploads_unless_allowed(ledger) -> None:
    shared = create_server(ledger, "x", host="0.0.0.0", port=0)
    allowed = create_server(
        ledger, "x", host="0.0.0.0", port=0, access=AccessOptions(uploads=True)
    )
    base_shared, base_allowed = _start(shared), _start(allowed)
    try:
        with urlopen(f"{base_shared}/api/ledger") as response:
            assert json.load(response)["can_add"] is False
        refused = _upload(f"{base_shared}/api/structures")
        assert refused.status == 403
        assert "--allow-uploads" in json.load(refused)["error"]
        assert _upload(f"{base_allowed}/api/structures").status == 200
    finally:
        _stop(shared)
        _stop(allowed)


def test_wildcard_bind_prints_usable_addresses_and_warns(ledger) -> None:
    server = create_server(ledger, "x", host="0.0.0.0", port=0)
    try:
        port = server.server_address[1]
        urls = server.urls()
        assert urls and not any("0.0.0.0" in url for url in urls)
        assert all(
            url.endswith(f":{port}/?token={TEST_TOKEN}") for url in urls
        )
        # On this computer the browser opens the loopback address.
        assert server.browser_url("#/a") == (
            f"http://127.0.0.1:{port}/?token={TEST_TOKEN}#/a"
        )
        reach, plain = server.warnings()
        assert "anyone who can reach this computer" in reach
        assert "--allow" in reach
        assert "unencrypted" in plain and "--certfile" in plain
    finally:
        server.server_close()
    limited = create_server(
        ledger,
        "x",
        host="0.0.0.0",
        port=0,
        access=AccessOptions(allow=parse_allow("10.0.0.0/8")),
    )
    try:
        assert "--allow" not in limited.warnings()[0]
    finally:
        limited.server_close()


def test_host_check_accepts_the_names_given() -> None:
    assert host_allowed(
        "viewer.example.org:8765", 8765, "0.0.0.0", ("viewer.example.org",)
    )
    assert not host_allowed(
        "evil.test:8765", 8765, "0.0.0.0", ("viewer.example.org",)
    )


# ------------------------------------------------------------------- TLS


def _authorized(url: str) -> Request:
    # urlopen with an SSL context builds its own opener, without the token.
    return Request(url, headers={"Authorization": f"token {TEST_TOKEN}"})


def _make_certificate(
    folder: Path, alt_names: str = "DNS:localhost,IP:127.0.0.1"
) -> tuple[Path, Path]:
    """A throwaway self-signed certificate for ``alt_names``."""
    if shutil.which("openssl") is None:
        pytest.skip("openssl is not installed")
    cert, key = folder / "cert.pem", folder / "key.pem"
    result = subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            f"subjectAltName={alt_names}",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip(f"openssl cannot make a certificate: {result.stderr!r}")
    return cert, key


@pytest.fixture(scope="module")
def certificate(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A throwaway self-signed certificate for localhost and 127.0.0.1."""
    return _make_certificate(tmp_path_factory.mktemp("tls"))


@pytest.fixture
def tls_served(
    ledger, certificate
) -> Iterator[tuple[ViewerServer, str, ssl.SSLContext]]:
    cert, key = certificate
    server = create_server(
        ledger, "x", port=0, access=AccessOptions(certfile=cert, keyfile=key)
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = ssl.create_default_context(cafile=str(cert))
    yield server, f"https://localhost:{server.server_address[1]}", client
    _stop(server)


def test_certificate_names_come_from_its_alt_names(certificate) -> None:
    assert certificate_names(certificate[0]) == ["localhost", "127.0.0.1"]


def test_tls_serves_https_with_a_secure_cookie(tls_served) -> None:
    server, base, client = tls_served
    assert server.urls()[0].startswith("https://127.0.0.1:")
    with urlopen(
        _authorized(f"{base}/api/ledger"), context=client
    ) as response:
        assert response.status == 200
    connection = http.client.HTTPSConnection(
        base.removeprefix("https://"), context=client, timeout=5
    )
    connection.request("GET", f"/?token={TEST_TOKEN}")
    response = connection.getresponse()
    assert response.status == 303
    assert response.getheader("Set-Cookie").endswith("; Secure")
    connection.close()


def test_silent_or_plain_clients_do_not_block_others(tls_served) -> None:
    server, base, client = tls_served
    port = server.server_address[1]
    # One client connects and says nothing; another speaks plain HTTP.
    silent = socket.create_connection(("127.0.0.1", port))
    plain = socket.create_connection(("127.0.0.1", port))
    plain.sendall(b"GET / HTTP/1.0\r\n\r\n")
    try:
        start = time.monotonic()
        with urlopen(
            _authorized(f"{base}/api/ledger"), context=client, timeout=5
        ) as response:
            assert response.status == 200
        assert time.monotonic() - start < 3
    finally:
        silent.close()
        plain.close()


def test_tls_bind_warns_only_about_reach(ledger, certificate) -> None:
    cert, key = certificate
    server = create_server(
        ledger,
        "x",
        host="0.0.0.0",
        port=0,
        access=AccessOptions(certfile=cert, keyfile=key),
    )
    try:
        # The certificate's names, not this computer's addresses.
        assert server.urls()[0].startswith("https://localhost:")
        [warning] = server.warnings()
        assert "unencrypted" not in warning
    finally:
        server.server_close()


def test_unusable_certificates_are_refused(ledger, tmp_path, capsys) -> None:
    bad = tmp_path / "bad.pem"
    bad.write_text("not a certificate")
    with pytest.raises(AccessError, match="cannot use the certificate"):
        create_server(ledger, "x", port=0, access=AccessOptions(certfile=bad))
    path = tmp_path / "a.ledger"
    AtomsLedger(path)
    assert main(["--ledger", str(path), "serve", "--keyfile", str(bad)]) == 1
    assert "--keyfile needs --certfile" in capsys.readouterr().err
    assert (
        main(
            [
                "--ledger",
                str(path),
                "serve",
                "--certfile",
                str(tmp_path / "none.pem"),
            ]
        )
        == 1
    )
    assert "not found" in capsys.readouterr().err


# ------------------------------------------------- review follow-ups (gate)


def _login(base: str) -> str:
    """Log in with the token link; the ``name=value`` of the session cookie."""
    response = _open(f"{base}/?token={TEST_TOKEN}")
    assert response.status == 303
    return response.headers["Set-Cookie"].split(";", 1)[0]


def test_two_viewers_on_one_computer_keep_their_own_sessions(ledger) -> None:
    first = create_server(ledger, "a", port=0)
    second = create_server(ledger, "b", port=0)
    base_first, base_second = _start(first), _start(second)
    try:
        cookie_first, cookie_second = _login(base_first), _login(base_second)
        assert cookie_first.split("=")[0] != cookie_second.split("=")[0]
        # A browser sends both cookies to both ports (cookies ignore ports).
        both = {"Cookie": f"{cookie_first}; {cookie_second}"}
        for base in (base_first, base_second):
            assert _open(f"{base}/api/ledger", headers=both).status == 200
        alone = {"Cookie": cookie_first}
        assert _open(f"{base_second}/api/ledger", headers=alone).status == 401
    finally:
        _stop(first)
        _stop(second)


@pytest.mark.parametrize(
    "others",
    [
        'prefs={"theme": "dark", "size": 2}',
        "bad cookie=1",
        'x="unterminated',
        "_xsrf=2|ab|cd|1",
    ],
)
def test_other_local_cookies_do_not_hide_the_session(served, others) -> None:
    session = _login(served)
    for header in (f"{others}; {session}", f"{session}; {others}"):
        response = _open(f"{served}/api/ledger", headers={"Cookie": header})
        assert response.status == 200


def test_python_callers_cannot_set_a_short_token(ledger) -> None:
    with pytest.raises(AccessError, match="at least"):
        create_server(
            ledger,
            "x",
            host="0.0.0.0",
            port=0,
            access=AccessOptions(token="abc"),
        )


def test_logged_in_browser_survives_a_stale_token_link(served) -> None:
    session = {"Cookie": _login(served)}
    response = _open(f"{served}/?view=1&token=stale-token", headers=session)
    assert response.status == 303
    assert response.headers["Location"] == "/?view=1"
    # It keeps its session rather than getting a new one.
    assert "Set-Cookie" not in response.headers
    again = _open(f"{served}/?token={TEST_TOKEN}", headers=session)
    assert again.status == 303 and "Set-Cookie" not in again.headers


@pytest.mark.parametrize("path", ["//evil.example/", "/\\evil.example/"])
def test_login_redirect_stays_on_this_server(served, path) -> None:
    host, port = served.removeprefix("http://").split(":")
    connection = http.client.HTTPConnection(host, int(port), timeout=5)
    connection.request("GET", f"{path}?token={TEST_TOKEN}")
    response = connection.getresponse()
    assert response.status == 303
    location = response.getheader("Location")
    assert location.startswith("/") and location[1] not in "/\\"
    connection.close()


def test_sessions_are_capped_oldest_first(monkeypatch) -> None:
    from stoms.web import access

    monkeypatch.setattr(access, "MAX_SESSIONS", 3)
    gate = access.Gate(TEST_TOKEN)
    sessions = [gate.new_session() for _ in range(5)]
    name = gate.cookie_name
    kept = [s for s in sessions if gate.has_session(f"{name}={s}")]
    assert kept == sessions[2:]


# --------------------------------------------- review follow-ups (startup)


def test_slow_dns_does_not_hold_up_the_start(ledger, monkeypatch) -> None:
    from stoms.web import access

    release = threading.Event()

    def slow_fqdn(*args: Any) -> str:
        release.wait(10)
        return "viewer.example.org"

    real_getaddrinfo = socket.getaddrinfo

    def slow_getaddrinfo(name: Any, *args: Any, **kwargs: Any) -> Any:
        if name == socket.gethostname():
            release.wait(10)
        return real_getaddrinfo(name, *args, **kwargs)

    monkeypatch.setattr(socket, "getfqdn", slow_fqdn)
    monkeypatch.setattr(socket, "getaddrinfo", slow_getaddrinfo)
    monkeypatch.setattr(access, "LOOKUP_TIMEOUT", 0.2)
    try:
        start = time.monotonic()
        server = create_server(ledger, "x", host="0.0.0.0", port=0)
        assert server.urls()
        assert time.monotonic() - start < 2
    finally:
        release.set()
    base = _start(server)
    try:
        # The name arrives later and is then accepted in Host headers.
        port = server.server_address[1]
        named = {
            "Host": f"viewer.example.org:{port}",
            "Authorization": f"token {TEST_TOKEN}",
        }
        deadline = time.monotonic() + 5
        while True:
            status = _open(f"{base}/api/ledger", headers=named).status
            if status == 200 or time.monotonic() > deadline:
                break
            time.sleep(0.05)
        assert status == 200
    finally:
        _stop(server)


def test_a_loaded_tls_context_is_not_loaded_again(
    ledger, certificate, monkeypatch
) -> None:
    from stoms.web import server as server_module
    from stoms.web.access import tls_context

    cert, key = certificate
    context = tls_context(cert, key)

    def refuse(*args: Any) -> None:
        raise AssertionError("the certificate was loaded again")

    monkeypatch.setattr(server_module, "tls_context", refuse)
    server = create_server(
        ledger,
        "x",
        port=0,
        access=AccessOptions(certfile=cert, keyfile=key, tls=context),
    )
    try:
        assert server.tls is context
    finally:
        server.server_close()


def test_cli_loads_the_certificate_once(certificate, monkeypatch) -> None:
    from stoms.cli import _access_options, _parser
    from stoms.web import access

    cert, key = certificate
    calls = []
    real = access.tls_context

    def counted(*args: Any) -> ssl.SSLContext:
        calls.append(args)
        return real(*args)

    monkeypatch.setattr(access, "tls_context", counted)
    args = _parser().parse_args(
        ["serve", "--certfile", str(cert), "--keyfile", str(key)]
    )
    options = _access_options(args)
    assert len(calls) == 1 and options.tls is not None


def test_open_with_tls_and_a_wildcard_bind_uses_a_name_that_works(
    ledger, certificate, tmp_path
) -> None:
    cert, key = certificate
    local = create_server(
        ledger,
        "x",
        host="0.0.0.0",
        port=0,
        access=AccessOptions(certfile=cert, keyfile=key),
    )
    try:
        assert local.browser_url().startswith("https://localhost:")
    finally:
        local.server_close()
    # A certificate only for a name that does not resolve here.
    cert, key = _make_certificate(tmp_path, "DNS:viewer.invalid")
    remote = create_server(
        ledger,
        "x",
        host="0.0.0.0",
        port=0,
        access=AccessOptions(certfile=cert, keyfile=key),
    )
    try:
        assert remote.urls()[0].startswith("https://viewer.invalid:")
        assert remote.browser_url().startswith("https://127.0.0.1:")
    finally:
        remote.server_close()


# ------------------------------------------- slow clients and many sockets


def _closed_within(connection: socket.socket, seconds: float) -> bool:
    """Whether the server closes ``connection`` within ``seconds``."""
    connection.settimeout(seconds)
    try:
        while connection.recv(1024):
            pass
    except TimeoutError:
        return False
    except OSError:
        return True  # reset by the server
    return True


@pytest.fixture
def quick_timeouts(monkeypatch) -> None:
    from stoms.web import server as server_module

    monkeypatch.setattr(server_module, "HEADER_TIMEOUT", 0.5)
    monkeypatch.setattr(server_module, "IO_TIMEOUT", 0.5)


def _port(base: str) -> int:
    return int(base.rsplit(":", 1)[1])


def test_silent_client_is_closed_after_the_header_deadline(
    ledger, quick_timeouts
) -> None:
    server = create_server(ledger, "x", port=0)
    base = _start(server)
    try:
        silent = socket.create_connection(("127.0.0.1", _port(base)))
        assert _closed_within(silent, 5)
        silent.close()
    finally:
        _stop(server)


def test_trickling_headers_do_not_hold_a_thread(
    ledger, quick_timeouts
) -> None:
    server = create_server(ledger, "x", port=0)
    base = _start(server)
    try:
        slow = socket.create_connection(("127.0.0.1", _port(base)))
        start = time.monotonic()
        closed = False
        # One byte every 0.2 s, never finishing the headers: each read is
        # quicker than IO_TIMEOUT, so only the deadline in all ends it.
        for byte in b"GET / HTTP/1.0\r\nX-Slow: " + b"a" * 200:
            try:
                slow.sendall(bytes([byte]))
            except OSError:
                closed = True
                break
            time.sleep(0.2)
            if time.monotonic() - start > 5:
                break
        assert closed or _closed_within(slow, 1)
        assert time.monotonic() - start < 5
        slow.close()
    finally:
        _stop(server)


def test_a_slow_upload_body_is_not_cut_off(ledger, quick_timeouts) -> None:
    server = create_server(ledger, "x", port=0)
    base = _start(server)
    try:
        body = json.dumps(
            {"name": "h.xyz", "data": base64.b64encode(XYZ).decode()}
        ).encode()
        connection = socket.create_connection(("127.0.0.1", _port(base)))
        connection.sendall(
            (
                "POST /api/structures HTTP/1.0\r\n"
                f"Host: 127.0.0.1:{_port(base)}\r\n"
                f"Authorization: token {TEST_TOKEN}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode()
        )
        # The body takes longer than the header deadline, each piece
        # quicker than IO_TIMEOUT.
        for start in range(0, len(body), 8):
            connection.sendall(body[start : start + 8])
            time.sleep(0.1)
        connection.settimeout(10)
        answer = b""
        while chunk := connection.recv(65536):
            answer += chunk
        assert answer.startswith(b"HTTP/1.0 200")
        connection.close()
    finally:
        _stop(server)


def _wait_for(condition: Any, seconds: float = 5) -> bool:
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.02)
    return True


@pytest.mark.parametrize(
    "limit", ["max_connections", "max_connections_per_client"]
)
def test_connections_over_the_limit_are_closed_unread(ledger, limit) -> None:
    server = create_server(ledger, "x", port=0)
    setattr(server, limit, 2)
    base = _start(server)
    held: list[socket.socket] = []
    try:
        for _ in range(2):
            held.append(socket.create_connection(("127.0.0.1", _port(base))))
        assert _wait_for(lambda: server.open_connections() == 2)
        extra = socket.create_connection(("127.0.0.1", _port(base)))
        assert _closed_within(extra, 2)
        extra.close()
        # Once the held connections end, others get in again.
        for connection in held:
            connection.close()
        assert _wait_for(lambda: server.open_connections() == 0)
        with urlopen(f"{base}/api/ledger") as response:
            assert response.status == 200
    finally:
        for connection in held:
            connection.close()
        _stop(server)
