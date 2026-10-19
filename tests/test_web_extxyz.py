import json
import threading
from pathlib import Path
from typing import Any, cast
from urllib.request import urlopen

import numpy as np
import pytest
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import write

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)
from stoms.cli import main
from stoms.web import ExtxyzLoadError, create_server, load_extxyz


def _frame(symbols: str = "H2", z: float = 0.74) -> Atoms:
    return Atoms(
        symbols, positions=[[0, 0, 0], [0, 0, z]], cell=[5, 5, 5], pbc=True
    )


def _labelled(energy: float, label: str = "REF", **info: Any) -> Atoms:
    atoms = _frame()
    atoms.info[f"{label}_energy"] = energy
    atoms.new_array(
        f"{label}_forces", np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]])
    )
    atoms.info.update(info)
    return atoms


def _load(tmp_path: Path, frames: list[Atoms]) -> tuple[AtomsLedger, Any]:
    path = tmp_path / "frames.extxyz"
    write(path, frames, format="extxyz")
    ledger = AtomsLedger(tmp_path / "view.ledger")
    return ledger, load_extxyz(ledger, path)


def test_frames_keep_file_order_and_repeats(tmp_path: Path) -> None:
    unlabelled = _frame("He2", 1.0)
    ledger, aggregation = _load(
        tmp_path,
        [
            _labelled(-1.0, temperature=300),
            unlabelled,
            _labelled(-1.0, temperature=300),
        ],
    )

    assert aggregation.name == "frames.extxyz"
    members = aggregation.members
    assert [m.ordinal for m in members] == [0, 1, 2]
    # Identical frames stay separate records.
    assert len({m.structure_id for m in members}) == 3
    assert [m.evaluation_id is not None for m in members] == [
        True,
        False,
        True,
    ]

    structure = ledger.repository.get_structure(members[0].structure_id)
    assert structure.atoms.info == {"temperature": 300}
    assert set(structure.atoms.arrays) == {"numbers", "positions"}
    assert structure.provenance.metadata["frame"] == 0
    assert (
        ledger.repository.get_structure(
            members[1].structure_id
        ).atoms.get_chemical_formula()
        == "He2"
    )

    evaluation = ledger.load_evaluation(cast(str, members[0].evaluation_id))
    assert evaluation.method.name == "REF"
    assert evaluation.method.method_identifier == "REF"
    assert set(evaluation.properties) == {"energy", "forces"}
    assert evaluation.properties["energy"] == -1.0
    assert evaluation.units == {"energy": "eV", "forces": "eV/angstrom"}


def test_calculator_results_become_the_evaluation(tmp_path: Path) -> None:
    atoms = _frame()
    atoms.calc = SinglePointCalculator(
        atoms, energy=-2.5, forces=np.ones((2, 3))
    )
    ledger, aggregation = _load(tmp_path, [atoms])

    evaluation = ledger.load_evaluation(
        cast(str, aggregation.members[0].evaluation_id)
    )
    assert evaluation.method.name == "extxyz"
    assert evaluation.properties["energy"] == -2.5
    np.testing.assert_allclose(
        evaluation.properties["forces"], np.ones((2, 3))
    )


def test_several_evaluations_in_one_frame_are_rejected(tmp_path: Path) -> None:
    atoms = _labelled(-1.0)
    atoms.info["MACE_energy"] = -1.1
    with pytest.raises(
        ExtxyzLoadError,
        match="frame 0 has several evaluations \\(MACE, REF\\)",
    ):
        _load(tmp_path, [atoms])


