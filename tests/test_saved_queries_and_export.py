import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.io import read

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    DatasetQuery,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    StrictSelectionError,
    StructureQuery,
    StructureSourceSpec,
)
from stoms.atomsledger.exceptions import IntegrityError

METHOD = MethodSpec(
    method_identifier="mace-v1", family="MLIP", name="MACE", version="1"
)
SOURCE = StructureSourceSpec(kind="direct", name="test")


def add_structure(ledger: AtomsLedger, purpose: str) -> str:
    position = tuple(
        (ord(purpose[index]) if index < len(purpose) else 0) / 100
        for index in range(3)
    )
    result = ledger.add_structure(
        Atoms("H", positions=(position,)),
        SOURCE,
        Provenance(created_by="test", purpose=purpose, tags=("split:train",)),
    )
    assert isinstance(result, str)
    return result


def add_evaluation(
    ledger: AtomsLedger,
    structure_id: str,
    energy: float,
    *,
    method: MethodSpec = METHOD,
    extra_properties: dict[str, object] | None = None,
) -> str:
    properties: dict[str, object] = {
        "energy": energy,
        "forces": np.zeros((1, 3)),
        "node_energy": np.array([energy]),
    }
    properties.update(extra_properties or {})
    return ledger.add_evaluation(
        structure_id,
        method=method,
        properties=properties,
        provenance=Provenance(created_by="test", purpose="labels"),
    )


def test_stored_query_labels_are_nonunique_and_dynamic(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "saved.sqlite")
    first = add_structure(ledger, "first")
    add_evaluation(ledger, first, -1.0)
    query_id = ledger.create_stored_query(
        label="train",
        description="Training labels",
        query=DatasetQuery(
            structures=StructureQuery(tags_all=("split:train",)),
            evaluations=EvaluationQuery(method_names=(METHOD.name,)),
            require_evaluation=True,
        ),
        provenance=Provenance(created_by="test", purpose="selection"),
    )

    saved = ledger.list_stored_queries()
    assert [query.id for query in saved] == [query_id]
    assert saved[0].label == "train"
    assert saved[0].criteria.structures.tags_all == ("split:train",)
    assert ledger.select(query_id).structure_ids == (first,)

    second = add_structure(ledger, "second")
    add_evaluation(ledger, second, -2.0)
    assert ledger.select(query_id).structure_ids == (first, second)
    assert saved[0].criteria == ledger.get_stored_query(query_id).query


def test_stored_query_keeps_explicit_membership(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "frozen.sqlite")
    first = add_structure(ledger, "first")
    second = add_structure(ledger, "second")
    add_evaluation(ledger, first, -1.0)
    add_evaluation(ledger, second, -2.0)
    query_id = ledger.create_stored_query(
        label="release",
        query=DatasetQuery(
            structures=StructureQuery(ids=(first,)),
            evaluations=EvaluationQuery(method_names=(METHOD.name,)),
            require_evaluation=True,
        ),
        provenance=Provenance(created_by="test", purpose="release"),
    )

    assert ledger.select(query_id).structure_ids == (first,)


def test_stored_queries_are_preserved_by_sqlite_transfer(
    tmp_path: Path,
) -> None:
    source = AtomsLedger(tmp_path / "source.sqlite")
    structure_id = add_structure(source, "transfer")
    add_evaluation(source, structure_id, -1.0)
    query_id = source.create_stored_query(
        label="transfer-query",
        query=DatasetQuery(
            evaluations=EvaluationQuery(method_names=(METHOD.name,))
        ),
        provenance=Provenance(created_by="test", purpose="transfer"),
    )
    snapshot = tmp_path / "snapshot.sqlite"
    source.export_database(snapshot)

    destination = AtomsLedger(tmp_path / "destination.sqlite")
    report = destination.import_database(snapshot)
    assert report.stored_queries_written == 1
    assert destination.get_stored_query(query_id).label == "transfer-query"


def test_existing_schema_is_upgraded_without_record_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "upgrade.sqlite"
    ledger = AtomsLedger(path)
    structure_id = add_structure(ledger, "old")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE schema_info SET value = '5' WHERE key = 'schema_version'"
        )
    upgraded = AtomsLedger(path)
    assert upgraded.load_atoms(structure_id).get_chemical_formula() == "H"
    upgraded.repository.validate()
    assert tuple(upgraded.list_stored_queries()) == ()


