import base64
import http.client
import io
import json
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
import pytest
from ase import Atoms
from ase.build import bulk, graphene
from ase.io import read, write
from web_access_helpers import TEST_TOKEN

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)
from stoms.cli import main
from stoms.web import create_server
from stoms.web.server import host_allowed


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    path = tmp_path / "project.ledger"
    ledger = AtomsLedger(path)
    source = StructureSourceSpec(
        kind="generated", name="sampler", parameters={"seed": 7}
    )
    first = cast(
        str,
        ledger.add_structure(
            Atoms("H2"),
            source,
            Provenance(
                created_by="researcher",
                purpose="selection",
                tags=("iteration:000",),
                metadata={"batch": 1},
            ),
        ),
    )
    second = cast(
        str,
        ledger.add_structure(
            Atoms("He"),
            source,
            Provenance(created_by="researcher", purpose="selection"),
        ),
    )
    evaluation = ledger.add_evaluation(
        first,
        method=MethodSpec(
            method_identifier="mace-v1", family="MLIP", name="MACE"
        ),
        properties={
            "energy": -1.0,
            "forces": [[3.0, 4.0, 0.0], [0.0, 0.0, 1.0]],
        },
        provenance=Provenance(created_by="calculator", purpose="label"),
    )
    complete = ledger.create_aggregation(
        name="complete",
        members=(AggregationMemberInput(first, evaluation),),
    )
    aggregation = ledger.create_aggregation(
        name="selected",
        description="For the next calculation",
        members=(
            AggregationMemberInput(first, evaluation),
            AggregationMemberInput(second),
        ),
    )
    server = create_server(ledger, str(path), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            f"http://127.0.0.1:{server.server_address[1]}",
            {
                "aggregation": aggregation.id,
                "complete": complete.id,
                "first": first,
                "second": second,
                "evaluation": evaluation,
            },
        )
    finally:
        server.shutdown()
        server.server_close()


def _get(url: str) -> Any:
    with urlopen(url) as response:
        return json.load(response)


def _status(
    url: str, headers: dict[str, str], data: bytes | None = None
) -> int:
    request = Request(url, data=data, headers=headers)
    try:
        with urlopen(request) as response:
            return response.status
    except HTTPError as error:
        return error.code


def test_requests_naming_another_host_are_refused(served) -> None:
    # DNS rebinding reaches the server under the attacker's domain name.
    base, ids = served
    port = base.rsplit(":", 1)[1]
    url = f"{base}/api/aggregations"
    for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
        assert _status(url, {"Host": host}) == 200
    for host in (f"attacker.example:{port}", "127.0.0.1:1", "localhost"):
        assert _status(url, {"Host": host}) == 421
    assert _status(f"{base}/", {"Host": f"attacker.example:{port}"}) == 421
    export = f"{base}/api/aggregations/{ids['aggregation']}/extxyz"
    json_type = {"Content-Type": "application/json"}
    assert (
        _status(export, {**json_type, "Host": f"evil.test:{port}"}, b"{}")
        == 421
    )


@pytest.mark.parametrize("length", ["-1", "abc", None])
def test_posts_without_a_valid_length_are_refused(served, length) -> None:
    # Reading a body without a valid length would wait for the client.
    base, ids = served
    connection = http.client.HTTPConnection(
        base.removeprefix("http://"), timeout=5
    )
    connection.putrequest(
        "POST", f"/api/aggregations/{ids['aggregation']}/extxyz"
    )
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Authorization", f"token {TEST_TOKEN}")
    if length is not None:
        connection.putheader("Content-Length", length)
    connection.endheaders(b"{}")
    assert connection.getresponse().status == 411
    connection.close()


def test_viewer_responses_forbid_framing_and_foreign_scripts(served) -> None:
    base, _ = served
    for url in (f"{base}/", f"{base}/app.js", f"{base}/api/aggregations"):
        with urlopen(url) as response:
            policy = response.headers["Content-Security-Policy"]
            assert "script-src 'self'" in policy
            assert "connect-src 'self'" in policy
            assert "frame-ancestors 'none'" in policy
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Frame-Options"] == "DENY"


