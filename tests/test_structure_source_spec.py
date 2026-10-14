import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    Provenance,
    StructureSourceSpec,
)
from stoms.atomsledger.serialization import (
    json_dumps,
    structure_source_content_hash,
    structure_source_to_dict,
)


def test_source_spec_hash_is_canonical_and_roundtrips(tmp_path: Path) -> None:
    first = StructureSourceSpec(
        kind="simulation",
        name="relaxation",
        tool="VASP-6.5.1",
        parameters={"cutoff": 520, "settings": {"ediff": 1e-6}},
    )
    second = StructureSourceSpec(
        kind="simulation",
        name="relaxation",
        tool="VASP-6.5.1",
        parameters={"settings": {"ediff": 1e-6}, "cutoff": 520},
    )

    assert first == second
    assert structure_source_content_hash(
        first
    ) == structure_source_content_hash(second)

    ledger = AtomsLedger(tmp_path / "source.sqlite")
    structure_id = ledger.add_structure(
        Atoms("H"),
        first,
        Provenance(created_by="test", purpose="source"),
    )
    assert isinstance(structure_id, str)

    assert ledger.repository.get_structure(structure_id).source_spec == first


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kind", " direct", "leading or trailing whitespace"),
        ("name", "direct ", "leading or trailing whitespace"),
        ("tool", "", "must not be empty"),
    ],
)
def test_source_spec_identifier_validation(
    field: str, value: str, message: str
) -> None:
    values: dict[str, Any] = {"kind": "direct", "name": "user"}
    values[field] = value

    with pytest.raises((TypeError, ValueError), match=message):
        StructureSourceSpec(**values)


def test_source_spec_rejects_non_json_values() -> None:
    with pytest.raises(TypeError, match=r"parameters.steps"):
        StructureSourceSpec(
            kind="simulation",
            name="relaxation",
            parameters={"steps": (1, 2)},
        )


def test_source_spec_is_part_of_structure_conflict_identity(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "conflict.sqlite")
    provenance = Provenance(created_by="test", purpose="same")
    first = StructureSourceSpec(kind="direct", name="first")
    second = StructureSourceSpec(kind="direct", name="second")

    ledger.add_structure(Atoms("H"), first, provenance)

    result = ledger.add_structure(Atoms("H"), second, provenance)

    assert not isinstance(result, str)
    assert result[0].provenance == provenance


def test_model_identifier_is_opaque_and_legacy_sources_are_migrated(
    tmp_path: Path,
) -> None:
    source = StructureSourceSpec(
        kind="sampling",
        name="cmaes",
        model_identifier="model-a",
    )
    assert source.model_identifier == "model-a"
    assert "model_identifier" in structure_source_to_dict(source)
    assert "model_id" not in structure_source_to_dict(source)
    with pytest.raises(TypeError):
        StructureSourceSpec(kind="sampling", name="cmaes", model_id="old")

    ledger_path = tmp_path / "migration.sqlite"
    ledger = AtomsLedger(ledger_path)
    structure_id = ledger.add_structure(
        Atoms("H"),
        source,
        Provenance(created_by="test", purpose="migration"),
    )
    assert isinstance(structure_id, str)

    legacy = structure_source_to_dict(source)
    legacy["model_id"] = legacy.pop("model_identifier")
    legacy_id = hashlib.sha256(json_dumps(legacy).encode()).hexdigest()
    with sqlite3.connect(ledger_path) as connection:
        connection.execute(
            "INSERT INTO structure_source_specs(id, specification) "
            "VALUES (?, ?)",
            (legacy_id, json.dumps(legacy, separators=(",", ":"))),
        )
        connection.execute(
            "UPDATE structures SET source_spec_id = ? WHERE id = ?",
            (legacy_id, structure_id),
        )
        connection.execute(
            "DELETE FROM structure_source_specs WHERE id = ?",
            (structure_source_content_hash(source),),
        )
        connection.execute(
            "UPDATE schema_info SET value = '7' WHERE key = 'schema_version'"
        )

    migrated = AtomsLedger(ledger_path)
    assert (
        migrated.repository.get_structure(structure_id).source_spec == source
    )