def test_strict_extxyz_labels_traceability_and_node_energy_opt_in(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "export.sqlite")
    structure_id = add_structure(ledger, "export")
    evaluation_id = add_evaluation(ledger, structure_id, -1.0)
    destination = tmp_path / "export.extxyz"

    assert (
        ledger.to_extxyz(
            destination,
            dataset=StructureQuery(ids=(structure_id,)),
            evaluator=METHOD,
        )
        == 1
    )
    image = read(destination)
    assert isinstance(image, Atoms)
    assert image.info["REF_energy"] == -1.0
    assert image.arrays["REF_forces"].shape == (1, 3)
    assert "REF_node_energy" not in image.arrays
    assert image.info["atomsledger_structure_id"] == structure_id
    assert image.info["atomsledger_evaluation_id"] == evaluation_id
    assert image.info["atomsledger_evaluator_label"] == METHOD.name
    assert image.info["atomsledger_units"]["energy"] == "eV"
    header = destination.read_text().splitlines()[1]
    assert "Properties=species:S:1:pos:R:3:REF_forces:R:3" in header
    assert ":forces:R:3" not in header
    assert " energy=" not in header

    overridden = tmp_path / "overridden.extxyz"
    ledger.to_extxyz(
        overridden,
        dataset=StructureQuery(ids=(structure_id,)),
        evaluator=METHOD,
        energy_label="energy_ref",
        forces_label="forces_ref",
        node_energy_label="node_ref",
        include_node_energy=True,
    )
    image = read(overridden)
    assert isinstance(image, Atoms)
    assert image.info["energy_ref"] == -1.0
    assert image.arrays["forces_ref"].shape == (1, 3)
    assert image.arrays["node_ref"].shape == (1,)


def test_extxyz_evaluation_labels_overwrite_structure_labels(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "export.sqlite")
    atoms = Atoms("H")
    atoms.info.update(
        {"REF_energy": 9.0, "energy_ref": 8.0, "source_note": "keep"}
    )
    atoms.new_array("REF_forces", np.full((1, 3), 9.0))
    atoms.new_array("REF_node_energy", np.array([9.0]))
    atoms.new_array("forces_ref", np.full((1, 3), 8.0))
    atoms.new_array("node_ref", np.array([8.0]))
    atoms.new_array("source_per_atom", np.array([7.0]))
    structure_id = ledger.add_structure(
        atoms,
        SOURCE,
        Provenance(created_by="test", purpose="stale labels"),
    )
    assert isinstance(structure_id, str)
    add_evaluation(
        ledger,
        structure_id,
        -1.0,
        extra_properties={"stress": np.arange(6.0)},
    )

    default_destination = tmp_path / "default.extxyz"
    ledger.to_extxyz(
        default_destination,
        dataset=StructureQuery(ids=(structure_id,)),
        evaluator=METHOD,
        include_node_energy=True,
    )
    default_image = read(default_destination)
    assert default_image.info["REF_energy"] == -1.0
    np.testing.assert_array_equal(default_image.arrays["REF_forces"], 0.0)
    np.testing.assert_array_equal(
        default_image.arrays["REF_node_energy"], -1.0
    )
    np.testing.assert_array_equal(
        default_image.info["eval_stress"], np.arange(6.0)
    )
    assert default_image.info["source_note"] == "keep"
    assert "source_per_atom" not in default_image.arrays

    custom_destination = tmp_path / "custom.extxyz"
    ledger.to_extxyz(
        custom_destination,
        dataset=StructureQuery(ids=(structure_id,)),
        evaluator=METHOD,
        energy_label="energy_ref",
        forces_label="forces_ref",
        node_energy_label="node_ref",
        include_node_energy=True,
    )
    custom_image = read(custom_destination)
    assert custom_image.info["energy_ref"] == -1.0
    np.testing.assert_array_equal(custom_image.arrays["forces_ref"], 0.0)
    np.testing.assert_array_equal(custom_image.arrays["node_ref"], -1.0)

    stored = ledger.load_atoms(structure_id)
    assert stored.info["REF_energy"] == 9.0
    assert stored.info["energy_ref"] == 8.0
    np.testing.assert_array_equal(stored.arrays["REF_forces"], 9.0)
    np.testing.assert_array_equal(stored.arrays["REF_node_energy"], 9.0)
    np.testing.assert_array_equal(stored.arrays["forces_ref"], 8.0)
    np.testing.assert_array_equal(stored.arrays["node_ref"], 8.0)


def test_strict_extxyz_reports_missing_and_ambiguous_matches(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "strict-export.sqlite")
    missing = add_structure(ledger, "missing")
    ambiguous = add_structure(ledger, "ambiguous")
    add_evaluation(ledger, ambiguous, -1.0)
    add_evaluation(ledger, ambiguous, -2.0)

    with pytest.raises(StrictSelectionError) as error:
        ledger.to_extxyz(
            tmp_path / "strict.extxyz",
            dataset=StructureQuery(ids=(missing, ambiguous)),
            evaluator=METHOD,
        )
    assert error.value.missing_structure_ids == (missing,)
    assert error.value.ambiguous_structure_ids == (ambiguous,)