def test_host_check_allows_addresses_and_the_served_name() -> None:
    assert host_allowed("192.168.1.20:8765", 8765, "0.0.0.0")
    assert host_allowed("workstation:8765", 8765, "workstation")
    assert not host_allowed("workstation:8765", 8765, "0.0.0.0")
    assert not host_allowed(None, 8765, "127.0.0.1")
    assert not host_allowed("127.0.0.1:notaport", 8765, "127.0.0.1")


def test_homepage_serves_static_app(served) -> None:
    base, _ = served
    with urlopen(f"{base}/") as response:
        assert response.headers["Content-Type"].startswith("text/html")
        assert b'<script src="app.js">' in response.read()
    for name in ("app.js", "app.css", "viewer.js"):
        with urlopen(f"{base}/{name}") as response:
            assert response.status == 200


def test_api_lists_and_shows_aggregation_members(served) -> None:
    base, ids = served
    assert _get(f"{base}/api/ledger")["ledger"].endswith("project.ledger")

    listed = _get(f"{base}/api/aggregations")
    assert [item["id"] for item in listed] == [
        ids["aggregation"],
        ids["complete"],
    ]
    assert listed[0]["member_count"] == 2

    shown = _get(f"{base}/api/aggregations/{ids['aggregation']}")
    assert shown["name"] == "selected"
    first, second = shown["members"]
    assert first["structure_id"] == ids["first"]
    assert first["formula"] == "H2"
    assert first["source"] == "sampler/generated"
    assert first["iteration"] == "000"
    assert first["method"] == "MACE/mace-v1"
    assert first["properties"] == [
        {"name": "energy", "unit": "eV"},
        {"name": "forces", "unit": "eV/angstrom"},
    ]
    assert second["iteration"] is None
    assert second["evaluation_id"] is None


def test_member_rows_from_catalog_match_loaded_rows(tmp_path: Path) -> None:
    from stoms.web.server import LedgerView

    ledger = AtomsLedger(tmp_path / "rows.ledger")
    source = StructureSourceSpec(kind="generated", name="sampler", tool="cma")
    structure = cast(
        str,
        ledger.add_structure(
            Atoms("H2O", positions=[[0, 0, 0], [0, 0, 1], [0, 1, 0]]),
            source,
            Provenance(created_by="t", purpose="p", tags=("iteration:001",)),
        ),
    )
    evaluation = ledger.add_evaluation(
        structure,
        method=MethodSpec(method_identifier="dft", family="DFT", name="VASP"),
        properties={"energy": -3.0, "forces": [[0, 0, 0]] * 3},
        provenance=Provenance(created_by="t", purpose="label"),
    )
    unevaluated = cast(
        str,
        ledger.add_structure(
            Atoms("He"), source, Provenance(created_by="t", purpose="p")
        ),
    )
    aggregation = ledger.create_aggregation(
        name="rows",
        members=(
            AggregationMemberInput(structure, evaluation),
            AggregationMemberInput(unevaluated),
        ),
    )
    view = LedgerView(ledger, "rows")
    rows = view.aggregation(aggregation.id)["members"]
    # Linked pages are added to either kind of row afterwards.
    assert rows == [
        {**view._loaded_member_row(m), "linked_pages": []}
        for m in aggregation.members
    ]
    assert rows[0]["natoms"] == 3
    assert rows[0]["source"] == "sampler/cma/generated"
    assert rows[0]["method"] == "VASP/dft"
    assert rows[1]["evaluation_id"] is None


def test_atom_count_reads_formulas() -> None:
    from stoms.web.server import _atom_count

    assert _atom_count("O84Sr25Ti32") == 141
    assert _atom_count("CH4") == 5
    assert _atom_count("H") == 1


