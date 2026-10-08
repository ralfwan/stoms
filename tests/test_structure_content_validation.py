from pathlib import Path

import pytest
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    Provenance,
    RecordNotFoundError,
    StructureContentMismatchError,
    StructureSourceSpec,
)


def make_atoms(shift: float = 0.0) -> Atoms:
    return Atoms(
        "H2",
        positions=((0.0, 0.0, 0.0), (0.0, 0.0, 0.74 + shift)),
        cell=(8.0, 8.0, 8.0),
        pbc=False,
    )


def store_atoms(ledger: AtomsLedger) -> str:
    structure_id = ledger.add_structure(
        make_atoms(),
        StructureSourceSpec(kind="direct", name="test"),
        Provenance(created_by="test", purpose="content validation"),
    )
    assert isinstance(structure_id, str)
    return structure_id


def test_validates_transport_cleaned_remote_atoms(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "validation.sqlite")
    structure_id = store_atoms(ledger)
    remote_atoms = ledger.load_atoms(structure_id)
    remote_atoms.info["stoms_structure_id"] = structure_id

    result_atoms = remote_atoms.copy()
    result_atoms.info.pop("stoms_structure_id")

    assert (
        ledger.validate_structure_content(structure_id, result_atoms) is None
    )


def test_rejects_different_structure_content(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "mismatch.sqlite")
    structure_id = store_atoms(ledger)

    with pytest.raises(StructureContentMismatchError) as error:
        ledger.validate_structure_content(structure_id, make_atoms(0.01))

    assert error.value.structure_id == structure_id
    assert (
        error.value.expected_structure_content_hash
        != error.value.actual_structure_content_hash
    )


def test_rejects_unknown_structure_id(tmp_path: Path) -> None:
    ledger = AtomsLedger(tmp_path / "missing.sqlite")

    with pytest.raises(RecordNotFoundError):
        ledger.validate_structure_content("str_missing", make_atoms())
