from pathlib import Path
from typing import cast

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


def test_top_level_help_describes_report_options(capsys) -> None:
    try:
        main(["--help"])
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("--help should exit successfully")

    help_text = capsys.readouterr().out
    assert "aggregations report > report.html" in help_text
    assert (
        "--full-collapse  Collapse every nested detail block in the report"
        in help_text
    )
    assert "aggregations to-extxyz agg_... training.extxyz" in help_text
    assert "--include-node-energy      Include per-atom energies" in help_text


def test_aggregation_cli_lists_and_shows_grouped_audit_data(
    tmp_path: Path, capsys
) -> None:
    path = tmp_path / "project.ledger"
    ledger = AtomsLedger(path)
    source = StructureSourceSpec(
        kind="generated", name="sampler", parameters={"seed": 7}
    )
    provenance = Provenance(
        created_by="researcher",
        purpose="selection",
        tags=("project:test", "iteration:000"),
        notes="initial batch",
        metadata={"batch": 1},
    )
    first = cast(str, ledger.add_structure(Atoms("H2"), source, provenance))
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
            method_identifier="mace-v1",
            family="MLIP",
            name="MACE",
            parameters={"cutoff": 5},
        ),
        properties={"energy": -1.0},
        provenance=Provenance(created_by="calculator", purpose="label"),
    )
    second_evaluation = ledger.add_evaluation(
        second,
        method=MethodSpec(
            method_identifier="mace-v1",
            family="MLIP",
            name="MACE",
        ),
        properties={"energy": -2.0},
        provenance=Provenance(created_by="calculator", purpose="label"),
    )
    aggregation = ledger.create_aggregation(
        name="selected",
        description="For the next calculation",
        metadata={"iteration": 0},
        members=(
            AggregationMemberInput(first, evaluation),
            AggregationMemberInput(second, second_evaluation),
        ),
        external_key="workflow:0:selected",
    )

    assert main(["--ledger", str(path), "aggregations", "list"]) == 0
    listed = capsys.readouterr().out
    assert f"ID: {aggregation.id}" in listed
    assert "Name: selected" in listed
    assert "Members: 2" in listed
    assert "Description: For the next calculation" in listed

    assert (
        main(["--ledger", str(path), "aggregations", "show", aggregation.id])
        == 0
    )
    shown = capsys.readouterr().out
    assert shown == (
        f"Aggregation: selected ({aggregation.id})\n"
        "Members: 2\n"
        "Description: For the next calculation\n"
        "Members:\n"
        f"  0: structure={first} formula=H2 atoms=2 source=sampler/generated "
        f"iteration=iteration:000 method=MACE/mace-v1 evaluation={evaluation} "
        "properties=energy [eV]\n"
        f"  1: structure={second} formula=He atoms=1 source=sampler/generated "
        f"iteration=- method=MACE/mace-v1 evaluation={second_evaluation} "
        "properties=energy [eV]\n"
    )

    assert (
        main(
            [
                "--ledger",
                str(path),
                "aggregations",
                "show",
                aggregation.id,
                "--details",
                "all",
            ]
        )
        == 0
    )
    detailed = capsys.readouterr().out
    assert '"name": "sampler"' in detailed
    assert '"method_identifier": "mace-v1"' in detailed
    assert '"created_by": "researcher"' in detailed
    assert "Structure sources:" in detailed
    assert "Methods:" in detailed
    assert "Structure provenance:" in detailed
    assert "Evaluation provenance:" in detailed

    assert (
        main(
            [
                "--ledger",
                str(path),
                "aggregations",
                "show",
                aggregation.id,
                "--details",
                "source",
                "--structure",
                second,
            ]
        )
        == 0
    )
    selected_detail = capsys.readouterr().out
    assert '"name": "sampler"' in selected_detail
    assert '"batch": 1' not in selected_detail

    assert (
        main(
            [
                "--ledger",
                str(path),
                "aggregations",
                "show",
                aggregation.id,
                "--format",
                "html",
            ]
        )
        == 0
    )
    page = capsys.readouterr().out
    assert page.startswith("<!doctype html>")
    assert "<details><summary>0:" in page
    assert "<details><summary>1:" in page
    assert (
        "sampler/generated | iteration:000 | MACE/mace-v1 | energy [eV]"
        in page
    )
    assert "sampler/generated | - | MACE/mace-v1 | energy [eV]" in page
    assert "<details open" not in page
    assert page.count("<details>") == page.count("</details>")
    assert "name:</span> <code>&quot;sampler&quot;</code>" in page
    assert "method_identifier:</span> <code>&quot;mace-v1&quot;</code>" in page
    assert "Structure provenance" in page
    assert "Evaluation provenance" in page

    assert (
        main(
            [
                "--ledger",
                str(path),
                "aggregations",
                "show",
                aggregation.id,
                "--format",
                "html",
                "--full-collapse",
            ]
        )
        == 0
    )
    fully_collapsed = capsys.readouterr().out
    assert "<details open" not in fully_collapsed

    assert main(["--ledger", str(path), "aggregations", "report"]) == 0
    report = capsys.readouterr().out
    assert report.startswith("<!doctype html>")
    assert "<h2>Index</h2>" in report
    assert f'href="#{aggregation.id}"' in report
    assert f'id="{aggregation.id}"' in report
    assert "Back to index" in report
    assert (
        "sampler/generated | iteration:000 | MACE/mace-v1 | energy [eV]"
        in report
    )
    assert "sampler/generated | - | MACE/mace-v1 | energy [eV]" in report

    destination = tmp_path / "training.extxyz"
    assert (
        main(
            [
                "--ledger",
                str(path),
                "aggregations",
                "to-extxyz",
                aggregation.id,
                str(destination),
                "--energy-label",
                "energy_ref",
                "--include-node-energy",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == f"Wrote 2 frames to {destination}\n"
    frames = read(destination, index=":")
    assert isinstance(frames, list)
    assert [frame.info["energy_ref"] for frame in frames] == [-1.0, -2.0]


def test_aggregation_cli_empty_list_and_errors(tmp_path: Path, capsys) -> None:
    path = tmp_path / "empty.ledger"
    AtomsLedger(path)
    assert main(["--ledger", str(path), "aggregations", "list"]) == 0
    assert capsys.readouterr().out == "No aggregations.\n"

    assert (
        main(["--ledger", str(path), "aggregations", "show", "agg_missing"])
        == 1
    )
    error = capsys.readouterr()
    assert error.out == ""
    assert error.err.startswith("error:")

    assert (
        main(
            [
                "--ledger",
                str(tmp_path / "missing.ledger"),
                "aggregations",
                "list",
            ]
        )
        == 1
    )
    assert "readable regular file" in capsys.readouterr().err


def test_aggregation_cli_rejects_directory(tmp_path: Path, capsys) -> None:
    directory = tmp_path / "ledger-directory"
    directory.mkdir()
    assert main(["--ledger", str(directory), "aggregations", "list"]) == 1
    assert "readable regular file" in capsys.readouterr().err
