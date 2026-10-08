import io
import json
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from ase import Atoms
from ase.io import read

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)
from stoms.cli import main
from stoms.web import create_server


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
    (evaluation,) = structure["evaluations"]
    assert evaluation["id"] == ids["evaluation"]
    assert evaluation["method"] == "MACE/mace-v1"
    assert evaluation["family"] == "MLIP"
    assert len(evaluation["spec_hash"]) == 8
    assert evaluation["vectors"] == [{"name": "forces", "unit": "eV/angstrom"}]
    assert _get(f"{base}/api/structures/{ids['second']}")["evaluations"] == []


def test_api_evaluation_vector_returns_per_atom_values(served) -> None:
    base, ids = served
    forces = _get(f"{base}/api/evaluations/{ids['evaluation']}/vectors/forces")
    assert forces["unit"] == "eV/angstrom"
    assert forces["values"] == [[3.0, 4.0, 0.0], [0.0, 0.0, 1.0]]
    with pytest.raises(HTTPError) as error:
        urlopen(f"{base}/api/evaluations/{ids['evaluation']}/vectors/energy")
    assert error.value.code == 404


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
