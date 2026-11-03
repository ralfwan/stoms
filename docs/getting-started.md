# Getting started

Passing a path creates a SQLite ledger when needed.

```python
import numpy as np
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)

ledger = AtomsLedger("study.atomsledger")
atoms = Atoms("H2", positions=[(0, 0, 0), (0, 0, 0.74)])

structure_id = ledger.add_structure(
    atoms,
    StructureSourceSpec(kind="direct", name="manual-build"),
    Provenance(
        created_by="researcher",
        purpose="reference structure",
        tags=("study:h2", "split:train"),
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
    ),
    properties={"energy": -1.0, "forces": np.zeros((2, 3))},
    provenance=Provenance(
        created_by="researcher",
        purpose="reference label",
        tags=("quality:reference",),
    ),
)
```

`add_structure` strips an attached ASE calculator. Exact repeats reuse the
existing ID. Calculator-free content that exists with different immutable
provenance or source specification is reported instead of inserted. Pass
`allow_equivalent_atoms=True` only when a distinct record is intentional.

## Query and export

```python
from stoms.atomsledger import DatasetQuery, StructureQuery

selection = ledger.select(
    DatasetQuery(structures=StructureQuery(tags_all=("split:train",))),
    evaluator="VASP-r2SCAN",
)
energy = selection.project_energy()
frames_written = ledger.to_extxyz("h2-training.extxyz", selection=selection)
```

Strict selection requires exactly one matching evaluation for every structure;
otherwise it raises `StrictSelectionError`. Numerical projections preserve
aligned structure and evaluation IDs. extxyz writes `REF_energy` and
`REF_forces` by default and retains STOMS traceability metadata.

## Dynamic query, frozen membership

```python
from stoms.atomsledger import DatasetQuery, EvaluationQuery, StructureQuery

query_id = ledger.create_stored_query(
    label="h2 training candidates",
    query=DatasetQuery(
        structures=StructureQuery(tags_all=("split:train",)),
        evaluations=EvaluationQuery(
            method_identifiers=("vasp-r2scan",),
            properties_all=("energy", "forces"),
        ),
        require_evaluation=True,
    ),
    provenance=Provenance(
        created_by="researcher", purpose="define training candidates"
    ),
)
aggregation = ledger.materialize_stored_query(
    stored_query_id=query_id,
    name="iteration-0-training",
    external_key="workflow:iteration:0:training",
)
```

Stored queries are immutable definitions whose membership may grow. An
aggregation freezes ordered membership. Stored-query labels are nonunique; a
string selector is the `query_...` ID, not a label.