def test_stoms_export_keeps_method_units_and_tags(tmp_path: Path) -> None:
    source_ledger = AtomsLedger(tmp_path / "source.ledger")
    structure_id = cast(
        str,
        source_ledger.add_structure(
            _frame(),
            StructureSourceSpec(kind="generated", name="test"),
            Provenance(
                created_by="t",
                purpose="sampling",
                tags=("role:winner", "run:run_001"),
            ),
        ),
    )
    evaluation_id = source_ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="vasp/r2scan",
            family="dft",
            name="r2scan",
            code="vasp",
        ),
        properties={
            "energy": -3.0,
            "forces": [[0.0, 0.0, 0.5], [0.0, 0.0, -0.5]],
        },
        units={"energy": "eV", "forces": "eV/angstrom"},
        provenance=Provenance(
            created_by="t", purpose="label", tags=("stage:vasp",)
        ),
    )
    exported = source_ledger.create_aggregation(
        name="export",
        members=(AggregationMemberInput(structure_id, evaluation_id),),
    )
    path = tmp_path / "export.extxyz"
    source_ledger.to_extxyz(path, aggregation_id=exported.id)

    ledger = AtomsLedger(tmp_path / "view.ledger")
    member = load_extxyz(ledger, path).members[0]
    structure = ledger.repository.get_structure(member.structure_id)
    assert structure.provenance.tags == ("role:winner", "run:run_001")
    assert structure.provenance.purpose == "sampling"
    assert structure.provenance.metadata["structure_id"] == structure_id
    assert not any(
        key.startswith("atomsledger_") for key in structure.atoms.info
    )

    evaluation = ledger.load_evaluation(cast(str, member.evaluation_id))
    assert evaluation.method.method_identifier == "vasp/r2scan"
    assert (
        evaluation.method.family,
        evaluation.method.name,
        evaluation.method.code,
    ) == ("dft", "r2scan", "vasp")
    assert evaluation.units == {"energy": "eV", "forces": "eV/angstrom"}
    assert evaluation.properties["energy"] == -3.0
    assert evaluation.provenance.tags == ("stage:vasp",)


