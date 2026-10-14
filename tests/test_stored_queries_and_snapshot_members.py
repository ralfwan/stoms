from pathlib import Path

import pytest
from ase import Atoms

from stoms.atomsledger import (
    AggregationMemberInput,
    AggregationValidationError,
    AtomsLedger,
    DatasetQuery,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    StoredQueryInUseError,
    StructureSourceSpec,
)

SOURCE = StructureSourceSpec(kind="direct", name="test")


def structure(ledger: AtomsLedger, index: int) -> str:
    result = ledger.add_structure(
        Atoms("H", positions=[(float(index), 0, 0)]),
        SOURCE,
        Provenance(created_by="test", purpose="fixture"),
    )
    assert isinstance(result, str)
    return result


def test_stored_query_labels_are_nonunique_and_hidden_queries_are_not_listed(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "queries.sqlite")
    provenance = Provenance(created_by="test", purpose="query")
    first = ledger.create_stored_query(
        label="same", query=DatasetQuery(), provenance=provenance
    )
    ledger.create_stored_query(
        label="same",
        query=DatasetQuery(),
        provenance=provenance,
    )
    assert len(ledger.list_stored_queries()) == 2
    assert ledger.get_stored_query(first).label == "same"


def test_aggregation_members_are_structure_evaluation_pairs(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "members.sqlite")
    first, second = structure(ledger, 1), structure(ledger, 2)
    aggregation = ledger.create_aggregation(
        name="snapshot",
        members=(
            AggregationMemberInput(first),
            AggregationMemberInput(second),
        ),
    )
    assert [member.evaluation_id for member in aggregation.members] == [
        None,
        None,
    ]


def test_aggregation_allows_multiple_evaluations_but_not_null_mixed_members(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "evaluation-members.sqlite")
    structure_id = structure(ledger, 1)
    method = MethodSpec(
        method_identifier="test-model", family="test", name="model"
    )
    evaluations = [
        ledger.add_evaluation(
            structure_id,
            method=method,
            properties={"energy": float(index)},
            provenance=Provenance(created_by="test", purpose="evaluation"),
        )
        for index in range(2)
    ]
    aggregation = ledger.create_aggregation(
        name="evaluations",
        members=tuple(
            AggregationMemberInput(structure_id, evaluation_id)
            for evaluation_id in evaluations
        ),
    )
    assert [
        member.evaluation_id for member in aggregation.members
    ] == evaluations
    with pytest.raises(AggregationValidationError):
        ledger.create_aggregation(
            name="mixed",
            members=(
                AggregationMemberInput(structure_id),
                AggregationMemberInput(structure_id, evaluations[0]),
            ),
        )


def test_stored_query_can_be_hidden_explicitly(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "hidden.sqlite")
    query_id = ledger.create_stored_query(
        label="hidden",
        query=DatasetQuery(evaluations=EvaluationQuery()),
        provenance=Provenance(created_by="test", purpose="query"),
    )
    ledger.hide_stored_query(query_id)
    assert ledger.list_stored_queries() == ()
    assert ledger.get_stored_query(query_id).hidden_at is not None


def test_force_deleting_stored_query_nulls_source_without_deleting_aggregation(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "delete.sqlite")
    structure(ledger, 1)
    query = ledger.create_stored_query(
        label="source",
        query=DatasetQuery(),
        provenance=Provenance(created_by="test", purpose="query"),
    )
    aggregation = ledger.materialize_stored_query(
        stored_query_id=query, name="a"
    )
    with pytest.raises(StoredQueryInUseError) as error:
        ledger.delete_stored_query(query)
    assert error.value.aggregation_ids == (aggregation.id,)
    ledger.delete_stored_query(query, force=True)
    assert (
        ledger.get_aggregation(aggregation.id).source_stored_query_id is None
    )
