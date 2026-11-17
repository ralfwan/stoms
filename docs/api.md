# Public API

The supported public API is `stoms.atomsledger`. SQLite and PostgreSQL are
supported backends. Import public names from this module rather than
implementation modules.

```python
from stoms.atomsledger import AtomsLedger, SQLiteRepository

ledger = AtomsLedger("study.atomsledger")
```

`AtomsLedger()` uses `atomsledger.sqlite`. `AtomsLedger.open(path)` is a path
constructor. Passing a `Repository` implementation is supported at the service
boundary, but `SQLiteRepository` is the only supported concrete backend.

`AtomsLedger.open(path, read_only=True)` (or
`SQLiteRepository(path, read_only=True)`) opens an existing ledger so that
SQLite refuses every write; a missing file or a SQLite database that is not a
ledger raises `IntegrityError`. `stoms serve` and the `stoms aggregations`
commands open ledgers this way.

## Domain values

| Public value | Purpose |
|---|---|
| `Provenance` | Required `created_by` and `purpose`; optional immutable tags, notes, and strict JSON metadata. |
| `StructureSourceSpec` | Immutable description of a structure-producing process. |
| `MethodSpec` | Description of an evaluation method; `method_identifier` is its ordinary matching identity. |
| `StructureInput`, `EvaluationInput`, `TrajectoryFrame` | Batch ingestion and trajectory inputs. |
| `StructureRecord`, `EvaluationRecord`, `TrajectoryRecord` | Immutable persisted records. |
| `StoredQuery`, `StoredQuerySummary` | Immutable query definitions and listing views. |
| `Aggregation`, `AggregationMember`, `AggregationMemberInput`, `AggregationSummary` | Immutable ordered memberships and views. |

`StructureID`, `StoredQueryID`, and `AggregationID` are string aliases. The
library creates type-prefixed IDs such as `str_`, `eval_`, `traj_`, `query_`, and
`agg_`.

## Public imports

`stoms.atomsledger.__all__` exports the following names:

| Group | Names |
|---|---|
| Service and storage | `AtomsLedger`, `SQLiteRepository`, `SQLiteCatalog` |
| Records and views | `StructureRecord`, `EvaluationRecord`, `TrajectoryRecord`, `StoredQuery`, `StoredQuerySummary`, `Aggregation`, `AggregationSummary`, `AggregationMember`, `StructureContentMatch`, `StructureContentConflict`, `StructureCatalogEntry`, `EvaluatorCatalogEntry`, `SelectedRecord`, `NumericalProjection`, `StrictSelection` |
| Inputs and query values | `StructureInput`, `EvaluationInput`, `TrajectoryFrame`, `AggregationMemberInput`, `Provenance`, `StructureSourceSpec`, `MethodSpec`, `StructureQuery`, `EvaluationQuery`, `DatasetQuery`, `EvaluatorSelector` |
| Type aliases | `StructureID`, `StoredQueryID`, `AggregationID`, `JSONValue` |
| Transfer | `TransferReport`, `transfer_repository`, `verify_repository_subset`, `export_sqlite`, `import_sqlite` |
| Errors and warning | `AtomsLedgerError`, `RecordNotFoundError`, `DuplicateRecordError`, `IntegrityError`, `StrictSelectionError`, `StructureContentConflictError`, `StructureContentMismatchError`, `AggregationConflictError`, `AggregationNotFoundError`, `AggregationValidationError`, `LedgerOverwriteError`, `StoredQueryInUseError`, `SerializationError`, `EquivalentAtomsWarning` |

## Ingest and read

```python
ledger.add_structure(atoms, source_spec, provenance, *, allow_equivalent_atoms=False)
ledger.add_structures(items, *, source_spec, provenance=None, allow_equivalent_atoms=False)
ledger.add_evaluation(structure_id, *, method, properties, units=None, provenance)
ledger.add_evaluations(items)
ledger.add_trajectory(*, kind, frames, provenance)

ledger.load_atoms(structure_id)
ledger.load_evaluation(evaluation_id)
ledger.validate_structure_content(structure_id, atoms)
ledger.find_structures(query=None)
ledger.find_evaluations(query=None)
ledger.list_method_identifiers()
```

`add_structure` returns a record ID or `StructureContentMatch` values.
`add_structures` returns IDs or raises `StructureContentConflictError` atomically.
Evaluation ingestion requires one or more of `energy`, `forces`, or `node_energy`.
Their accepted shapes are `()`/`(1,)`, `(n, 3)`, and `(n,)`; their default units
are `eV`, `eV/angstrom`, and `eV`.

