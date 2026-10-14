from dataclasses import replace

import numpy as np
import pytest
from ase import Atoms

pytest.importorskip(
    "psycopg", reason="install the postgres optional dependency"
)

from stoms.atomsledger import (
    AtomsLedger,
    DuplicateRecordError,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    StructureQuery,
    StructureSourceSpec,
    TrajectoryFrame,
)
from stoms.atomsledger.backends.postgres import PostgresRepository

SOURCE = StructureSourceSpec(
    kind="direct", name="postgres-test", parameters={"seed": 4}
)
METHOD = MethodSpec(
    method_identifier="vasp-r2scan",
    family="DFT",
    name="VASP-r2SCAN",
    version="6.5.1",
    code="VASP",
    parameters={"ENCUT": 440},
)


def make_ledger(postgres_schema: tuple[str, str]) -> AtomsLedger:
    dsn, schema = postgres_schema
    return AtomsLedger(PostgresRepository(dsn, schema=schema))


def populate(ledger: AtomsLedger) -> tuple[list[str], list[str]]:
    structure_ids = ledger.add_structures(
        (
            Atoms("H2", positions=((0, 0, 0), (0, 0, 0.74))),
            Atoms("He", positions=((0, 0, 0),)),
        ),
        source_spec=SOURCE,
        provenance=Provenance(
            created_by="test",
            purpose="PostgreSQL core records",
            tags=("study:core",),
        ),
    )
    evaluation_ids = ledger.add_evaluations(
        (
            {
                "structure_id": structure_ids[0],
                "method": METHOD,
                "properties": {"energy": -1.0, "forces": np.zeros((2, 3))},
                "provenance": Provenance(
                    created_by="test",
                    purpose="Reference label",
                    tags=("quality:reference",),
                ),
            },
            {
                "structure_id": structure_ids[1],
                "method": replace(
                    METHOD,
                    method_identifier="orca-pbe",
                    name="ORCA-PBE",
                    version="6.0.0",
                    code="ORCA",
                ),
                "properties": {"energy": -0.5},
                "provenance": Provenance(
                    created_by="test",
                    purpose="Secondary label",
                    tags=("quality:test",),
                ),
            },
        )
    )
    return structure_ids, evaluation_ids


def test_core_record_round_trip_and_trajectory(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_ledger(postgres_schema)
    structure_ids, evaluation_ids = populate(ledger)

    structure = ledger.load_atoms(structure_ids[0])
    assert structure.get_chemical_formula() == "H2"
    assert (
        ledger.repository.get_structure(structure_ids[0]).source_spec == SOURCE
    )
    assert ledger.load_evaluation(evaluation_ids[0]).method == METHOD

    trajectory_id = ledger.add_trajectory(
        kind="relaxation",
        frames=(TrajectoryFrame(structure_ids[0], (evaluation_ids[0],)),),
        provenance=Provenance(created_by="test", purpose="Trajectory"),
    )
    assert ledger.repository.get_trajectory(trajectory_id).frames == (
        TrajectoryFrame(structure_ids[0], (evaluation_ids[0],)),
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        (StructureQuery(ids=()), ()),
        (StructureQuery(formula="H2"), (0,)),
        (StructureQuery(tags_all=("study:core",)), (0, 1)),
        (StructureQuery(tags_any=("study:core", "missing")), (0, 1)),
        (StructureQuery(tags_none=("missing",)), (0, 1)),
        (StructureQuery(tags_none=("study:core",)), ()),
        (StructureQuery(purpose_contains="CORE"), (0, 1)),
    ),
)
def test_structure_queries_match_current_model(
    postgres_schema: tuple[str, str],
    query: StructureQuery,
    expected: tuple[int, ...],
) -> None:
    ledger = make_ledger(postgres_schema)
    structure_ids, _ = populate(ledger)

    assert [record.id for record in ledger.find_structures(query)] == [
        structure_ids[index] for index in expected
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    (
        (EvaluationQuery(ids=()), ()),
        (EvaluationQuery(method_families=("DFT",)), (0, 1)),
        (EvaluationQuery(method_names=("VASP-r2SCAN",)), (0,)),
        (EvaluationQuery(method_versions=("6.5.1",)), (0,)),
        (EvaluationQuery(method_codes=("VASP",)), (0,)),
        (EvaluationQuery(method_identifiers=("orca-pbe",)), (1,)),
        (EvaluationQuery(properties_all=("energy", "forces")), (0,)),
        (EvaluationQuery(tags_all=("quality:reference",)), (0,)),
        (EvaluationQuery(tags_any=("quality:test", "missing")), (1,)),
        (EvaluationQuery(tags_none=("quality:reference",)), (1,)),
    ),
)
def test_evaluation_queries_match_current_model(
    postgres_schema: tuple[str, str],
    query: EvaluationQuery,
    expected: tuple[int, ...],
) -> None:
    ledger = make_ledger(postgres_schema)
    _, evaluation_ids = populate(ledger)

    assert [record.id for record in ledger.find_evaluations(query)] == [
        evaluation_ids[index] for index in expected
    ]


