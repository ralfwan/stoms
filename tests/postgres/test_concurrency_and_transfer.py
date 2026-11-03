from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from ase import Atoms

pytest.importorskip(
    "psycopg", reason="install the postgres optional dependency"
)

from stoms.atomsledger import (
    AtomsLedger,
    DatasetQuery,
    DuplicateRecordError,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    StructureContentConflictError,
    StructureQuery,
    StructureSourceSpec,
    TrajectoryFrame,
    transfer_repository,
    verify_repository_subset,
)
from stoms.atomsledger.backends.postgres import PostgresRepository

SOURCE = StructureSourceSpec(kind="direct", name="postgres-concurrency")
METHOD = MethodSpec(
    method_identifier="test-model", family="test", name="model"
)


def make_postgres_ledger(postgres_schema: tuple[str, str]) -> AtomsLedger:
    dsn, schema = postgres_schema
    return AtomsLedger(PostgresRepository(dsn, schema=schema))


def test_concurrent_exact_structure_ingestion_persists_one_record(
    postgres_schema: tuple[str, str],
) -> None:
    dsn, schema = postgres_schema
    provenance = Provenance(created_by="test", purpose="concurrent")

    def ingest(_: int) -> str:
        ledger = AtomsLedger(PostgresRepository(dsn, schema=schema))
        result = ledger.add_structure(
            Atoms("H2", positions=((0, 0, 0), (0, 0, 0.74))),
            source_spec=SOURCE,
            provenance=provenance,
        )
        assert isinstance(result, str)
        return result

    with ThreadPoolExecutor(max_workers=8) as executor:
        persisted_ids = set(executor.map(ingest, range(16)))

    assert len(persisted_ids) == 1
    ledger = make_postgres_ledger(postgres_schema)
    assert [record.id for record in ledger.find_structures()] == list(
        persisted_ids
    )


def test_conflicting_equivalent_content_batch_is_atomic(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_postgres_ledger(postgres_schema)

    with pytest.raises(StructureContentConflictError) as error:
        ledger.add_structures(
            (
                {
                    "atoms": Atoms("H"),
                    "provenance": Provenance(
                        created_by="test", purpose="first"
                    ),
                },
                {
                    "atoms": Atoms("H"),
                    "provenance": Provenance(
                        created_by="test", purpose="second"
                    ),
                },
            ),
            source_spec=SOURCE,
        )

    assert error.value.conflicts[0].input_index == 1
    assert list(ledger.find_structures()) == []


def test_structure_batch_rollback_is_transactional(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_postgres_ledger(postgres_schema)
    existing_id = ledger.add_structure(
        Atoms("H"),
        source_spec=SOURCE,
        provenance=Provenance(created_by="test", purpose="existing"),
    )
    existing = ledger.repository.get_structure(existing_id)
    new = replace(
        existing,
        id="str_postgres_transaction_rollback",
    )

    with pytest.raises(DuplicateRecordError):
        ledger.repository.put_structures((new, existing))

    assert list(ledger.find_structures(StructureQuery(ids=(new.id,)))) == []


def populate_complete_ledger(ledger: AtomsLedger) -> None:
    first, second = ledger.add_structures(
        (Atoms("H"), Atoms("He")),
        source_spec=SOURCE,
        provenance=Provenance(
            created_by="test", purpose="transfer", tags=("source:fixture",)
        ),
    )
    evaluation = ledger.add_evaluation(
        first,
        method=METHOD,
        properties={"energy": -1.0},
        provenance=Provenance(
            created_by="test", purpose="label", tags=("quality:reference",)
        ),
    )
    ledger.add_tags_many({first: ("split:train",), evaluation: ("reviewed",)})
    ledger.add_trajectory(
        kind="relaxation",
        frames=(
            TrajectoryFrame(first, (evaluation,)),
            TrajectoryFrame(second),
        ),
        provenance=Provenance(created_by="test", purpose="trajectory"),
    )
    query_id = ledger.create_stored_query(
        label="transfer-query",
        query=DatasetQuery(
            evaluations=EvaluationQuery(method_names=(METHOD.name,))
        ),
        provenance=Provenance(created_by="test", purpose="query"),
    )
    ledger.materialize_stored_query(
        stored_query_id=query_id,
        name="frozen-transfer",
        external_key="transfer:frozen",
    )


def test_sqlite_postgres_sqlite_transfer_preserves_complete_ledger(
    postgres_schema: tuple[str, str], tmp_path: Path
) -> None:
    source = AtomsLedger(tmp_path / "source.sqlite")
    populate_complete_ledger(source)
    postgres = make_postgres_ledger(postgres_schema)

    first_report = transfer_repository(source.repository, postgres.repository)
    assert first_report.written == 6
    verify_repository_subset(source.repository, postgres.repository)
    assert postgres.repository.get_post_ingestion_tags(
        next(iter(source.repository.iter_structures())).id
    ) == {"split:train"}

    destination = AtomsLedger(tmp_path / "destination.sqlite")
    second_report = transfer_repository(
        postgres.repository, destination.repository
    )
    assert second_report.written == 6
    verify_repository_subset(source.repository, destination.repository)
    assert destination.repository.get_post_ingestion_tags(
        next(iter(source.repository.iter_structures())).id
    ) == {"split:train"}
    assert len(destination.list_aggregations()) == 1
    assert len(tuple(destination.repository.iter_trajectories())) == 1
