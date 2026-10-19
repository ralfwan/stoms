from pathlib import Path

import numpy as np
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    DatasetQuery,
    EvaluationInput,
    EvaluationQuery,
    MethodSpec,
    Provenance,
    StructureQuery,
    StructureSourceSpec,
)

root = Path("example-output")
root.mkdir(exist_ok=True)
ledger = AtomsLedger(root / "source.atomsledger")

atoms_a = Atoms("H2", positions=[(0, 0, 0), (0, 0, 0.74)])
atoms_b = atoms_a.copy()
atoms_b.positions[1, 2] = 0.80

structure_provenance = Provenance(
    created_by="example",
    purpose="Demonstrate batch insertion",
    tags=("campaign:h2-demo", "split:train"),
)
structure_ids = ledger.add_structures(
    [atoms_a, atoms_b],
    source_spec=StructureSourceSpec(
        kind="direct", name="manual-displacements"
    ),
    provenance=structure_provenance,
)

method = MethodSpec(
    method_identifier="demo-model-001",
    family="MLIP",
    name="demo-potential",
    version="1",
)
evaluation_provenance = Provenance(
    created_by="example",
    purpose="Demonstrate batch evaluations",
    tags=("quality:reference",),
)
ledger.add_evaluations(
    [
        EvaluationInput(
            structure_id=structure_id,
            method=method,
            properties={
                "energy": energy,
                "forces": np.zeros((2, 3)),
            },
            units={"energy": "eV", "forces": "eV/angstrom"},
            provenance=evaluation_provenance,
        )
        for structure_id, energy in zip(
            structure_ids,
            (-1.0, -0.9),
            strict=True,
        )
    ]
)

ledger.save_dataset(
    name="h2-training",
    description="All H2 demo training structures with energy and forces",
    query=DatasetQuery(
        structures=StructureQuery(tags_all=("campaign:h2-demo",)),
        evaluations=EvaluationQuery(properties_all=("energy", "forces")),
        require_evaluation=True,
    ),
    provenance=Provenance(
        created_by="example",
        purpose="Define a reusable extxyz export",
    ),
)

ledger.to_extxyz(
    root / "h2-training.extxyz",
    dataset="h2-training",
    evaluator=EvaluationQuery(method_identifiers=("demo-model-001",)),
)

report = ledger.export_database(
    root / "portable.atomsledger",
    overwrite=True,
)
print(report)
