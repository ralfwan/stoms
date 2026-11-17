from pathlib import Path

import pytest
from ase import Atoms

from stoms.atomsledger import (
    AggregationMemberInput,
    AggregationNotFoundError,
    AggregationValidationError,
    AtomsLedger,
    DatasetQuery,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)
from stoms.atomsledger.serialization import record_fingerprint

SOURCE = StructureSourceSpec(kind="direct", name="test")
METHOD = MethodSpec(method_identifier="dft-v1", family="DFT", name="VASP")


def structure(ledger: AtomsLedger, index: int) -> str:
    result = ledger.add_structure(
        Atoms("H", positions=[(float(index), 0, 0)]),
        SOURCE,
        Provenance(created_by="test", purpose="fixture"),
    )
    assert isinstance(result, str)
    return result


def evaluation(ledger: AtomsLedger, structure_id: str, energy: float) -> str:
    return ledger.add_evaluation(
        structure_id,
        method=METHOD,
        properties={"energy": energy},
        provenance=Provenance(created_by="test", purpose="label"),
    )


def test_export_copies_only_members_and_paired_evaluations(
    tmp_path: Path,
) -> None:
    source = AtomsLedger(tmp_path / "source.ledger")
    first, second, outsider = (structure(source, i) for i in range(3))
    paired = evaluation(source, first, -1.0)
    evaluation(source, first, -1.5)  # same structure, not in the aggregation
    evaluation(source, outsider, -3.0)
    source.add_tags(first, ["reviewed"])
    source.add_tags(paired, ["converged"])
    aggregation = source.create_aggregation(
        name="selected",
        members=(
            AggregationMemberInput(second),
            AggregationMemberInput(first, paired),
        ),
    )
    source.create_aggregation(
        name="other", members=(AggregationMemberInput(outsider),)
    )

    destination = tmp_path / "subset.ledger"
    report = source.export_aggregation(aggregation.id, destination)

    assert report.structures_written == 2
    assert report.evaluations_written == 1
    assert report.aggregations_written == 1
    target = AtomsLedger.open(destination)
    copied = target.repository.get_aggregation(aggregation.id)
    assert record_fingerprint(copied) == record_fingerprint(
        source.repository.get_aggregation(aggregation.id)
    )
    assert {record.id for record in target.repository.iter_structures()} == {
        first,
        second,
    }
    assert [record.id for record in target.repository.iter_evaluations()] == [
        paired
    ]
    assert [summary.id for summary in target.list_aggregations()] == [
        aggregation.id
    ]
    assert target.get_tags(first) == source.get_tags(first)
    assert "converged" in target.get_tags(paired)


def test_export_copies_the_source_stored_query(tmp_path: Path) -> None:
    source = AtomsLedger(tmp_path / "source.ledger")
    structure(source, 0)
    query_id = source.create_stored_query(
        label="all",
        query=DatasetQuery(),
        provenance=Provenance(created_by="test", purpose="query"),
    )
    aggregation = source.materialize_stored_query(
        stored_query_id=query_id, name="all"
    )

    report = source.export_aggregation(
        aggregation.id, tmp_path / "subset.ledger"
    )

    assert report.stored_queries_written == 1
    target = AtomsLedger.open(tmp_path / "subset.ledger")
    assert target.get_stored_query(query_id).id == query_id


def test_export_rejects_superseding_aggregation(tmp_path: Path) -> None:
    source = AtomsLedger(tmp_path / "source.ledger")
    first = structure(source, 0)
    predecessor = source.create_aggregation(
        name="initial", members=(AggregationMemberInput(first),)
    )
    successor = source.create_aggregation(
        name="expanded",
        members=(AggregationMemberInput(first),),
        supersedes_id=predecessor.id,
    )
    destination = tmp_path / "subset.ledger"

    with pytest.raises(AggregationValidationError, match="supersedes"):
        source.export_aggregation(successor.id, destination)
    assert not destination.exists()


def test_export_rejects_missing_aggregation_and_existing_file(
    tmp_path: Path,
) -> None:
    source = AtomsLedger(tmp_path / "source.ledger")
    aggregation = source.create_aggregation(
        name="one", members=(AggregationMemberInput(structure(source, 0)),)
    )
    destination = tmp_path / "subset.ledger"

    with pytest.raises(AggregationNotFoundError):
        source.export_aggregation("agg_missing", destination)
    assert not destination.exists()

    destination.write_text("keep me")
    with pytest.raises(FileExistsError):
        source.export_aggregation(aggregation.id, destination)
    assert destination.read_text() == "keep me"

    source.export_aggregation(aggregation.id, destination, overwrite=True)
    assert AtomsLedger.open(destination).list_aggregations()[0].id == (
        aggregation.id
    )
