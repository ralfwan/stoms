from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    EquivalentAtomsWarning,
    Provenance,
    StructureContentConflictError,
    StructureSourceSpec,
)

SOURCE = StructureSourceSpec(kind="direct", name="test")


def make_atoms(shift: float = 0.0) -> Atoms:
    return Atoms(
        "H2",
        positions=((0.0, 0.0, 0.0), (0.0, 0.0, 0.74 + shift)),
        cell=(8.0, 8.0, 8.0),
        pbc=False,
    )


def test_exact_structure_and_provenance_reuse_existing_id(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "dedup.sqlite")
    provenance = Provenance(created_by="test", purpose="candidate")

    first = ledger.add_structure(make_atoms(), SOURCE, provenance)
    assert isinstance(first, str)
    with pytest.warns(EquivalentAtomsWarning, match=first):
        second = ledger.add_structure(make_atoms(), SOURCE, provenance)
        assert isinstance(second, str)

    assert second == first
    assert [record.id for record in ledger.find_structures()] == [first]


def test_provenance_differences_report_content_conflicts(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "provenance.sqlite")
    base = Provenance(created_by="test", purpose="candidate")
    first = ledger.add_structure(make_atoms(), SOURCE, base)
    assert isinstance(first, str)
    variants = (
        replace(base, created_by="other"),
        replace(base, purpose="other"),
        replace(base, tags=("ingestion",)),
        replace(base, metadata={"cutoff": 5.0}),
        replace(base, notes="note"),
    )

    with pytest.warns(EquivalentAtomsWarning):
        matches = []
        for provenance in variants:
            result = ledger.add_structure(make_atoms(), SOURCE, provenance)
            assert not isinstance(result, str)
            matches.append(result)

    assert all([match.id for match in result] == [first] for result in matches)
    assert len(list(ledger.find_structures())) == 1


def test_different_structure_content_creates_distinct_record(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "content.sqlite")
    provenance = Provenance(created_by="test", purpose="candidate")

    first = ledger.add_structure(make_atoms(), SOURCE, provenance)
    second = ledger.add_structure(make_atoms(0.01), SOURCE, provenance)
    assert isinstance(first, str)
    assert isinstance(second, str)

    assert second != first
    assert len(list(ledger.find_structures())) == 2


def test_post_ingestion_tags_do_not_change_duplicate_identity(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "tags.sqlite")
    provenance = Provenance(created_by="test", purpose="candidate")
    first = ledger.add_structure(make_atoms(), SOURCE, provenance)
    assert isinstance(first, str)
    ledger.add_tags(first, ("invalid",))

    second = ledger.add_structure(make_atoms(), SOURCE, provenance)
    assert isinstance(second, str)

    assert second == first
    assert ledger.get_tags(first) == {"invalid"}
    assert len(list(ledger.find_structures())) == 1


def test_reporting_equivalent_content_returns_provenance_without_inserting(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "report.sqlite")
    first_provenance = Provenance(created_by="test", purpose="first")
    second_provenance = Provenance(created_by="test", purpose="second")
    first = ledger.add_structure(make_atoms(), SOURCE, first_provenance)
    assert isinstance(first, str)
    second = replace(
        ledger.repository.get_structure(first),
        id="str_raw_content_match",
        source_spec=SOURCE,
        provenance=second_provenance,
    )
    ledger.repository.put_structure(second)

    with pytest.warns(EquivalentAtomsWarning, match=first):
        matches = ledger.add_structure(
            make_atoms(),
            SOURCE,
            Provenance(created_by="test", purpose="incoming"),
            report_equivalent_content=True,
        )

    assert not isinstance(matches, str)
    assert [match.id for match in matches] == [first, second.id]
    assert [match.provenance for match in matches] == [
        first_provenance,
        second_provenance,
    ]
    assert len(list(ledger.find_structures())) == 2


def test_allow_equivalent_atoms_inserts_different_provenance(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "allow-equivalent.sqlite")
    first = ledger.add_structure(
        make_atoms(), SOURCE, Provenance(created_by="test", purpose="first")
    )
    assert isinstance(first, str)
    assert isinstance(first, str)
    assert isinstance(first, str)

    second = ledger.add_structure(
        make_atoms(),
        SOURCE,
        Provenance(created_by="test", purpose="second"),
        allow_equivalent_atoms=True,
    )
    assert isinstance(second, str)

    assert second != first
    assert len(list(ledger.find_structures())) == 2


def test_reporting_without_existing_content_inserts_normally(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "empty-report.sqlite")
    result = ledger.add_structure(
        make_atoms(),
        SOURCE,
        Provenance(created_by="test", purpose="candidate"),
        report_equivalent_content=True,
    )

    assert isinstance(result, str)
    assert len(list(ledger.find_structures())) == 1


def test_batch_deduplication_reuses_records_within_batch(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "batch.sqlite")
    provenance = Provenance(created_by="test", purpose="candidate")

    ids = ledger.add_structures(
        [make_atoms(), make_atoms(), make_atoms(0.01)],
        source_spec=SOURCE,
        provenance=provenance,
    )

    assert ids[0] == ids[1]
    assert ids[2] != ids[0]
    assert len(list(ledger.find_structures())) == 2


