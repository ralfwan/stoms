import sqlite3
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    DatasetQuery,
    DuplicateRecordError,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    StructureQuery,
    StructureSourceSpec,
    TrajectoryFrame,
)

SOURCE = StructureSourceSpec(kind="direct", name="test")


def make_atoms(shift: float = 0.0) -> Atoms:
    return Atoms(
        "H2",
        positions=((0.0, 0.0, 0.0), (0.0, 0.0, 0.74 + shift)),
        cell=(8.0, 8.0, 8.0),
        pbc=False,
    )


def populate(ledger: AtomsLedger) -> tuple[list[str], list[str]]:
    structure_ids = ledger.add_structures(
        [make_atoms(), make_atoms(0.01)],
        source_spec=SOURCE,
        provenance=Provenance(
            created_by="test",
            purpose="SQLite batch test",
            tags=("study:h2", "split:train"),
        ),
    )
    method = MethodSpec(
        method_identifier="vasp-r2scan",
        family="DFT",
        name="VASP-r2SCAN",
        version="6.5.1",
        code="VASP",
        parameters={"ENCUT": 440},
    )
    evaluation_ids = ledger.add_evaluations(
        [
            {
                "structure_id": structure_id,
                "method": method,
                "properties": {
                    "energy": -1.0 - index,
                    "forces": np.zeros((2, 3)),
                },
                "units": {"energy": "eV", "forces": "eV/angstrom"},
                "provenance": Provenance(
                    created_by="test",
                    purpose="Reference labels",
                    tags=("quality:reference",),
                ),
            }
            for index, structure_id in enumerate(structure_ids)
        ]
    )
    ledger.add_trajectory(
        kind="test-path",
        frames=tuple(
            TrajectoryFrame(structure_id, (evaluation_id,))
            for structure_id, evaluation_id in zip(
                structure_ids, evaluation_ids, strict=True
            )
        ),
        provenance=Provenance(created_by="test", purpose="Trajectory test"),
    )
    ledger.create_stored_query(
        label="training",
        description="Training structures with reference DFT labels",
        query=DatasetQuery(
            structures=StructureQuery(tags_all=("split:train",)),
            evaluations=EvaluationQuery(
                method_names=("VASP-r2SCAN",),
                properties_all=("energy", "forces"),
            ),
            require_evaluation=True,
        ),
        provenance=Provenance(created_by="test", purpose="Saved dataset"),
    )
    return structure_ids, evaluation_ids


def test_identical_methods_are_stored_once(tmp_path: Path) -> None:
    path = tmp_path / "shared-method.sqlite"
    ledger = AtomsLedger(path)
    structure_ids = ledger.add_structures(
        [make_atoms(0.01 * index) for index in range(3)],
        source_spec=SOURCE,
        provenance=Provenance(created_by="test", purpose="shared method"),
    )
    method = MethodSpec(
        method_identifier="vasp-r2scan",
        family="DFT",
        name="VASP-r2SCAN",
        version="6.5.1",
        code="VASP",
        parameters={"ENCUT": 520, "kpoints": ((0.0, 0.0, 0.0),)},
    )

    ledger.add_evaluations(
        {
            "structure_id": structure_id,
            "method": method,
            "properties": {"energy": -float(index)},
            "provenance": Provenance(
                created_by="test", purpose="shared method evaluation"
            ),
        }
        for index, structure_id in enumerate(structure_ids)
    )

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM method_specs"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(DISTINCT method) FROM evaluations"
        ).fetchone() == (1,)
    assert all(
        evaluation.method == method for evaluation in ledger.find_evaluations()
    )


def test_sqlite_full_export_import_is_idempotent(tmp_path: Path) -> None:
    source = AtomsLedger(tmp_path / "source.atomsledger")
    structure_ids, evaluation_ids = populate(source)

    snapshot = tmp_path / "snapshot.atomsledger"
    report = source.export_database(snapshot)
    assert report.written == 6

    destination = AtomsLedger(tmp_path / "destination.atomsledger")
    first = destination.import_database(snapshot)
    second = destination.import_database(snapshot)
    assert first.written == 6
    assert second.existing == 6
    assert (
        destination.load_atoms(structure_ids[0]).get_chemical_formula() == "H2"
    )
    assert (
        destination.load_evaluation(evaluation_ids[0]).properties["energy"]
        == -1.0
    )


@pytest.mark.skip(reason="HDF5 support is quarantined until STOMS is stable")
def test_hdf5_interchange_is_preserved(tmp_path: Path) -> None:
    source = AtomsLedger(tmp_path / "source.atomsledger")
    structure_ids, _ = populate(source)

    hdf5 = tmp_path / "snapshot.h5"
    source.export_database_hdf5(hdf5)  # type: ignore[attr-defined]

    destination = AtomsLedger(tmp_path / "destination.atomsledger")
    destination.import_database_hdf5(hdf5)  # type: ignore[attr-defined]
    assert (
        destination.load_atoms(structure_ids[1]).get_chemical_formula() == "H2"
    )