def test_structure_batch_rolls_back_after_duplicate(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_ledger(postgres_schema)
    structure_ids = ledger.add_structures(
        (Atoms("H"),),
        source_spec=SOURCE,
        provenance=Provenance(created_by="test", purpose="Existing"),
    )
    existing = ledger.repository.get_structure(structure_ids[0])
    new = replace(existing, id="str_postgres_rolled_back")

    with pytest.raises(DuplicateRecordError):
        ledger.repository.put_structures((new, existing))

    assert list(ledger.find_structures(StructureQuery(ids=(new.id,)))) == []


def test_structure_purpose_query_uses_unicode_casefold(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_ledger(postgres_schema)
    structure_id = ledger.add_structure(
        Atoms("H"),
        source_spec=SOURCE,
        provenance=Provenance(created_by="test", purpose="Straße candidate"),
    )

    assert [
        record.id
        for record in ledger.find_structures(
            StructureQuery(purpose_contains="STRASSE")
        )
    ] == [structure_id]


def test_post_ingestion_tags_are_effective_and_idempotent(
    postgres_schema: tuple[str, str],
) -> None:
    ledger = make_ledger(postgres_schema)
    structure_ids, evaluation_ids = populate(ledger)

    assert ledger.add_tags_many(
        {
            structure_ids[0]: ("split:train", "split:train"),
            evaluation_ids[0]: ("reviewed",),
        }
    ) == {
        structure_ids[0]: frozenset({"study:core", "split:train"}),
        evaluation_ids[0]: frozenset({"quality:reference", "reviewed"}),
    }
    assert ledger.repository.get_post_ingestion_tags(structure_ids[0]) == {
        "split:train"
    }
    assert [
        record.id
        for record in ledger.find_structures(
            StructureQuery(tags_all=("study:core", "split:train"))
        )
    ] == [structure_ids[0]]
    assert [
        record.id
        for record in ledger.find_evaluations(
            EvaluationQuery(tags_none=("reviewed",))
        )
    ] == [evaluation_ids[1]]


def test_catalog_returns_metadata_without_deserializing_payloads(
    postgres_schema: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = make_ledger(postgres_schema)
    structure_ids, evaluation_ids = populate(ledger)

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("catalog search deserialized a payload")

    monkeypatch.setattr(
        "stoms.atomsledger.backends.postgres.atoms_from_binary_payload", fail
    )
    monkeypatch.setattr(
        "stoms.atomsledger.backends.postgres.properties_from_binary_payload",
        fail,
    )

    entries = ledger.repository.catalog_structures(
        StructureQuery(tags_all=("study:core",))
    )

    assert [entry.id for entry in entries] == structure_ids
    assert entries[0].formula == "H2"
    assert entries[0].available_property_names == ("energy", "forces")
    assert entries[0].evaluators[0].id == evaluation_ids[0]
    assert entries[0].evaluators[0].method == METHOD
    assert entries[0].evaluators[0].property_names == ("energy", "forces")
