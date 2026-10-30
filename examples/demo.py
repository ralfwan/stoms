from pathlib import Path

import numpy as np
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    DatasetQuery,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    StructureQuery,
    StructureSourceSpec,
    TrajectoryFrame,
)

ledger = AtomsLedger("example-data.atomsledger")

a = 3.905
atoms = Atoms(
    "SrTiO3",
    scaled_positions=[
        (0.0, 0.0, 0.0),
        (0.5, 0.5, 0.5),
        (0.5, 0.5, 0.0),
        (0.5, 0.0, 0.5),
        (0.0, 0.5, 0.5),
    ],
    cell=[a, a, a],
    pbc=True,
)
structure_id = ledger.add_structure(
    atoms,
    StructureSourceSpec(
        kind="direct",
        name="ase.build.bulk",
        parameters={"a": 3.905, "crystalstructure": "cubic"},
        tool="ASE",
    ),
    Provenance(
        created_by="ralf",
        purpose="Prototype bulk reference for an energy-only fine-tuning study",
        tags=("SrTiO3", "bulk", "training-candidate"),
    ),
)

evaluation_id = ledger.add_evaluation(
    structure_id,
    method=MethodSpec(
        method_identifier="vasp-r2scan",
        family="DFT",
        name="VASP-r2SCAN",
        version="6.5.1",
        code="VASP",
        parameters={"ENCUT": 440, "METAGGA": "R2SCAN"},
    ),
    properties={
        "energy": -42.123,
        "forces": np.zeros((len(atoms), 3)),
    },
    units={"energy": "eV", "forces": "eV/angstrom"},
    provenance=Provenance(
        created_by="ralf",
        purpose="Reference label for MLIP fine-tuning",
        tags=("reference", "training-label"),
    ),
)

ledger.add_trajectory(
    kind="geometry-optimization",
    frames=(TrajectoryFrame(structure_id, (evaluation_id,)),),
    provenance=Provenance(
        created_by="ralf",
        purpose="Demonstrate immutable trajectory membership",
    ),
)

query = DatasetQuery(
    structures=StructureQuery(tags_all=("training-candidate",)),
    evaluations=EvaluationQuery(
        method_families=("DFT",),
        properties_all=("energy", "forces"),
    ),
    require_evaluation=True,
)

ledger.save_template(
    name="dft-training-data",
    description="DFT-labeled structures carrying energies and forces",
    query=query,
    provenance=Provenance(
        created_by="ralf",
        purpose="Reusable dataset selection",
    ),
)

count = ledger.export_extxyz(
    Path("dft-training-data.extxyz"),
    template="dft-training-data",
    evaluation_policy="latest",
)
print(f"Exported {count} frame(s)")
