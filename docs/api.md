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
| Errors and warning | `AtomsLedgerError`, `RecordNotFoundError`, `DuplicateRecordError`, `IntegrityError`, `StrictSelectionError`, `StructureContentConflictError`, `StructureContentMismatchError`, `AggregationConflictError`, `AggregationNotFoundError`, `AggregationValidationError`, `StoredQueryInUseError`, `SerializationError`, `EquivalentAtomsWarning` |

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
ledger.import_database(source, *, conflict="verify", batch_size=256)

transfer_repository(source, target, *, conflict="verify", batch_size=256)
verify_repository_subset(source, target)
export_sqlite(source, destination, *, overwrite=False, batch_size=256)
import_sqlite(source, target, *, conflict="verify", batch_size=256)
```

Conflict policy is `error`, `skip`, or `verify`. `verify` accepts an existing ID
only if its immutable fingerprint matches. Transfer is additive and never
rewrites or deletes destination records.

## Errors and warnings

Public errors derive from `AtomsLedgerError`: `RecordNotFoundError`,
`DuplicateRecordError`, `IntegrityError`, `StrictSelectionError`,
`StructureContentConflictError`, `StructureContentMismatchError`,
`AggregationConflictError`, `AggregationNotFoundError`,
`AggregationValidationError`, `StoredQueryInUseError`, and `SerializationError`.
Reused or equivalent structure IDs issue `EquivalentAtomsWarning`.
