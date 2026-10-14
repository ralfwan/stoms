# Researcher quick start

This guide is for adding structures and calculation results to a project- or one-time
ledger. Ledgers can be shared and combined.

## One-time setup

Install `stoms` with `uv`:

```bash
uv add stoms
```

A specific ledger can be accessed through its storage location. It is either opened or otherwise created.

```python
from stoms.atomsledger import AtomsLedger

ledger = AtomsLedger("my.ledger")
```

The `.ledger` file is a searchable, immutable archive for structures and evaluations. `Aggregation` objects freeze ordered structure/evaluation membership and can be exported in extxyz format. These aggregations are themselves immutable and, thereby, reproducible.

## Example usage

```python
import numpy as np
from ase import Atoms

from stoms.atomsledger import (
    AtomsLedger,
    EvaluationInput,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)

# your data loaded into a list of atoms objects
structures = [
    Atoms("H2", positions=[(0, 0, 0), (0, 0, 0.74)]),
    Atoms("H2", positions=[(0, 0, 0), (0, 0, 0.80)]),
]

ledger = AtomsLedger("my.ledger")

source = StructureSourceSpec(
    kind="generated",             # How the structures were obtained.
    name="random-displacements",  # The algorithm or generator name.
    tool="my-generator",          # Software that ran the algorithm.
    version="1.0",
    parameters={"amplitude": 0.05, "seed": 1234},  # any
)
structure_provenance = Provenance(
    created_by="Ada Example",      # Person or automated tool doing this write.
    purpose="structures for MLIP comparison",
    tags=("project:demo", "system:h2"),  # any
    metadata={"input_file": "structures.xyz"},
)

# the data batch (atoms list) shares Spec and Provenance
structure_ids = ledger.add_structures(
    structures,
    source_spec=source,
    provenance=structure_provenance,
)

# if you have any energies and forces
# method_identifier is the central matching key, you can choose any text or, for example, a file hash
method = MethodSpec(
    method_identifier="medium-omat-0",  # Stable name used to select results.
    family="MLIP",
    name="MACE OMAT foundation model (medium)",
    version="0.3.15",
    code="mace-torch",
)
evaluation_provenance = Provenance(
    created_by="Ada Example",
    purpose="MLIP evaluation of generated structures",
    tags=("project:demo", "evaluator:medium-omat-0"),
)

# Replace these illustrative values with the energy and forces you already have.
mlip_results = [
    {"energy": -1.0, "forces": np.zeros((len(atoms), 3))}
    for atoms in structures
]
evaluation_ids = ledger.add_evaluations(
    EvaluationInput(
        structure_id=structure_id,
        method=method,
        properties=properties,
        provenance=evaluation_provenance,
    )
    for structure_id, properties in zip(
        structure_ids, mlip_results, strict=True
    )
)
```

`StructureSourceSpec` answers "how was this structure made?" `MethodSpec`
answers "what produced these numerical values?" `Provenance` answers "who
placed this record here, and why?" The fields are immutable after insertion.

## Project defaults

The provenance allows you to consistently group data or differentiate between different data.

```python
from stoms.atomsledger import Provenance

RESEARCHER = "YOUR_NAME_OR_ORCID"
PROJECT_TAGS = ("project:example", "collection:initial")


def project_provenance(*, purpose, tags=(), notes=None, metadata=None):
    return Provenance(
        created_by=RESEARCHER,
        purpose=purpose,
        tags=PROJECT_TAGS + tuple(tags),
        notes=notes,
        metadata=metadata or {},
    )
```

Keep `RESEARCHER` personal: it identifies the person who ingested this record.
The shared `PROJECT_TAGS` and standard purposes can be predefined by the group.
Only use a supplied standard purpose when it truthfully describes the record.

## Add a structure

Use the source specification that describes how the structure was obtained.
For a structure you built directly, the following is sufficient:

```python
from ase import Atoms
from stoms.atomsledger import StructureSourceSpec

atoms = Atoms("H2", positions=[(0, 0, 0), (0, 0, 0.74)])
source = StructureSourceSpec(kind="direct", name="manual-build")

structure_id = ledger.add_structure(
    atoms,
    source,
    project_provenance(
        purpose="initial structure for geometry optimisation",
        tags=("system:h2",),
    ),
)
```

For generated, downloaded, or relaxed structures, use a source specification
provided by the project or ask the data owner. It must describe the actual
generator, database, or calculation, not the ledger destination.

If `add_structure` returns matches rather than one `str_...` ID, equivalent
structure content is already in the ledger with different provenance or source
details. Stop and compare the records before adding another copy. Can be overruled via `allow_equivalent_atoms=True`.

## Add calculation results

An evaluation labels one existing structure. Keep a named `MethodSpec` for each
agreed computational method, then reuse it only for runs with that same method
identity and settings.

```python
import numpy as np

from stoms.atomsledger import MethodSpec

method = MethodSpec(
    method_identifier="example-dft-v1",
    family="DFT",
    name="Example DFT workflow",
    code="VASP",
)

evaluation_id = ledger.add_evaluation(
    structure_id,
    method=method,
    properties={"energy": -1.0, "forces": np.zeros((2, 3))},
    provenance=project_provenance(
        purpose="single-point reference calculation",
        tags=("quality:reference",),
        metadata={"calculation_directory": "relative/path/to/run"},
    ),
)
```