def test_api_member_detail_includes_provenance_and_method(served) -> None:
    base, ids = served
    detail = _get(f"{base}/api/aggregations/{ids['aggregation']}/members/0")
    assert detail["source_spec"]["parameters"] == {"seed": 7}
    assert detail["structure_provenance"]["metadata"] == {"batch": 1}
    assert detail["structure_provenance"]["effective_tags"] == [
        "iteration:000"
    ]
    assert detail["evaluation"]["id"] == ids["evaluation"]
    assert detail["evaluation"]["method_spec"]["method_identifier"] == (
        "mace-v1"
    )

    without_evaluation = _get(
        f"{base}/api/aggregations/{ids['aggregation']}/members/1"
    )
    assert without_evaluation["evaluation"] is None


def test_api_summary_reports_coverage_and_distributions(served) -> None:
    base, ids = served
    summary = _get(f"{base}/api/aggregations/{ids['aggregation']}/summary")
    assert summary["members"] == 2
    assert summary["evaluated"] == 1
    assert summary["missing"] == 1
    assert summary["iterations"] == [
        {"iteration": "000", "evaluated": 1, "missing": 0},
        {"iteration": None, "evaluated": 0, "missing": 1},
    ]
    energy, forces = summary["properties"]
    assert energy["method"] == "MACE/mace-v1"
    assert energy["kind"] == "scalar"
    assert energy["ordinals"] == [0]
    assert energy["values"] == [-1.0]
    assert energy["natoms"] == [2]
    assert energy["pooled"] is None
    assert forces["kind"] == "per_atom_vector"
    assert forces["values"] == [5.0]
    assert forces["pooled"]["stats"]["n"] == 2
    assert forces["pooled"]["stats"]["min"] == 1.0
    assert sum(forces["pooled"]["histogram"]["counts"]) == 2


def test_api_exports_extxyz_with_requested_labels(served) -> None:
    base, ids = served
    url = (
        f"{base}/api/aggregations/{ids['complete']}/extxyz"
        "?energy_label=DFT_energy&forces_label=DFT_forces"
    )
    with urlopen(url) as response:
        disposition = response.headers["Content-Disposition"]
        body = response.read().decode()
    assert disposition == f'attachment; filename="{ids["complete"]}.extxyz"'
    frames = read(io.StringIO(body), index=":", format="extxyz")
    assert len(frames) == 1
    assert frames[0].info["DFT_energy"] == -1.0
    assert "DFT_forces" in frames[0].arrays


def _post(url: str, payload: Any, content_type: str = "application/json"):
    data = (
        payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    )
    return urlopen(
        Request(url, data=data, headers={"Content-Type": content_type})
    )


def test_api_exports_selected_members_as_zip_of_files(served) -> None:
    base, ids = served
    url = f"{base}/api/aggregations/{ids['complete']}/extxyz"
    with _post(
        url,
        {
            "energy_label": "DFT_energy",
            "archive_name": "complete set",
            "files": [
                {"name": "complete_H2", "ordinals": [0]},
                {"name": "../escape", "ordinals": [0]},
            ],
        },
    ) as response:
        assert response.headers["Content-Type"] == "application/zip"
        assert (
            'filename="complete_set.zip"'
            in (response.headers["Content-Disposition"])
        )
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    assert sorted(archive.namelist()) == [
        "complete_H2.extxyz",
        "escape.extxyz",
    ]
    frames = read(
        io.StringIO(archive.read("complete_H2.extxyz").decode()),
        index=":",
        format="extxyz",
    )
    assert len(frames) == 1
    assert frames[0].info["DFT_energy"] == -1.0


def test_api_exports_single_selected_file_as_extxyz(served) -> None:
    base, ids = served
    url = f"{base}/api/aggregations/{ids['aggregation']}/extxyz"
    with _post(
        url, {"files": [{"name": "H2 only", "ordinals": [0]}]}
    ) as response:
        assert (
            'filename="H2_only.extxyz"'
            in (response.headers["Content-Disposition"])
        )
        frames = read(
            io.StringIO(response.read().decode()), index=":", format="extxyz"
        )
    assert [frame.get_chemical_formula() for frame in frames] == ["H2"]