def test_loaded_file_is_served(tmp_path: Path) -> None:
    path = tmp_path / "frames.extxyz"
    write(path, [_labelled(-1.0), _frame()], format="extxyz")
    ledger = AtomsLedger(tmp_path / "view.ledger")
    aggregation = load_extxyz(ledger, path)
    server = create_server(ledger, str(path), port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def get(route: str) -> Any:
            with urlopen(f"{base}/api/{route}") as response:
                return json.load(response)

        assert get("ledger")["ledger"] == str(path)
        assert [item["name"] for item in get("aggregations")] == [
            "frames.extxyz"
        ]
        first = aggregation.members[0]
        structure = get(f"structures/{first.structure_id}")
        assert [e["method"] for e in structure["evaluations"]] == ["REF/REF"]
        forces = get(f"evaluations/{first.evaluation_id}/vectors/forces")
        assert forces["values"][0] == [0.0, 0.0, 1.0]
    finally:
        server.shutdown()
        server.server_close()


def test_cli_serve_file_checks_arguments(tmp_path: Path, capsys) -> None:
    path = tmp_path / "frames.extxyz"
    write(path, [_frame()], format="extxyz")
    ledger_path = tmp_path / "project.ledger"
    AtomsLedger(ledger_path)

    with pytest.raises(SystemExit):
        main(["--ledger", str(ledger_path), "--file", str(path), "serve"])
    assert "not allowed with argument" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        main(["--file", str(path), "aggregations", "list"])
    assert "--file works only with serve" in capsys.readouterr().err

    assert main(["--file", str(tmp_path / "missing.extxyz"), "serve"]) == 1
    assert "not a readable regular file" in capsys.readouterr().err

    assert main(["--file", str(ledger_path), "serve"]) == 1
    assert (
        f"use: stoms --ledger {ledger_path} serve" in capsys.readouterr().err
    )

    broken = tmp_path / "broken.extxyz"
    broken.write_text("not an extxyz file\n")
    assert main(["--file", str(broken), "serve"]) == 1
    assert "cannot read" in capsys.readouterr().err


def test_cli_other_commands_still_require_ledger(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["aggregations", "list"])
    assert "required: --ledger" in capsys.readouterr().err


def _served(
    tmp_path: Path, frames: list[Atoms], text: str | None = None
) -> tuple[Path, Any, Any]:
    from stoms.web.extxyz import extxyz_source
    from stoms.web.server import LedgerView

    path = tmp_path / "frames.extxyz"
    if text is None:
        write(path, frames, format="extxyz")
    else:
        path.write_text(text)
    ledger = AtomsLedger(tmp_path / "view.ledger")
    aggregation = load_extxyz(ledger, path)
    return (
        path,
        aggregation,
        LedgerView(ledger, str(path), extxyz_source(path, aggregation)),
    )


def test_file_exports_copy_frames_verbatim(tmp_path: Path) -> None:
    path, aggregation, view = _served(
        tmp_path,
        [
            _labelled(-1.0, temperature=300),
            _frame("He2", 1.0),
            _labelled(-2.0),
        ],
    )
    blocks = path.read_bytes().splitlines(keepends=True)
    frame = [b"".join(blocks[i * 4 : i * 4 + 4]) for i in range(3)]

    assert view.overview()["file"] is True
    assert view.extxyz(aggregation.id, {}).body == path.read_bytes()
    picked = view.extxyz_files(
        aggregation.id, {"files": [{"name": "pick", "ordinals": [2, 0, 2]}]}
    )
    assert picked.filename == "pick.extxyz"
    assert picked.body == frame[0] + frame[2]
    # Frames without an evaluation export verbatim too.
    single = view.structure_extxyz(aggregation.members[1].structure_id, None)
    assert single.filename == "frames_frame1.extxyz"
    assert single.body == frame[1]


def test_frame_spans_skip_blank_lines_and_reject_other_layouts(
    tmp_path: Path,
) -> None:
    from stoms.web.extxyz import _frame_spans

    text = "1\nfirst\nH 0 0 0\n\n1\nsecond\nH 0 0 1\n"
    path = tmp_path / "blank.extxyz"
    path.write_text(text)
    spans = _frame_spans(path)
    assert spans is not None
    assert [path.read_bytes()[a:b] for a, b in spans] == [
        b"1\nfirst\nH 0 0 0\n",
        b"1\nsecond\nH 0 0 1\n",
    ]

    path.write_text("2\ntruncated\nH 0 0 0\n")
    assert _frame_spans(path) is None


def test_ledger_selection_exports_structures_without_evaluation(
    tmp_path: Path,
) -> None:
    from ase.io import read

    from stoms.atomsledger import StrictSelectionError
    from stoms.web.server import LedgerView

    _, aggregation, _ = _served(
        tmp_path, [_labelled(-1.0), _frame("He2", 1.0)]
    )
    view = LedgerView(AtomsLedger(tmp_path / "view.ledger"), "ledger")
    files = {"files": [{"name": "both", "ordinals": [0, 1]}]}
    with pytest.raises(StrictSelectionError):
        view.extxyz_files(aggregation.id, files)

    body = view.extxyz_files(
        aggregation.id, {**files, "include_unevaluated": True}
    ).body
    (tmp_path / "both.extxyz").write_bytes(body)
    frames = read(tmp_path / "both.extxyz", index=":", format="extxyz")
    assert [frame.get_chemical_formula() for frame in frames] == ["H2", "He2"]
    assert frames[0].info["REF_energy"] == -1.0
    assert "REF_energy" not in frames[1].info
    assert "atomsledger_exported_properties" not in frames[1].info
    assert frames[1].pbc.all()

    structure_id = aggregation.members[0].structure_id
    with_evaluation = view.structure_extxyz(
        structure_id, aggregation.members[0].evaluation_id
    )
    assert b"REF_energy=-1.0" in with_evaluation.body
    assert b"REF_energy" not in view.structure_extxyz(structure_id, None).body