Replace the example energy, forces, method, and calculation path with the real
results. Do not use an incomplete or failed calculation as a reference label.
For VASP results, use the VASP parser guide rather than manually copying values
where possible.

## Before sharing data

1. Confirm that each structure has the intended source description and each
   record names its actual ingester.
2. Confirm the method identifier and its settings identify the calculation.
3. Keep the original inputs and outputs accessible from the path or notes you
   recorded.

Do not edit SQLite tables directly. Ledger records are immutable; if metadata is
wrong, tell the group lead rather than silently changing history. Use the `stoms` API for any access.

## Inspect aggregations from the command line

Install STOMS to get the supported `stoms` command. The ledger
path must already exist:

```bash
stoms --ledger my.ledger aggregations list
stoms --ledger my.ledger aggregations show agg_...
```

`list` shows the newest aggregations first. `show` requires the complete
aggregation ID and displays its ordered members with compact source and method
labels. Source labels combine source name, tool, and kind; method labels combine
method name and identifier. Evaluation property names are shown with their declared units; no
property values are printed. Large audit details are opt-in:

```bash
stoms --ledger my.ledger aggregations show agg_... --details source
stoms --ledger my.ledger aggregations show agg_... --details method
stoms --ledger my.ledger aggregations show agg_... --details evaluation-provenance
stoms --ledger my.ledger aggregations show agg_... --details all
stoms --ledger my.ledger aggregations show agg_... --details method --structure str_...
stoms --ledger my.ledger aggregations show agg_... --format html > aggregation.html
stoms --ledger my.ledger aggregations show agg_... --format html --full-collapse > aggregation.html
stoms --ledger my.ledger aggregations report > aggregation-report.html
stoms --ledger my.ledger aggregations to-extxyz agg_... training.extxyz
```

Use these detail sections when investigating a particular source, method, or
provenance payload rather than printing every payload for every aggregation.
When `--structure` is omitted, details default to the first member. Pass a full
structure ID to inspect another member.
For a browser-friendly view, use `--format html`. It writes a standalone HTML
document with every member shown as a collapsed section; expanding a member
reveals its source, method, and provenance details without repeating them in
the main list. By default, only the first two levels are collapsed; deeper
nodes are expanded but remain collapsible. Add `--full-collapse` to collapse
every nested block initially.
To browse all aggregations from one file, use `aggregations report`. The report
starts with a clickable index and includes a linked detail section for every
aggregation. Add `--full-collapse` to the report command for fully collapsed
recursive data.
For interactive browsing, run `stoms --ledger my.ledger serve --open`. It
starts a read-only homepage on `http://127.0.0.1:8765/` (change it with
`--port`; `--port 0` picks a free port) that lists all aggregations and lets
you filter, sort, and narrow members by iteration. Member source, method, and
provenance details load only when you expand a member, so large ledgers stay
responsive. Each aggregation page also shows a summary: evaluation coverage
per iteration and histograms for every numeric property, per method. Scalar
properties can be viewed per structure or divided by atom count; per-atom
arrays such as forces show either one value per structure (for example the
largest force magnitude) or the distribution over all atoms. Clicking a
per-structure histogram bar filters the member table to those members. The
"Export to extxyz" panel downloads the aggregation with the same label options
as `aggregations to-extxyz`. It can group members by stoichiometry, iteration,
or tag prefix, export only the checked groups, and write either one file per
group (downloaded as a zip) or a single file; every exported member needs an
evaluation. Member order follows the aggregation within each file.
"Open in structure viewer" in an expanded member opens an interactive view of
that structure: top view or views along a and b, in-plane cell repeats,
optional bonds and coordination polyhedra (adjustable pair cutoffs), and
per-element sphere sizes, bond radius, and polyhedron/plane opacity under
"Appearance".
Atoms can be hidden by element or sliced by fractional coordinates (for
example only atoms with c >= 0.7). Miller planes are given as
h·x + k·y + l·z = t in fractional coordinates, where t is the distance from the
origin in units of d_hkl. Atoms can be coloured by element, by height along the
surface normal, or by the per-atom force difference between two evaluations of
the structure. The evaluation picker lists every evaluation recorded for the
structure, labelled by method and a short hash of its full method
specification, so models sharing a method identifier stay distinguishable.
"Related structures" lists structures for stepping with the arrow keys: either
those sharing a tag prefix (default `run:`) or the members of an aggregation in
member order. A structure opened from an aggregation steps through that
aggregation by default. With a tag prefix, structures from the same iteration,
such as a run's founder, winner, and relaxed winner, can be shown side by side
with synchronized rotation; each panel is captioned with its `role:` tag. Viewer settings are remembered in the
browser, and "Reset all viewer settings" restores the defaults. The server
binds to the local machine only by default and stops with Ctrl+C. Unlike
`report`, it reflects the ledger's current contents on every page load.
To export an aggregation's immutable member order and attached evaluations,
use `aggregations to-extxyz AGGREGATION_ID DESTINATION`. By default, energy and
forces are written as `REF_energy` and `REF_forces`; override these names with
`--energy-label` and `--forces-label`. Pass `--include-node-energy` to include
per-atom energies, optionally changing its `REF_node_energy` property name with
`--node-energy-label`.

## Before beginning

Decide on / collect / define

1. The project tag and standard purposes.
2. Specifications for the structure sources you will use.
3. Named method specifications for each calculation protocol.
