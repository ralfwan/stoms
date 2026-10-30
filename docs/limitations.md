# Limitations

These are current implementation limits, not planned behavior.

## Storage and data model

- SQLite and PostgreSQL are supported backends; SQLite is the sole portable
  archive format.
- SQLite has no server, writer coordination, or access control. PostgreSQL
  provides those natively; STOMS adds no authorization layer, connection pool,
  or backup service of its own. See [PostgreSQL operational ledger](postgres.md)
  for what STOMS adds on top of PostgreSQL's own concurrency guarantees.
- Structure, evaluation, and catalog iteration is cursor-backed. Trajectory,
  stored-query, and aggregation iteration materializes matching rows first.
- Structures, evaluations, trajectories, and aggregation membership cannot be
  updated or deleted. Tags are append-only.

## Querying and selection

- Queries cannot inspect numerical property values, atom counts, array contents,
  or scientific/geometric similarity.
- STOMS does not infer scientific equivalence between method specifications.
- `MethodSpec.model_id` is not persisted, hashed, or matched by SQLite. Do not
  use it as a durable evaluator identity; use `method_identifier` and parameters.
- `DatasetQuery(require_evaluation=True)` does not itself select an evaluator;
  strict selection still requires an evaluator criterion.

## Export and VASP

- extxyz export performs no unit conversion. It exports standard energy/forces,
  optional node energy, custom scalar values, and custom arrays with atom-count
  first dimension; other custom values are omitted.
- The VASP adapter parses `vasprun.xml` and selected sidecar metadata. It does
  not create structures, ingest records, or preserve general VASP artifacts.
- A missing POTCAR can fall back to XML titles. A present POTCAR with no
  parseable datasets is an error.
- XML recovery depends on pymatgen support. Versions without
  `exception_on_bad_xml` cannot request a distinct recovery parse.
