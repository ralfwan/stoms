import json
import os
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from ase import Atoms
from web_access_helpers import bare_opener

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    Provenance,
    StructureSourceSpec,
)
from stoms.cli import main
from stoms.web import (
    LinkedPageError,
    create_server,
    load_linked_page,
    load_linked_pages,
)
from stoms.web.server import linked_page_report

ENTRY = b"<!doctype html><title>STM images</title>"


def _write_page(directory: Path, ids: list[str], **manifest: Any) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_bytes(ENTRY)
    (directory / "stoms-link.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "name": "stm",
                "title": "STM images",
                "description": "Simulated constant-height STM",
                "structure_ids": ids,
                **manifest,
            }
        )
    )
    return directory


@pytest.fixture
def ledger(tmp_path: Path) -> tuple[AtomsLedger, str, str]:
    ledger = AtomsLedger(tmp_path / "project.ledger")
    source = StructureSourceSpec(kind="generated", name="sampler")
    provenance = Provenance(created_by="researcher", purpose="selection")
    first = cast(str, ledger.add_structure(Atoms("H2"), source, provenance))
    second = cast(str, ledger.add_structure(Atoms("He"), source, provenance))
    return ledger, first, second


@pytest.fixture
def served(
    tmp_path: Path, ledger: tuple[AtomsLedger, str, str]
) -> Iterator[tuple[str, dict[str, Any]]]:
    store, first, second = ledger
    page = _write_page(tmp_path / "viewer", [first, "str_elsewhere"])
    (page / "data").mkdir()
    (page / "data" / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "secret.txt").write_text("outside")
    (page / "escape.txt").symlink_to(tmp_path / "secret.txt")
    (page / ".env").write_text("outside")
    (page / ".git").mkdir()
    (page / ".git" / "config").write_text("outside")
    aggregation = store.create_aggregation(
        name="both",
        members=(
            AggregationMemberInput(first),
            AggregationMemberInput(second),
        ),
    )
    server = create_server(
        store, "project.ledger", port=0, linked_pages=(load_linked_page(page),)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield (
            base,
            {
                "first": first,
                "second": second,
                "aggregation": aggregation.id,
                # Linked pages live under the server's key.
                "key": server.gate.linked_key,
                "linked": f"{base}/linked/{server.gate.linked_key}",
            },
        )
    finally:
        server.shutdown()
        server.server_close()


def _get(url: str) -> Any:
    with urlopen(url) as response:
        return json.load(response)


def test_structure_lists_linked_pages_from_the_manifest(served) -> None:
    base, ids = served
    first = _get(f"{base}/api/structures/{ids['first']}")
    assert first["linked_pages"] == [
        {
            "name": "stm",
            "title": "STM images",
            "description": "Simulated constant-height STM",
            "url": f"linked/{ids['key']}/stm/index.html#{ids['first']}",
        }
    ]
    second = _get(f"{base}/api/structures/{ids['second']}")
    assert second["linked_pages"] == []


def test_aggregation_members_list_their_linked_pages(served) -> None:
    base, ids = served
    aggregation = _get(f"{base}/api/aggregations/{ids['aggregation']}")
    # Each page is described once; members name the pages that list them.
    assert aggregation["linked_pages"] == [
        {
            "name": "stm",
            "title": "STM images",
            "description": "Simulated constant-height STM",
            "url_template": f"linked/{ids['key']}/stm/index.html"
            "#{structure_id}",
        }
    ]
    links = {
        m["structure_id"]: m["linked_pages"] for m in aggregation["members"]
    }
    assert links == {ids["first"]: ["stm"], ids["second"]: []}


def test_linked_page_files_are_served_with_revalidation(served) -> None:
    base, ids = served
    with urlopen(f"{ids['linked']}/stm/index.html") as response:
        assert response.read() == ENTRY
        # The browser takes the charset from the page itself.
        assert response.headers["Content-Type"] == "text/html"
        assert response.headers["Cache-Control"] == "no-cache"
        # Its own origin: no access to the API or the viewer's storage.
        policy = response.headers["Content-Security-Policy"]
        assert policy.startswith("sandbox allow-scripts")
        assert "allow-same-origin" not in policy
        # No dialogs or downloads; new tabs (a link back to the viewer) work.
        assert "allow-modals" not in policy
        assert "allow-downloads" not in policy
        assert "allow-popups-to-escape-sandbox" in policy
        etag = response.headers["ETag"]
    with urlopen(f"{ids['linked']}/stm/data/image.png") as response:
        assert response.headers["Content-Type"] == "image/png"
        assert response.read() == b"\x89PNG"
    # A proxy that compresses the body may hand back a weak ETag.
    for tag in (etag, f"W/{etag}", f'"other", {etag}'):
        request = Request(
            f"{ids['linked']}/stm/index.html", headers={"If-None-Match": tag}
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 304


def test_file_that_cannot_be_opened_is_not_found(served, monkeypatch) -> None:
    # Opening fails as it would without read permission. chmod cannot test
    # this: root, as in CI containers, reads the file anyway.
    opened = Path.open

    def refuse(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == "index.html":
            raise PermissionError(self)
        return opened(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refuse)
    base, ids = served
    with pytest.raises(HTTPError) as error:
        urlopen(f"{ids['linked']}/stm/index.html")
    assert error.value.code == 404


def test_directory_address_serves_the_entry(served) -> None:
    base, ids = served
    with urlopen(f"{ids['linked']}/stm/") as response:
        assert response.read() == ENTRY


def test_replacing_a_file_with_an_older_copy_is_not_fresh(
    served, tmp_path: Path
) -> None:
    base, ids = served
    entry = tmp_path / "viewer" / "index.html"
    with urlopen(f"{ids['linked']}/stm/index.html") as response:
        etag = response.headers["ETag"]
    # Same size, older modification time, as left by cp -p or rsync -t.
    stat = entry.stat()
    entry.write_bytes(ENTRY.upper())
    os.utime(entry, ns=(stat.st_atime_ns, stat.st_mtime_ns - 10**9))
    request = Request(
        f"{ids['linked']}/stm/index.html", headers={"If-None-Match": etag}
    )
    with urlopen(request) as response:
        assert response.read() == ENTRY.upper()


@pytest.mark.parametrize(
    "path",
    [
        "/linked/stm/../../secret.txt",
        "/linked/stm/%2e%2e/secret.txt",
        "/linked/stm/escape.txt",
        "/linked/stm/.env",
        "/linked/stm/.git/config",
        "/linked/stm/data/../.env",
        "/linked/stm/data",
        "/linked/stm",
        "/linked/other/index.html",
        "/linked/stm/a%00b",
    ],
)
def test_linked_pages_stay_inside_their_directory(served, path: str) -> None:
    base, ids = served
    path = path.replace("/linked/", f"/linked/{ids['key']}/", 1)
    # http.client sends the path as given; urllib would not normalize it
    # either, but this makes the raw request explicit.
    connection = HTTPConnection(base.removeprefix("http://"))
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    assert response.status == 404
    assert b"outside" not in body


@pytest.mark.parametrize(
    "path",
    [
        "/linked/stm/index.html",  # the address without a key
        "/linked/0123456789abcdef0123456789abcdef/stm/index.html",
    ],
)
def test_linked_pages_need_the_key(served, path: str) -> None:
    # A sandboxed page's own requests carry no session cookie, so the key in
    # the address lets its files in; without it, nothing is served.
    base, _ = served
    connection = HTTPConnection(base.removeprefix("http://"))
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    connection.close()
    assert response.status == 404
    assert ENTRY not in body


def test_linked_page_files_need_no_session(served) -> None:
    base, ids = served
    with bare_opener().open(f"{ids['linked']}/stm/index.html") as response:
        assert response.read() == ENTRY


@pytest.mark.parametrize(
    "path, location", [("/linked/", "../"), ("/linked/{key}/", "../../")]
)
def test_linked_folders_lead_back_to_the_viewer(
    served, path, location
) -> None:
    # Pages written for /linked/<name>/ link back with ../../#/structures/…,
    # which now lands on /linked/ (or, one level deeper, /linked/<key>/).
    base, ids = served
    with pytest.raises(HTTPError) as error:
        bare_opener().open(base + path.format(key=ids["key"]))
    assert error.value.code == 303
    assert error.value.headers["Location"] == location


def test_fragment_keeps_its_own_separators(tmp_path: Path) -> None:
    page = load_linked_page(
        _write_page(
            tmp_path / "viewer",
            ["str_a"],
            fragment="id={structure_id}&view=stm",
        )
    )
    assert page.url("str_a") == "linked/stm/index.html#id=str_a&view=stm"
    assert page.url("a&b") == "linked/stm/index.html#id=a%26b&view=stm"


def test_report_checks_manifests_larger_than_one_query(
    tmp_path: Path, ledger: tuple[AtomsLedger, str, str]
) -> None:
    store, first, second = ledger
    ids = [first, second] + [f"str_{index:05d}" for index in range(40_000)]
    page = load_linked_page(_write_page(tmp_path / "viewer", ids))
    (line,) = linked_page_report(store, (page,))
    assert "40002 structures, warning: 40000 not in this ledger" in line


def test_report_warns_about_manifest_ids_missing_from_the_ledger(
    tmp_path: Path, ledger: tuple[AtomsLedger, str, str]
) -> None:
    store, first, _ = ledger
    page = load_linked_page(
        _write_page(tmp_path / "viewer", [first, "str_elsewhere"])
    )
    (line,) = linked_page_report(store, (page,))
    assert "'stm'" in line
    assert "2 structures" in line
    assert "warning: 1 not in this ledger" in line
    complete = load_linked_page(_write_page(tmp_path / "all", [first]))
    (line,) = linked_page_report(store, (complete,))
    assert "warning" not in line


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ({"schema": 2}, "unsupported schema"),
        ({"name": "../up"}, "may use only"),
        ({"name": ""}, "'name' must be"),
        ({"title": 3}, "'title' must be"),
        ({"fragment": "fixed"}, "must contain {structure_id}"),
        ({"structure_ids": "str_a"}, "must be a list of strings"),
        ({"entry": "missing.html"}, "is not a file"),
        ({"entry": "../outside.html"}, "is not a file"),
    ],
)
def test_invalid_manifests_are_rejected(
    tmp_path: Path, manifest: dict[str, Any], message: str
) -> None:
    (tmp_path / "outside.html").write_text("x")
    page = _write_page(tmp_path / "viewer", ["str_a"], **manifest)
    with pytest.raises(LinkedPageError, match=message):
        load_linked_page(page)


def test_missing_manifest_and_duplicate_names_are_rejected(
    tmp_path: Path,
) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(LinkedPageError, match="has no stoms-link.json"):
        load_linked_page(tmp_path / "empty")
    with pytest.raises(LinkedPageError, match="not a directory"):
        load_linked_page(tmp_path / "missing")
    first = _write_page(tmp_path / "a", ["str_a"])
    second = _write_page(tmp_path / "b", ["str_b"])
    with pytest.raises(LinkedPageError, match="two linked pages are named"):
        load_linked_pages([first, second])


def test_cli_reports_unusable_linked_page(tmp_path: Path, capsys) -> None:
    path = tmp_path / "project.ledger"
    AtomsLedger(path)
    (tmp_path / "empty").mkdir()
    argv = [
        "--ledger",
        str(path),
        "serve",
        "--link-page",
        str(tmp_path / "empty"),
    ]
    assert main(argv) == 1
    assert "has no stoms-link.json" in capsys.readouterr().err


def test_cli_rejects_linked_pages_with_extxyz_file(tmp_path: Path) -> None:
    frames = tmp_path / "frames.extxyz"
    frames.write_text("")
    with pytest.raises(SystemExit):
        main(["--file", str(frames), "serve", "--link-page", str(tmp_path)])