## Query, catalog, and tags

```python
StructureQuery(...)
EvaluationQuery(...)
DatasetQuery(structures=..., evaluations=..., require_evaluation=False)
EvaluatorSelector(method, exact_match=False)

ledger.catalog.search(query=None)
ledger.catalog.iter_search(query=None)
ledger.add_tags(record_id, tags)
ledger.add_tags_many(records)
ledger.get_tags(record_id)
```

`StructureQuery` filters by ID, content hash, formula, effective tags, purpose,
and time. `EvaluationQuery` filters by ID, structure ID, method family/name/
version/code/identifier, property presence, effective tags, and time.
`DatasetQuery.require_evaluation` does not select an evaluator for strict
selection.

The catalog returns `StructureCatalogEntry` values with evaluator metadata,
property names, and units without loading structure or numerical payloads. Tags
are append-only and supported for structures and evaluations.

## Strict selection and extxyz

```python
selection = ledger.select(query=None, *, evaluator=None, exact_match=False)
selection.project(property_name)
selection.project_energy()

ledger.to_extxyz(destination, *, dataset=None, evaluator=None, selection=None,
                 aggregation_id=None)
ledger.export_extxyz(destination, *, query=None, template=None, dataset=None,
                     evaluator=None, selection=None, aggregation_id=None,
                     include_node_energy=False)
```

`select` accepts a `DatasetQuery`, `StructureQuery`, `StoredQuery`, stored-query
ID, or `None`. A string is an ID, not a stored-query label. Evaluators can be a
method name, `MethodSpec`, `EvaluationQuery`, or `EvaluatorSelector`. Selection
raises `StrictSelectionError` unless every selected structure has exactly one
matching evaluation.

Pass `aggregation_id` to export its members in their immutable stored order.
Each member's attached evaluation ID is used directly; it cannot be combined
with a query, template, dataset, evaluator, or explicit selection.

`StrictSelection.project` returns `NumericalProjection` with aligned IDs and a
read-only NumPy array. Values must be numeric, have one declared unit, and share
a shape.

## Stored queries and aggregations

```python
ledger.create_stored_query(*, label, query, provenance, description="", hidden_at=None)
ledger.list_stored_queries()
ledger.get_stored_query(query_id)
ledger.hide_stored_query(query_id)
ledger.delete_stored_query(query_id, *, force=False)

ledger.create_aggregation(*, name, members, description=None, metadata=None,
                          external_key=None, supersedes_id=None)
ledger.materialize_stored_query(*, stored_query_id, name, description=None,
                                metadata=None, external_key=None)
ledger.get_aggregation(aggregation_id, *, include_members=True)
ledger.get_aggregation_by_external_key(external_key, *, include_members=True)
ledger.list_aggregations(*, name=None, source_stored_query_id=None,
                         metadata_filter=None)
ledger.get_aggregation_structure_ids(aggregation_id)
ledger.get_aggregation_structures(aggregation_id)
```

Stored-query labels are nonunique. Hiding changes visibility but not the query.
Deleting a query referenced by an aggregation raises `StoredQueryInUseError`
unless `force=True`. Aggregation members contain a required structure ID and an
optional evaluation ID. Membership is immutable. `external_key` permits
idempotent recreation only with matching membership and compatible fields.

## Transfer

```python
ledger.transfer_to(target, *, conflict="verify", batch_size=256)
ledger.export_database(destination, *, overwrite=False, batch_size=256)
ledger.export_aggregation(aggregation_id, destination, *, overwrite=False,
                          batch_size=256)
ledger.import_database(source, *, conflict="verify", batch_size=256)

transfer_repository(source, target, *, conflict="verify", batch_size=256)
verify_repository_subset(source, target)
export_sqlite(source, destination, *, overwrite=False, batch_size=256)
export_aggregation_sqlite(source, aggregation_id, destination, *,
                          overwrite=False, batch_size=256)
import_sqlite(source, target, *, conflict="verify", batch_size=256)
```

Conflict policy is `error`, `skip`, or `verify`. `verify` accepts an existing ID
only if its immutable fingerprint matches. Transfer is additive and never
rewrites or deletes destination records.

The exports never write to the source ledger's own file, even with
`overwrite=True` (also through a symbolic or hard link), and an extxyz export
(`to_extxyz`, `export_extxyz`) never replaces any ledger or other SQLite
database: both raise `LedgerOverwriteError`. Other existing files are replaced
by an extxyz export, and by a SQLite export only with `overwrite=True`.

