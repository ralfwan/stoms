from concurrent.futures import ThreadPoolExecutor

import pytest
from ase import Atoms

pytest.importorskip(
    "psycopg", reason="install the postgres optional dependency"
)

from stoms.atomsledger import (
    AggregationConflictError,
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
from stoms.atomsledger.backends.postgres import PostgresRepository

SOURCE = StructureSourceSpec(kind="direct", name="postgres-test")
METHOD = MethodSpec(
    method_identifier="test-model", family="test", name="model"
)


def make_ledger(postgres_schema: tuple[str, str]) -> AtomsLedger:
    dsn, schema = postgres_schema
    return AtomsLedger(PostgresRepository(dsn, schema=schema))


def add_structure(ledger: AtomsLedger, index: int) -> str:
    return ledger.add_structure(
        Atoms("H", positions=[(float(index), 0, 0)]),
        source_spec=SOURCE,
        provenance=Provenance(created_by="test", purpose="fixture"),
    )


def test_stored_query_visibility_and_reference_protection(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_ledger(postgres_schema)
    add_structure(ledger, 0)
    query_id = ledger.create_stored_query(
        label="same",
        query=DatasetQuery(),
        provenance=Provenance(created_by="test", purpose="query"),
    )
    ledger.create_stored_query(
        label="same",
        query=DatasetQuery(),
        provenance=Provenance(created_by="test", purpose="query"),
    )
    assert len(ledger.list_stored_queries()) == 2
    ledger.hide_stored_query(query_id)
    assert [item.id for item in ledger.list_stored_queries()] != [query_id]

    aggregation = ledger.materialize_stored_query(
        stored_query_id=query_id, name="snapshot"
    )
    with pytest.raises(StoredQueryInUseError) as error:
        ledger.delete_stored_query(query_id)
    assert error.value.aggregation_ids == (aggregation.id,)
    ledger.delete_stored_query(query_id, force=True)
    assert (
        ledger.get_aggregation(aggregation.id).source_stored_query_id is None
    )


def test_aggregation_snapshot_lineage_validation_and_summaries(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_ledger(postgres_schema)
    first, second = add_structure(ledger, 1), add_structure(ledger, 2)
    evaluation = ledger.add_evaluation(
        first,
        method=METHOD,
        properties={"energy": -1.0},
        provenance=Provenance(created_by="test", purpose="label"),
    )
    query_id = ledger.create_stored_query(
        label="candidates",
        query=DatasetQuery(
            evaluations=EvaluationQuery(method_names=(METHOD.name,)),
            require_evaluation=True,
        ),
        provenance=Provenance(created_by="test", purpose="query"),
    )
    predecessor = ledger.create_aggregation(
        name="initial", members=(AggregationMemberInput(first, evaluation),)
    )
    aggregation = ledger.create_aggregation(
        name="selected",
        members=(
            AggregationMemberInput(second),
            AggregationMemberInput(first),
        ),
        metadata={"iteration": 1},
        external_key="workflow:selected",
        supersedes_id=predecessor.id,
    )
    assert [member.structure_id for member in aggregation.members] == [
        second,
        first,
    ]
    assert (
        ledger.list_aggregations(metadata_filter={"iteration": 1})[
            0
        ].member_count
        == 2
    )
    assert (
        ledger.get_aggregation(aggregation.id, include_members=False).members
        == ()
    )

    snapshot = ledger.materialize_stored_query(
        stored_query_id=query_id, name="frozen"
    )
    assert snapshot.source_stored_query_id == query_id
    assert snapshot.source_query_snapshot is not None
    with pytest.raises(AggregationValidationError, match="cannot coexist"):
        ledger.create_aggregation(
            name="mixed",
            members=(
                AggregationMemberInput(first),
                AggregationMemberInput(first, evaluation),
            ),
        )


def test_external_key_is_concurrently_idempotent_and_conflicts(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_ledger(postgres_schema)
    structure_id = add_structure(ledger, 1)
    dsn, schema = postgres_schema

    def create(_: int) -> str:
        return (
            AtomsLedger(PostgresRepository(dsn, schema=schema))
            .create_aggregation(
                name="concurrent",
                members=(AggregationMemberInput(structure_id),),
                external_key="workflow:concurrent",
            )
            .id
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert len(set(executor.map(create, range(16)))) == 1
    assert len(ledger.list_aggregations()) == 1
    with pytest.raises(AggregationConflictError):
        ledger.create_aggregation(
            name="different",
            members=(AggregationMemberInput(structure_id),),
            external_key="workflow:concurrent",
        )