def test_batch_content_conflict_is_atomic(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "batch-conflict.sqlite")
    first = ledger.add_structure(
        make_atoms(), SOURCE, Provenance(created_by="test", purpose="first")
    )
    assert isinstance(first, str)

    with pytest.raises(StructureContentConflictError) as raised:
        ledger.add_structures(
            [make_atoms(), make_atoms(0.01)],
            source_spec=SOURCE,
            provenance=Provenance(created_by="test", purpose="second"),
        )

    assert raised.value.conflicts[0].input_index == 0
    assert [match.id for match in raised.value.conflicts[0].matches] == [first]
    assert "input index 0" in str(raised.value)
    assert first in str(raised.value)
    assert "purpose='first'" in str(raised.value)
    assert [record.id for record in ledger.find_structures()] == [first]


def test_allow_equivalent_atoms_applies_to_the_whole_batch(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "allow-equivalent-batch.sqlite")
    first = ledger.add_structure(
        make_atoms(), SOURCE, Provenance(created_by="test", purpose="first")
    )

    ids = ledger.add_structures(
        [make_atoms(), make_atoms(0.01)],
        source_spec=SOURCE,
        provenance=Provenance(created_by="test", purpose="second"),
        allow_equivalent_atoms=True,
    )

    assert ids[0] != first
    assert ids[1] != ids[0]
    assert len(list(ledger.find_structures())) == 3


def test_batch_reuse_warns_with_existing_ids(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "batch-warning.sqlite")
    provenance = Provenance(created_by="test", purpose="candidate")
    first = ledger.add_structure(make_atoms(), SOURCE, provenance)
    assert isinstance(first, str)

    with pytest.warns(EquivalentAtomsWarning, match=first):
        ids = ledger.add_structures(
            [make_atoms()], source_spec=SOURCE, provenance=provenance
        )

    assert ids == [first]


def test_deduplication_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "reopen.sqlite"
    provenance = Provenance(created_by="test", purpose="candidate")
    first = AtomsLedger(path).add_structure(make_atoms(), SOURCE, provenance)
    assert isinstance(first, str)

    second = AtomsLedger(path).add_structure(make_atoms(), SOURCE, provenance)
    assert isinstance(second, str)

    assert second == first


def test_concurrent_exact_ingestion_creates_one_record(tmp_path: Path) -> None:
    path = tmp_path / "concurrent.sqlite"
    provenance = Provenance(created_by="test", purpose="candidate")

    def add_one(_: int) -> str:
        result = AtomsLedger(path).add_structure(
            make_atoms(), SOURCE, provenance
        )
        assert isinstance(result, str)
        return result

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(add_one, range(16)))

    assert len(set(ids)) == 1
    assert len(list(AtomsLedger(path).find_structures())) == 1


@pytest.mark.skip(reason="HDF5 support is quarantined until STOMS is stable")
def test_hdf5_exact_ingestion_reuses_existing_id(tmp_path: Path) -> None:
    from stoms.atomsledger.backends.hdf5 import HDF5Repository

    repository = HDF5Repository(tmp_path / "dedup.h5")
    ledger = AtomsLedger(repository)  # type: ignore[arg-type]
    provenance = Provenance(created_by="test", purpose="candidate")

    first = ledger.add_structure(make_atoms(), SOURCE, provenance)
    second = ledger.add_structure(make_atoms(), SOURCE, provenance)

    assert second == first
    assert len(list(ledger.find_structures())) == 1


@pytest.mark.skip(reason="HDF5 support is quarantined until STOMS is stable")
def test_hdf5_content_conflict_does_not_insert(tmp_path: Path) -> None:
    from stoms.atomsledger.backends.hdf5 import HDF5Repository

    repository = HDF5Repository(tmp_path / "conflict.h5")
    ledger = AtomsLedger(repository)  # type: ignore[arg-type]
    first = ledger.add_structure(
        make_atoms(), SOURCE, Provenance(created_by="test", purpose="first")
    )
    assert isinstance(first, str)

    result = ledger.add_structure(
        make_atoms(), SOURCE, Provenance(created_by="test", purpose="second")
    )
    assert not isinstance(result, str)

    assert [match.id for match in result] == [first]
    assert len(list(ledger.find_structures())) == 1


def test_raw_transfer_preserves_distinct_structure_ids(tmp_path: Path) -> None:
    source = AtomsLedger(tmp_path / "source.sqlite")
    provenance = Provenance(created_by="test", purpose="candidate")
    first = source.add_structure(make_atoms(), SOURCE, provenance)
    assert isinstance(first, str)
    duplicate = replace(
        source.repository.get_structure(first), id="str_transferred_duplicate"
    )
    source.repository.put_structure(duplicate)

    export_path = tmp_path / "export.sqlite"
    source.export_database(export_path)
    destination = AtomsLedger(tmp_path / "destination.sqlite")
    destination.import_database(export_path)

    assert {record.id for record in destination.find_structures()} == {
        first,
        duplicate.id,
    }