def test_aggregation_extxyz_preserves_member_order_and_evaluations(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "aggregation-export.sqlite")
    first = add_structure(ledger, "first")
    second = add_structure(ledger, "second")
    first_evaluation = add_evaluation(ledger, first, -1.0)
    second_evaluation = add_evaluation(ledger, second, -2.0)
    revised_first_evaluation = add_evaluation(ledger, first, -3.0)
    aggregation = ledger.create_aggregation(
        name="training",
        members=(
            AggregationMemberInput(second, second_evaluation),
            AggregationMemberInput(first, revised_first_evaluation),
            AggregationMemberInput(first, first_evaluation),
        ),
    )
    destination = tmp_path / "training.extxyz"

    assert ledger.to_extxyz(destination, aggregation_id=aggregation.id) == 3

    frames = read(destination, index=":")
    assert isinstance(frames, list)
    assert [frame.info["atomsledger_structure_id"] for frame in frames] == [
        second,
        first,
        first,
    ]
    assert [frame.info["atomsledger_evaluation_id"] for frame in frames] == [
        second_evaluation,
        revised_first_evaluation,
        first_evaluation,
    ]
    assert [frame.info["REF_energy"] for frame in frames] == [-2.0, -3.0, -1.0]


def test_aggregation_extxyz_requires_evaluation_before_writing(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "unlabeled-aggregation.sqlite")
    structure_id = add_structure(ledger, "unlabeled")
    aggregation = ledger.create_aggregation(
        name="unlabeled",
        members=(AggregationMemberInput(structure_id),),
    )
    destination = tmp_path / "unlabeled.extxyz"

    with pytest.raises(StrictSelectionError, match="has no evaluation"):
        ledger.to_extxyz(destination, aggregation_id=aggregation.id)
    assert not destination.exists()


@pytest.mark.parametrize(
    "selector",
    ("query", "template", "dataset", "evaluator", "selection"),
)
def test_aggregation_extxyz_rejects_other_selectors(
    tmp_path: Path, selector: str
) -> None:
    ledger = AtomsLedger(tmp_path / "selector-conflict.sqlite")
    structure_id = add_structure(ledger, "selected")
    evaluation_id = add_evaluation(ledger, structure_id, -1.0)
    aggregation = ledger.create_aggregation(
        name="selected",
        members=(AggregationMemberInput(structure_id, evaluation_id),),
    )
    selection = ledger.select(
        StructureQuery(ids=(structure_id,)), evaluator=METHOD
    )
    selectors = {
        "query": DatasetQuery(),
        "template": "stored_query_id",
        "dataset": StructureQuery(ids=(structure_id,)),
        "evaluator": METHOD,
        "selection": selection,
    }

    with pytest.raises(ValueError, match="aggregation_id cannot be combined"):
        ledger.export_extxyz(
            tmp_path / "conflict.extxyz",
            aggregation_id=aggregation.id,
            **{selector: selectors[selector]},
        )


def test_aggregation_extxyz_rejects_mismatched_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = AtomsLedger(tmp_path / "mismatched-aggregation.sqlite")
    structure_id = add_structure(ledger, "selected")
    other_structure_id = add_structure(ledger, "other")
    evaluation_id = add_evaluation(ledger, structure_id, -1.0)
    aggregation = ledger.create_aggregation(
        name="selected",
        members=(AggregationMemberInput(structure_id, evaluation_id),),
    )
    evaluation = ledger.load_evaluation(evaluation_id)
    monkeypatch.setattr(
        ledger.repository,
        "get_evaluation",
        lambda _: replace(evaluation, structure_id=other_structure_id),
    )
    destination = tmp_path / "mismatched.extxyz"

    with pytest.raises(IntegrityError, match="pairs structure"):
        ledger.to_extxyz(destination, aggregation_id=aggregation.id)
    assert not destination.exists()


def test_broad_sqlite_catalog_and_record_paths_are_iterators(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "streaming.sqlite")
    structure_id = add_structure(ledger, "streaming")
    add_evaluation(ledger, structure_id, -1.0)

    structures = ledger.find_structures()
    evaluations = ledger.find_evaluations()
    catalog = ledger.catalog.iter_search()
    assert isinstance(structures, Iterator)
    assert isinstance(evaluations, Iterator)
    assert isinstance(catalog, Iterator)
    assert [record.id for record in structures] == [structure_id]
    assert [entry.id for entry in catalog] == [structure_id]
