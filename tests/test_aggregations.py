from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms

from stoms.atomsledger import (
    AggregationConflictError,
    AggregationMemberInput,
    AggregationNotFoundError,
    AggregationValidationError,
    AtomsLedger,
    DatasetQuery,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    RecordNotFoundError,
    StructureSourceSpec,
)

METHOD = MethodSpec(method_identifier="mace", family="MLIP", name="MACE")
SOURCE = StructureSourceSpec(kind="direct", name="test")


def add_structure(ledger: AtomsLedger, index: int) -> str:
    result = ledger.add_structure(
        Atoms("H", positions=[(float(index), 0.0, 0.0)]),
        SOURCE,
        Provenance(created_by="test", purpose="candidate"),
    )
    assert isinstance(result, str)
    return result


def add_evaluation(ledger: AtomsLedger, structure_id: str) -> str:
    return ledger.add_evaluation(
        structure_id,
        method=METHOD,
        properties={"energy": -1.0, "forces": np.zeros((1, 3))},
        provenance=Provenance(created_by="test", purpose="label"),
    )


def test_aggregation_preserves_order_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "aggregations.sqlite"
    ledger = AtomsLedger(path)
    ids = [add_structure(ledger, index) for index in range(3)]

    aggregation = ledger.create_aggregation(
        name="selected",
        members=tuple(
            AggregationMemberInput(item) for item in (ids[2], ids[0], ids[1])
        ),
        metadata={"purpose": "vasp", "iteration": 0},
    )
    assert [member.structure_id for member in aggregation.members] == [
        ids[2],
        ids[0],
        ids[1],
    ]
    assert ledger.get_aggregation_structure_ids(aggregation.id) == [
        ids[2],
        ids[0],
        ids[1],
    ]
    reopened = AtomsLedger(path).get_aggregation(aggregation.id)
    assert reopened == aggregation
    assert (
        ledger.list_aggregations(metadata_filter={"purpose": "vasp"})[
            0
        ].member_count
        == 3
    )


def test_aggregation_validates_members_and_is_not_mutable(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "validation.sqlite")
    first = add_structure(ledger, 0)

    with pytest.raises(AggregationValidationError):
        ledger.create_aggregation(name="empty", members=())
    with pytest.raises(RecordNotFoundError):
        ledger.create_aggregation(
            name="missing", members=(AggregationMemberInput("str_missing"),)
        )
    with pytest.raises(AggregationValidationError):
        ledger.create_aggregation(
            name="duplicate",
            members=(
                AggregationMemberInput(first),
                AggregationMemberInput(first),
            ),
        )
    with pytest.raises(AggregationValidationError):
        ledger.create_aggregation(
            name="malformed",
            members=(AggregationMemberInput(first),),
            metadata={"bad": object()},
        )
    assert ledger.list_aggregations() == []
    assert not hasattr(ledger, "update_aggregation_members")


def test_external_key_is_idempotent_but_conflicts_on_changed_membership(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "idempotency.sqlite")
    first, second = add_structure(ledger, 0), add_structure(ledger, 1)
    original = ledger.create_aggregation(
        name="workflow selection",
        members=(AggregationMemberInput(first),),
        metadata={"iteration": 0},
        external_key="workflow:1:selection",
    )
    retry = ledger.create_aggregation(
        name="workflow selection",
        members=(AggregationMemberInput(first),),
        metadata={"iteration": 0},
        external_key="workflow:1:selection",
    )
    assert retry == original
    with pytest.raises(AggregationConflictError):
        ledger.create_aggregation(
            name="workflow selection",
            members=(
                AggregationMemberInput(first),
                AggregationMemberInput(second),
            ),
            metadata={"iteration": 0},
            external_key="workflow:1:selection",
        )
    assert (
        ledger.get_aggregation_by_external_key("workflow:1:selection")
        == original
    )
    with pytest.raises(AggregationNotFoundError):
        ledger.get_aggregation_by_external_key("missing")


def test_concurrent_external_key_creation_is_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "concurrent.sqlite"
    structure_id = add_structure(AtomsLedger(path), 0)

    def create(_: int) -> str:
        return (
            AtomsLedger(path)
            .create_aggregation(
                name="concurrent",
                members=(AggregationMemberInput(structure_id),),
                external_key="workflow:concurrent",
            )
            .id
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(create, range(16)))
    assert len(set(ids)) == 1
    assert len(AtomsLedger(path).list_aggregations()) == 1


def test_materialized_saved_query_freezes_dynamic_results(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "materialize.sqlite")
    first = add_structure(ledger, 0)
    add_evaluation(ledger, first)
    query_id = ledger.create_stored_query(
        label="candidates",
        query=DatasetQuery(
            evaluations=EvaluationQuery(method_names=(METHOD.name,)),
            require_evaluation=True,
        ),
        provenance=Provenance(created_by="test", purpose="selection"),
    )

    aggregation = ledger.materialize_stored_query(
        stored_query_id=query_id,
        name="iteration-0",
        external_key="workflow:1:iteration:0",
    )
    second = add_structure(ledger, 1)
    add_evaluation(ledger, second)
    assert ledger.select(query_id).structure_ids == (first, second)
    assert ledger.get_aggregation_structure_ids(aggregation.id) == [first]
    assert aggregation.source_stored_query_id == query_id
    assert aggregation.source_query_snapshot is not None


def test_aggregation_lineage_and_sqlite_transfer(tmp_path: Path) -> None:
    source = AtomsLedger(tmp_path / "source.sqlite")
    first, second = add_structure(source, 0), add_structure(source, 1)
    predecessor = source.create_aggregation(
        name="initial",
        members=(AggregationMemberInput(first),),
        external_key="initial",
    )
    successor = source.create_aggregation(
        name="expanded",
        members=(
            AggregationMemberInput(first),
            AggregationMemberInput(second),
        ),
        supersedes_id=predecessor.id,
        external_key="expanded",
    )
    assert successor.supersedes_id == predecessor.id

    snapshot = tmp_path / "snapshot.sqlite"
    report = source.export_database(snapshot)
    assert report.aggregations_written == 2
    destination = AtomsLedger(tmp_path / "destination.sqlite")
    imported = destination.import_database(snapshot)
    assert imported.aggregations_written == 2
    assert destination.get_aggregation(successor.id) == successor