`export_aggregation` writes a new SQLite ledger with one aggregation, its
member structures, and the evaluation paired with each member; other
evaluations of those structures are left out. IDs, timestamps, provenance, and
tags are preserved, and a source stored query is copied as a definition. An
aggregation with `supersedes_id` raises `AggregationValidationError`.

## Errors and warnings

Public errors derive from `AtomsLedgerError`: `RecordNotFoundError`,
`DuplicateRecordError`, `IntegrityError`, `StrictSelectionError`,
`StructureContentConflictError`, `StructureContentMismatchError`,
`AggregationConflictError`, `AggregationNotFoundError`,
`AggregationValidationError`, `LedgerOverwriteError`, `StoredQueryInUseError`,
and `SerializationError`.
Reused or equivalent structure IDs issue `EquivalentAtomsWarning`.

## Ring analysis

`stoms.analysis.find_rings` finds the rings of an atomic network in any ASE
`Atoms`; the structure viewer's Rings tab uses it.

```python
from stoms.analysis import find_rings

result = find_rings(
    atoms,
    heights={"Cu": (10.0, 11.5), "O": (10.0, 11.5)},  # along a x b, Angstrom
    cutoffs={"Cu-O": 2.3},  # others: 1.15 x covalent radii, none metal-metal
    count="auto",  # "auto", "pairs", "all", or an element symbol
    method="planar",  # or "shortest-path" for 3D networks
)
result.signature  # "4,4,4,4,8,8,8,8+1Cu"
result.counts()  # {4: 4, 8: 4}
```

`elements` limits the network to some elements. `alternating=True` bonds only
atoms of different elements. The planar method traces the faces of the network
drawn in the a-b plane, for surfaces, layers and 2D materials. It reports faces
that wrap around the cell as `open_faces`, and the atoms that each ring
encloses. When network atoms lie on top of each other in the a-b plane, its
rings may be wrong, and `result.warnings` says so. The shortest-path method finds Guttman rings up to `max_size` atoms in
any network, including bulk and amorphous 3D structures. "auto" counts atom
pairs when every bond joins two different elements, and atoms otherwise; a
ring with an odd number of atoms counts half of them, rounded up, as pairs. Each
`Ring` has its `size`, `label`, `atoms` and periodic `images`, its corner
`points` moved into the cell, and, for the planar method, its `area` and the
atoms `inside` it.

## Symmetry

`stoms.analysis.symmetry` gives the space group of an ASE `Atoms` with spglib,
which comes with the optional `symmetry` extra (`pip install "stoms[symmetry]"`).
Without it the function raises an `ImportError` that names the extra.

```python
from stoms.analysis import symmetry, symmetry_available

result = symmetry(atoms, tolerance=0.01)  # Angstrom, spglib's symprec
result.international, result.number      # "P4_2/mnm", 136
result.crystal_system                    # "tetragonal"
result.wyckoffs                          # per atom: Wyckoff letter
result.site_symmetries                   # per atom: site-symmetry symbol
result.equivalent_atoms                  # per atom: first atom of its orbit
result.to_dict()                         # plain JSON
```

Only structures periodic along a, b and c with a non-zero volume have a space
group. For others `result.applicable` is False and `result.reason` says why;
layer groups of slabs are not computed. When spglib finds no symmetry (for
example overlapping atoms), `result.number` is None and `result.reason` holds
its message. `symmetry_available()` tells whether spglib can be imported.

## Notebook viewer

`stoms.viewer` shows ASE structures in the viewer, in Jupyter or a browser,
without a ledger. The link to Python needs the optional `jupyter` dependency
(anywidget); see [ASE structures in Jupyter](jupyter.md).

```python
from stoms.viewer import view, view_phonons

viewer = view(images)                # Atoms, a list, a Trajectory or a file name
viewer.frame, viewer.settings, viewer.camera   # synced with the browser
viewer.colour_by("charges")          # also show_cell, show_bonds, show_forces, ...
viewer.add_plane(1, 1, 1)            # also slice, hidden_elements, element_colours, bond_cutoffs, ...
viewer.save("figure.svg")            # the SVG the browser drew; or ".html"
viewer.get_settings()                # settings, view and measurements, for view(..., settings=...)
viewer.profile = "advanced"          # controls shown: "simple" (default) or "advanced"; not a setting
viewer.measurements, viewer.selected_atoms
view_phonons("phonopy_params.yaml")  # with the phonopy dependency
```

Public names: `view`, `view_phonons`, `Viewer` (the widget), `StaticView`
(HTML output without a link to Python) and `StaleViewError`, raised by `save()`
when the browser has not drawn the current state.