def test_standard_evaluation_units_default_and_override(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "units.atomsledger")
    structure_id = ledger.add_structure(
        make_atoms(),
        SOURCE,
        Provenance(created_by="test", purpose="Standard units"),
    )
    assert isinstance(structure_id, str)

    default_id = ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="mace", family="MLIP", name="MACE"
        ),
        properties={
            "energy": np.array([-1.0]),
            "forces": np.zeros((2, 3)),
            "node_energy": np.ones(2),
        },
        provenance=Provenance(created_by="test", purpose="Default units"),
    )
    overridden_id = ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="mace-custom-units",
            family="MLIP",
            name="MACE-custom-units",
        ),
        properties={"energy": -2.0, "forces": np.zeros((2, 3))},
        units={"energy": "hartree"},
        provenance=Provenance(created_by="test", purpose="Override units"),
    )

    assert ledger.load_evaluation(default_id).units == {
        "energy": "eV",
        "forces": "eV/angstrom",
        "node_energy": "eV",
    }
    assert ledger.load_evaluation(overridden_id).units == {
        "energy": "hartree",
        "forces": "eV/angstrom",
    }


@pytest.mark.parametrize(
    "properties",
    [
        {"energy": -1.0},
        {"energy": np.array([-1.0])},
        {"forces": np.zeros((2, 3))},
        {"node_energy": np.ones(2)},
    ],
)
def test_standard_evaluation_shapes_are_accepted(
    tmp_path: Path, properties: dict[str, object]
) -> None:
    ledger = AtomsLedger(tmp_path / "shapes.atomsledger")
    structure_id = ledger.add_structure(
        make_atoms(),
        SOURCE,
        Provenance(created_by="test", purpose="Standard shapes"),
    )
    assert isinstance(structure_id, str)

    ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="mace", family="MLIP", name="MACE"
        ),
        properties=properties,
        provenance=Provenance(created_by="test", purpose="Valid shapes"),
    )
    assert len(list(ledger.find_evaluations())) == 1


@pytest.mark.parametrize(
    "properties",
    [
        {},
        {"reference": 1.0},
        {"energy": np.array([-1.0, -2.0])},
        {"energy": -1.0, "forces": np.zeros((3, 3))},
        {"energy": -1.0, "forces": np.zeros(6)},
        {"energy": -1.0, "node_energy": np.ones(3)},
        {"energy": -1.0, "node_energy": np.ones((2, 1))},
    ],
)
def test_invalid_standard_shapes_fail_before_insertion(
    tmp_path: Path, properties: dict[str, object]
) -> None:
    ledger = AtomsLedger(tmp_path / "invalid-shapes.atomsledger")
    structure_id = ledger.add_structure(
        make_atoms(),
        SOURCE,
        Provenance(created_by="test", purpose="Invalid shapes"),
    )
    assert isinstance(structure_id, str)

    with pytest.raises(ValueError):
        ledger.add_evaluation(
            structure_id,
            method=MethodSpec(
                method_identifier="mace", family="MLIP", name="MACE"
            ),
            properties=properties,
            provenance=Provenance(created_by="test", purpose="Bad shape"),
        )

    assert list(ledger.find_evaluations()) == []


def test_invalid_evaluation_rolls_back_homogeneous_batch(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "rollback.atomsledger")
    structure_ids = ledger.add_structures(
        [make_atoms(), make_atoms(0.01)],
        source_spec=SOURCE,
        provenance=Provenance(created_by="test", purpose="Batch rollback"),
    )

    with pytest.raises(ValueError):
        ledger.add_evaluations(
            [
                {
                    "structure_id": structure_ids[0],
                    "method": MethodSpec(
                        method_identifier="mace", family="MLIP", name="MACE"
                    ),
                    "properties": {"energy": -1.0},
                    "provenance": Provenance(
                        created_by="test", purpose="Valid batch item"
                    ),
                },
                {
                    "structure_id": structure_ids[1],
                    "method": MethodSpec(
                        method_identifier="mace", family="MLIP", name="MACE"
                    ),
                    "properties": {
                        "energy": -2.0,
                        "forces": np.zeros((3, 3)),
                    },
                    "provenance": Provenance(
                        created_by="test", purpose="Invalid batch item"
                    ),
                },
            ]
        )

    assert list(ledger.find_evaluations()) == []


def test_sqlite_evaluation_batch_rolls_back_on_repository_failure(
    tmp_path: Path,
) -> None:
    ledger = AtomsLedger(tmp_path / "repository-rollback.atomsledger")
    structure_id = ledger.add_structure(
        make_atoms(),
        SOURCE,
        Provenance(created_by="test", purpose="Repository rollback"),
    )
    assert isinstance(structure_id, str)
    evaluation_id = ledger.add_evaluation(
        structure_id,
        method=MethodSpec(
            method_identifier="mace", family="MLIP", name="MACE"
        ),
        properties={"energy": -1.0},
        provenance=Provenance(created_by="test", purpose="Existing record"),
    )
    existing = ledger.load_evaluation(evaluation_id)
    candidate = replace(existing, id="eval_rollback_candidate")

    with pytest.raises(DuplicateRecordError):
        ledger.repository.put_evaluations([candidate, existing])

    assert list(ledger.find_evaluations()) == [existing]
