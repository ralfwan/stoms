from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.io import read

from stoms.atomsledger import (
    AtomsLedger,
    DatasetQuery,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    RecordNotFoundError,
    StructureQuery,
    StructureSourceSpec,
)
from stoms.atomsledger.serialization import record_fingerprint

SOURCE = StructureSourceSpec(kind="direct", name="test")


def make_ledger(path: Path) -> tuple[AtomsLedger, str, str]:
    ledger = AtomsLedger(path)
    structure_id = ledger.add_structure(
        Atoms("H", positions=((0.0, 0.0, 0.0),)),
        SOURCE,
        Provenance(created_by="test", purpose="structure", tags=("keep",)),
    )
    assert isinstance(structure_id, str)
    evaluation_id = ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="mace", family="MLIP", name="MACE"
        ),
        properties={"energy": -1.0, "forces": np.zeros((1, 3))},
        provenance=Provenance(
            created_by="test", purpose="evaluation", tags=("reference",)
        ),
    )
    return ledger, structure_id, evaluation_id


def test_effective_tags_are_append_only_and_persist(tmp_path: Path) -> None:
    ledger, structure_id, evaluation_id = make_ledger(tmp_path / "tags.sqlite")
    structure = ledger.repository.get_structure(structure_id)
    evaluation = ledger.load_evaluation(evaluation_id)
    structure_fingerprint = record_fingerprint(structure)
    evaluation_fingerprint = record_fingerprint(evaluation)

    assert ledger.add_tags(structure_id, ("invalid", "invalid")) == {
        "invalid",
        "keep",
    }
    result = ledger.add_tags_many({evaluation_id: ("obsolete", "obsolete")})
    assert result == {evaluation_id: frozenset(("obsolete", "reference"))}
    assert ledger.load_evaluation(evaluation_id).provenance.tags == (
        "reference",
    )
    assert record_fingerprint(
        ledger.repository.get_structure(structure_id)
    ) == (structure_fingerprint)
    assert record_fingerprint(ledger.load_evaluation(evaluation_id)) == (
        evaluation_fingerprint
    )

    reopened = AtomsLedger(tmp_path / "tags.sqlite")
    assert reopened.get_tags(structure_id) == {"invalid", "keep"}
    assert reopened.get_tags(evaluation_id) == {"obsolete", "reference"}


def test_tag_queries_and_catalog_use_effective_tags(tmp_path: Path) -> None:
    ledger, structure_id, evaluation_id = make_ledger(
        tmp_path / "queries.sqlite"
    )
    ledger.add_tags_many(
        {structure_id: ("invalid",), evaluation_id: ("obsolete",)}
    )

    assert [
        item.id
        for item in ledger.find_structures(
            StructureQuery(tags_all=("invalid",), tags_any=("keep",))
        )
    ] == [structure_id]
    assert (
        list(ledger.find_structures(StructureQuery(tags_none=("invalid",))))
        == []
    )
    assert [
        item.id
        for item in ledger.find_evaluations(
            EvaluationQuery(tags_all=("obsolete",), tags_none=("missing",))
        )
    ] == [evaluation_id]
    entry = ledger.catalog.search(StructureQuery(ids=(structure_id,)))[0]
    assert entry.tags == ("invalid", "keep")
    assert entry.evaluators[0].tags == ("obsolete", "reference")


def test_tag_batch_is_atomic_and_validates_boundaries(tmp_path: Path) -> None:
    ledger, structure_id, evaluation_id = make_ledger(
        tmp_path / "atomic.sqlite"
    )

    with pytest.raises(RecordNotFoundError):
        ledger.add_tags_many(
            {structure_id: ("first",), "str_missing": ("second",)}
        )
    assert ledger.get_tags(structure_id) == {"keep"}

    for invalid in ("", " ", " leading", "trailing ", "  both  "):
        with pytest.raises(ValueError):
            ledger.add_tags(structure_id, (invalid,))
    with pytest.raises(TypeError):
        ledger.add_tags(evaluation_id, ("valid", 1))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        ledger.add_tags(structure_id, ())
    assert ledger.add_tags_many({}) == {}


def test_frozen_saved_query_keeps_membership_but_exposes_tags(
    tmp_path: Path,
) -> None:
    ledger, structure_id, evaluation_id = make_ledger(
        tmp_path / "frozen.sqlite"
    )
    query_id = ledger.create_stored_query(
        label="frozen",
        query=DatasetQuery(
            structures=StructureQuery(ids=(structure_id,)),
            evaluations=EvaluationQuery(method_names=("MACE",)),
            require_evaluation=True,
        ),
        provenance=Provenance(created_by="test", purpose="frozen"),
    )
    ledger.add_tags(structure_id, ("invalid",))
    selection = ledger.select(query_id)
    assert selection.structure_ids == (structure_id,)
    assert selection.evaluation_ids == (evaluation_id,)
    assert selection.records[0].structure.effective_tags == (
        "invalid",
        "keep",
    )


def test_sqlite_export_import_and_extxyz_preserve_tags(tmp_path: Path) -> None:
    source, structure_id, evaluation_id = make_ledger(
        tmp_path / "source.sqlite"
    )
    source.add_tags_many(
        {structure_id: ("invalid",), evaluation_id: ("obsolete",)}
    )
    snapshot = tmp_path / "snapshot.sqlite"
    source.export_database(snapshot)

    destination = AtomsLedger(tmp_path / "destination.sqlite")
    destination.import_database(snapshot)
    assert destination.get_tags(structure_id) == {"invalid", "keep"}
    assert destination.get_tags(evaluation_id) == {"obsolete", "reference"}

    output = tmp_path / "records.extxyz"
    source.to_extxyz(
        output,
        dataset=StructureQuery(ids=(structure_id,)),
        evaluator="MACE",
    )
    image = read(output)
    assert isinstance(image, Atoms)
    assert image.info["atomsledger_structure_tags"] == "invalid,keep"
    assert image.info["atomsledger_evaluation_tags"] == "obsolete,reference"


@pytest.mark.skip(reason="HDF5 support is quarantined until STOMS is stable")
def test_post_ingestion_tags_reject_unsupported_transfer_and_backend(
    tmp_path: Path,
) -> None:
    from stoms.atomsledger import IntegrityError
    from stoms.atomsledger.backends.hdf5 import HDF5Repository

    source, structure_id, _ = make_ledger(tmp_path / "source.sqlite")
    source.add_tags(structure_id, ("invalid",))
    hdf5 = HDF5Repository(tmp_path / "target.h5")

    with pytest.raises(IntegrityError, match="cannot preserve"):
        source.transfer_to(hdf5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="only supported by SQLite"):
        AtomsLedger(hdf5).add_tags(  # type: ignore[arg-type]
            structure_id, ("invalid",)
        )