@pytest.mark.parametrize(
    ("payload", "content_type", "status"),
    [
        ({"files": [{"name": "x", "ordinals": [1]}]}, "application/json", 409),
        ({"files": [{"name": "x", "ordinals": [7]}]}, "application/json", 404),
        ({"files": []}, "application/json", 400),
        (
            {
                "files": [
                    {"name": "x", "ordinals": [0]},
                    {"name": "x", "ordinals": [0]},
                ]
            },
            "application/json",
            400,
        ),
        (b"not json", "application/json", 400),
        ({"files": [{"name": "x", "ordinals": [0]}]}, "text/plain", 415),
    ],
)
def test_api_selected_export_rejects_invalid_requests(
    served, payload, content_type: str, status: int
) -> None:
    base, ids = served
    url = f"{base}/api/aggregations/{ids['aggregation']}/extxyz"
    with pytest.raises(HTTPError) as error:
        _post(url, payload, content_type)
    assert error.value.code == status
    assert json.load(error.value)["error"]


def test_api_extxyz_rejects_members_without_evaluation(served) -> None:
    base, ids = served
    with pytest.raises(HTTPError) as error:
        urlopen(f"{base}/api/aggregations/{ids['aggregation']}/extxyz")
    assert error.value.code == 409
    assert "has no evaluation" in json.load(error.value)["error"]


def test_api_structure_lists_geometry_and_every_evaluation(served) -> None:
    base, ids = served
    structure = _get(f"{base}/api/structures/{ids['first']}")
    assert structure["formula"] == "H2"
    assert structure["symbols"] == ["H", "H"]
    assert len(structure["positions"]) == 2
    assert len(structure["cell"]) == 3
    assert structure["tags"] == ["iteration:000"]
    assert structure["file"] is None  # generated, not read from a file
    (evaluation,) = structure["evaluations"]
    assert evaluation["id"] == ids["evaluation"]
    assert evaluation["method"] == "MACE/mace-v1"
    assert evaluation["family"] == "MLIP"
    assert len(evaluation["spec_hash"]) == 8
    assert evaluation["vectors"] == [{"name": "forces", "unit": "eV/angstrom"}]
    assert evaluation["scalars"] == [
        {"name": "energy", "unit": "eV", "value": -1.0}
    ]
    assert _get(f"{base}/api/structures/{ids['second']}")["evaluations"] == []


def test_api_evaluation_detail_describes_method_provenance_and_properties(
    served,
) -> None:
    base, ids = served
    detail = _get(f"{base}/api/evaluations/{ids['evaluation']}")
    assert detail["id"] == ids["evaluation"]
    assert detail["structure_id"] == ids["first"]
    assert detail["method"] == "MACE/mace-v1"
    assert detail["method_spec"]["family"] == "MLIP"
    assert detail["provenance"]["created_by"] == "calculator"
    assert detail["provenance"]["effective_tags"] == []
    energy, forces = detail["properties"]
    assert energy == {
        "name": "energy",
        "unit": "eV",
        "shape": [],
        "value": -1.0,
    }
    assert forces["name"] == "forces"
    assert forces["unit"] == "eV/angstrom"
    assert forces["shape"] == [2, 3]
    assert forces["stats"]["min"] == 0.0
    assert forces["stats"]["max"] == 4.0
    assert forces["max_norm"] == 5.0
    with pytest.raises(HTTPError) as error:
        urlopen(f"{base}/api/evaluations/eval_missing")
    assert error.value.code == 404


def test_api_evaluation_vector_returns_per_atom_values(served) -> None:
    base, ids = served
    forces = _get(f"{base}/api/evaluations/{ids['evaluation']}/vectors/forces")
    assert forces["unit"] == "eV/angstrom"
    assert forces["values"] == [[3.0, 4.0, 0.0], [0.0, 0.0, 1.0]]
    with pytest.raises(HTTPError) as error:
        urlopen(f"{base}/api/evaluations/{ids['evaluation']}/vectors/energy")
    assert error.value.code == 404


def test_api_structure_lists_per_atom_values_for_colouring(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "atoms.ledger")
    atoms = Atoms("CuO", positions=[[0, 0, 0], [0, 0, 1.8]])
    atoms.set_tags([0, 1])
    atoms.set_initial_magnetic_moments([0.5, -0.5])
    atoms.new_array("spin", np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]))
    atoms.info["layer"] = [1, 2]
    atoms.info["size"] = [1, 2, 3]  # not one value per atom
    atoms.info["stress"] = [1.0, 2.0]  # of the whole structure
    structure = cast(
        str,
        ledger.add_structure(
            atoms,
            StructureSourceSpec(kind="generated", name="test"),
            Provenance(
                created_by="researcher",
                purpose="colours",
                metadata={"site": ["hollow", "top"], "bader": {"q": [1, -1]}},
            ),
        ),
    )
    evaluation = ledger.add_evaluation(
        structure,
        method=MethodSpec(method_identifier="pbe", family="DFT", name="VASP"),
        properties={
            "energy": -1.0,
            "charges": [0.4, -0.4],
            "virial": [0.1, 0.2],  # as long as the atom count, not per atom
            "forces": [[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]],
        },
        units={"charges": "e"},
        provenance=Provenance(created_by="calculator", purpose="label"),
    )
    server = create_server(ledger, "atoms.ledger", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        detail = _get(f"{base}/api/structures/{structure}")
        assert "arrays" not in detail  # loaded on demand, below
        extras = _get(f"{base}/api/structures/{structure}/extras")
        arrays = {(a["source"], a["name"]): a for a in extras["arrays"]}
        assert set(arrays) == {
            ("arrays", "initial_magmoms"),
            ("arrays", "spin"),
            ("arrays", "tags"),
            ("info", "layer"),
            ("metadata", "site"),
            ("metadata", "bader.q"),
        }
        assert extras["info"] == {
            "layer": [1, 2],
            "size": [1, 2, 3],
            "stress": [1.0, 2.0],
        }
        assert extras["metadata"]["site"] == ["hollow", "top"]
        assert detail["mass"] == pytest.approx(63.546 + 15.999, abs=0.01)
        assert arrays["arrays", "tags"]["kind"] == "number"
        assert arrays["arrays", "tags"]["values"] == [0, 1]
        assert arrays["arrays", "spin"]["kind"] == "vector"
        assert arrays["metadata", "site"] == {
            "name": "site",
            "source": "metadata",
            "kind": "text",
            "values": ["hollow", "top"],
        }
        (summary,) = detail["evaluations"]
        assert summary["atom_values"] == [{"name": "charges", "unit": "e"}]
        charges = _get(f"{base}/api/evaluations/{evaluation}/atoms/charges")
        assert charges["unit"] == "e"
        assert charges["values"] == [0.4, -0.4]
        for name in ("energy", "forces", "virial", "missing"):
            with pytest.raises(HTTPError) as error:
                urlopen(f"{base}/api/evaluations/{evaluation}/atoms/{name}")
            assert error.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_api_related_groups_structures_by_tag_prefix(served) -> None:
    base, ids = served
    related = _get(
        f"{base}/api/structures/{ids['first']}/related?prefix=iteration:"
    )
    assert related["tags"] == ["iteration:000"]
    assert [item["id"] for item in related["structures"]] == [ids["first"]]
    assert related["structures"][0]["iteration"] == "000"
    untagged = _get(f"{base}/api/structures/{ids['second']}/related")
    assert untagged == {"prefix": "run:", "tags": [], "structures": []}


def test_api_related_steps_through_aggregation_members(served) -> None:
    base, ids = served
    related = _get(
        f"{base}/api/structures/{ids['second']}/related"
        f"?aggregation={ids['aggregation']}"
    )
    assert related["aggregation"] == {
        "id": ids["aggregation"],
        "name": "selected",
    }
    assert [item["id"] for item in related["structures"]] == [
        ids["first"],
        ids["second"],
    ]
    assert [item["ordinal"] for item in related["structures"]] == [0, 1]
    assert related["structures"][0]["distinct_tags"] == []
    # A structure outside the aggregation still gets the member list.
    outside = _get(
        f"{base}/api/structures/{ids['second']}/related"
        f"?aggregation={ids['complete']}"
    )
    assert [item["id"] for item in outside["structures"]] == [ids["first"]]


@pytest.mark.parametrize(
    "path",
    [
        "/api/aggregations/agg_missing",
        "/api/aggregations/{aggregation}/members/9",
        "/api/aggregations/{aggregation}/members/x",
        "/api/unknown",
        "/api/structures/str_missing",
        "/vendor/three.module.min.js",
        "/../pyproject.toml",
    ],
)
def test_unknown_paths_return_json_404(served, path: str) -> None:
    base, ids = served
    with pytest.raises(HTTPError) as error:
        urlopen(base + path.format(**ids))
    assert error.value.code == 404
    assert "error" in json.load(error.value)


def test_not_found_errors_keep_their_message(served) -> None:
    base, ids = served
    with pytest.raises(HTTPError) as error:
        urlopen(f"{base}/api/aggregations/{ids['aggregation']}/members/9")
    assert error.value.code == 404
    assert "has no member 9" in json.load(error.value)["error"]


def test_serve_rejects_missing_ledger(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.ledger"
    assert main(["--ledger", str(missing), "serve"]) == 1
    assert "not a readable regular file" in capsys.readouterr().err
    assert not missing.exists()


def _poscar_text(atoms: Atoms) -> str:
    buffer = io.StringIO()
    write(buffer, atoms, format="vasp")
    return buffer.getvalue()


def test_added_files_are_viewable_without_changing_the_ledger(
    served, tmp_path: Path
) -> None:
    base, ids = served
    slab = Atoms(
        "Cu2O",
        positions=[[0, 0, 0], [1.8, 0, 0], [0.9, 0.9, 1]],
        cell=[3.6] * 3,
    )
    before = _get(f"{base}/api/aggregations")
    payload = {
        "name": "POSCAR",
        "data": base64.b64encode(_poscar_text(slab).encode()).decode(),
    }
    with _post(f"{base}/api/structures", payload) as response:
        added = json.load(response)
    assert added["name"] == "POSCAR"
    assert added["member_count"] == 1
    with _post(f"{base}/api/structures", payload) as response:
        assert json.load(response)["name"] == "POSCAR (2)"
    listed = _get(f"{base}/api/aggregations")
    assert [a for a in listed if not a.get("added")] == before
    assert {a["name"] for a in listed if a.get("added")} == {
        "POSCAR",
        "POSCAR (2)",
    }
    (structure_id,) = added["structure_ids"]
    structure = _get(f"{base}/api/structures/{structure_id}")
    assert structure["symbols"] == ["Cu", "Cu", "O"]
    related = _get(
        f"{base}/api/structures/{ids['first']}/related"
        f"?aggregation={added['id']}"
    )
    assert [r["id"] for r in related["structures"]] == [structure_id]
    with pytest.raises(HTTPError) as error:
        _post(f"{base}/api/structures", {"name": "x.cif", "data": "bm9wZQ=="})
    assert error.value.code == 400
    with pytest.raises(HTTPError) as error:
        _post(
            f"{base}/api/structures", {"name": "x.cif", "data": "not base64!"}
        )
    assert error.value.code == 400
    assert "base64" in json.load(error.value)["error"]
    # A file ASE cannot read says which files can be opened; a phonopy yaml
    # also how to view it.
    yaml = base64.b64encode(b"phonopy:\n  version: 2.21\n").decode()
    with pytest.raises(HTTPError) as error:
        _post(
            f"{base}/api/structures",
            {"name": "phonopy_params.yaml", "data": yaml},
        )
    assert error.value.code == 400
    message = json.load(error.value)["error"]
    assert "not a structure file ASE knows" in message
    assert "stoms --file phonopy_params.yaml serve" in message
    # Records of the served ledger keep their own errors once files are added.
    with pytest.raises(HTTPError) as error:
        urlopen(f"{base}/api/evaluations/{ids['evaluation']}/atoms/energy")
    assert error.value.code == 404
    assert "not one number per atom" in json.load(error.value)["error"]


def test_api_exports_structures_as_vasp_and_cif(served) -> None:
    base, ids = served
    slab = Atoms("CuO", positions=[[0, 0, 0], [0, 0, 1.8]], cell=[3, 3, 6])
    payload = {
        "name": "slab.vasp",
        "data": base64.b64encode(_poscar_text(slab).encode()).decode(),
    }
    with _post(f"{base}/api/structures", payload) as response:
        added = json.load(response)
    (structure_id,) = added["structure_ids"]
    url = f"{base}/api/structures/{structure_id}/extxyz?format="
    with urlopen(url + "vasp") as response:
        assert response.headers["Content-Disposition"].endswith('.vasp"')
        poscar = read(io.StringIO(response.read().decode()), format="vasp")
    assert poscar.get_chemical_symbols() == ["Cu", "O"]
    with urlopen(url + "cif") as response:
        cif = read(io.StringIO(response.read().decode()), format="cif")
    assert cif.get_chemical_formula() == "CuO"
    with pytest.raises(HTTPError) as error:
        urlopen(f"{base}/api/structures/{ids['first']}/extxyz?format=vasp")
    assert error.value.code == 400  # H2 has no cell
    with pytest.raises(HTTPError) as error:
        urlopen(url + "pdb")
    assert error.value.code == 400
    files = f"{base}/api/aggregations/{added['id']}/extxyz"
    with _post(
        files, {"format": "cif", "files": [{"name": "all", "ordinals": [0]}]}
    ) as response:
        assert 'filename="all.cif"' in response.headers["Content-Disposition"]


def test_api_finds_rings_of_a_structure(served) -> None:
    base, _ = served
    sheet = graphene(size=(2, 2, 1), vacuum=5)
    payload = {
        "name": "graphene.vasp",
        "data": base64.b64encode(_poscar_text(sheet).encode()).decode(),
    }
    with _post(f"{base}/api/structures", payload) as response:
        (structure_id,) = json.load(response)["structure_ids"]
    settings = quote(json.dumps({"cutoffs": {"C-C": 1.6}, "count": "all"}))
    rings = _get(
        f"{base}/api/structures/{structure_id}/rings?settings={settings}"
    )
    assert rings["method"] == "planar"
    assert rings["counts"] == {"6": 4}
    assert rings["signature"] == "6,6,6,6"
    assert len(rings["rings"][0]["points"]) == 6
    windowed = quote(
        json.dumps({"heights": {"C": [4.0, None]}, "cutoffs": {"C-C": 1.6}})
    )
    url = f"{base}/api/structures/{structure_id}/rings?settings={windowed}"
    assert _get(url)["network"] == 8  # graphene sits at z = 5
    assert _get(url) == _get(url)  # answered from the cache
    for bad in (
        {"colour": "red"},
        {"max_size": 99},
        {"method": "faces"},
        {"heights": [1, 2]},
        {"heights": {"C": 5}},
    ):
        with pytest.raises(HTTPError) as error:
            urlopen(
                f"{base}/api/structures/{structure_id}/rings"
                f"?settings={quote(json.dumps(bad))}"
            )
        assert error.value.code == 400


def test_api_ring_height_windows_follow_wrapped_atoms(served) -> None:
    base, _ = served
    sheet = graphene(size=(2, 2, 1), vacuum=5)
    sheet.positions[:, 2] -= 8  # stored at z = -3; wrapped at z = 7
    sheet.pbc = True
    payload = {
        "name": "low.vasp",
        "data": base64.b64encode(_poscar_text(sheet).encode()).decode(),
    }
    with _post(f"{base}/api/structures", payload) as response:
        (structure_id,) = json.load(response)["structure_ids"]
    window = {"heights": {"C": [4.0, None]}, "cutoffs": {"C-C": 1.6}}

    def network(**extra: Any) -> int:
        settings = quote(json.dumps({**window, **extra}))
        url = f"{base}/api/structures/{structure_id}/rings?settings={settings}"
        return _get(url)["network"]

    assert network() == 0
    assert network(wrap=True) == 8
    assert network(wrap=False) == 0
    with pytest.raises(HTTPError) as error:
        urlopen(
            f"{base}/api/structures/{structure_id}/rings"
            f"?settings={quote(json.dumps({'wrap': 'yes'}))}"
        )
    assert error.value.code == 400


def test_api_exports_members_as_one_poscar_each(served) -> None:
    base, _ = served
    frames = [
        Atoms("Cu", cell=[3, 3, 3], pbc=True),
        Atoms(
            "O2", positions=[[0, 0, 0], [0, 0, 1.2]], cell=[5] * 3, pbc=True
        ),
    ]
    buffer = io.StringIO()
    write(buffer, frames, format="extxyz")
    payload = {
        "name": "two.extxyz",
        "data": base64.b64encode(buffer.getvalue().encode()).decode(),
    }
    with _post(f"{base}/api/structures", payload) as response:
        added = json.load(response)
    url = f"{base}/api/aggregations/{added['id']}/extxyz"
    request = {
        "format": "vasp",
        "files": [{"name": "two", "ordinals": [0, 1]}],
    }
    with _post(url, request) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    assert sorted(archive.namelist()) == [
        "two/00000_Cu.vasp",
        "two/00001_O2.vasp",
    ]
    poscar = read(
        io.StringIO(archive.read("two/00001_O2.vasp").decode()), format="vasp"
    )
    assert poscar.get_chemical_symbols() == ["O", "O"]


def test_added_cif_keeps_a_note_of_info_it_cannot_store(served) -> None:
    base, _ = served
    buffer = io.BytesIO()
    write(buffer, bulk("Si"), format="cif")
    payload = {
        "name": "si.cif",
        "data": base64.b64encode(buffer.getvalue()).decode(),
    }
    with _post(f"{base}/api/structures", payload) as response:
        (structure_id,) = json.load(response)["structure_ids"]
    extras = _get(f"{base}/api/structures/{structure_id}/extras")
    assert "spacegroup" not in extras["info"]
    assert extras["metadata"]["dropped_info"] == ["spacegroup"]


def test_added_evaluations_are_served_from_the_added_file(served) -> None:
    base, _ = served
    frame = Atoms(
        "H2", positions=[[0, 0, 0], [0, 0, 0.74]], cell=[5] * 3, pbc=True
    )
    frame.info["REF_energy"] = -1.5
    frame.new_array(
        "REF_forces", np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]])
    )
    buffer = io.StringIO()
    write(buffer, [frame], format="extxyz")
    payload = {
        "name": "labelled.extxyz",
        "data": base64.b64encode(buffer.getvalue().encode()).decode(),
    }
    with _post(f"{base}/api/structures", payload) as response:
        (structure_id,) = json.load(response)["structure_ids"]
    (evaluation,) = _get(f"{base}/api/structures/{structure_id}")[
        "evaluations"
    ]
    assert (
        _get(f"{base}/api/evaluations/{evaluation['id']}")["method"]
        == "REF/REF"
    )
    forces = _get(f"{base}/api/evaluations/{evaluation['id']}/vectors/forces")
    assert forces["values"][0] == [0.0, 0.0, 1.0]


def test_malformed_ring_and_upload_requests_are_rejected(served) -> None:
    base, ids = served
    with pytest.raises(HTTPError) as error:
        urlopen(
            f"{base}/api/structures/{ids['first']}/rings?settings=not-json"
        )
    assert error.value.code == 400
    with pytest.raises(HTTPError) as error:
        _post(f"{base}/api/structures", {"data": "aGk="})
    assert error.value.code == 400
