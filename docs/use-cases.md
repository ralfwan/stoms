# Use cases and boundaries

This page describes behavior implemented by STOMS 0.3.0.

## Good fits

### Local research ledgers

Use a SQLite ledger for an experiment, project, or research collection. The
file can be backed up, transferred, and copied to node-local scratch after
writes complete.

### Provenance-aware structure and label ingestion

Ingest ASE structures with a `StructureSourceSpec` and `Provenance`, then add
DFT, MLIP, or other evaluations for their exact structure IDs. Standard
`energy`, `forces`, and `node_energy` are shape-validated; additional properties
may also be stored.

### Duplicate-aware collection

Default ingestion detects equivalent calculator-free ASE content. Exact repeats
reuse a record; changed immutable provenance or source specification is reported
as a conflict. Distinct equivalent records require explicit opt-in.

### Dataset preparation

Discover data by formula, purpose, time, method metadata, property availability,
and effective tags. Strictly select one evaluator per structure before export.
Use a stored query for a reusable dynamic definition and an aggregation for
stable ordered workflow membership.

### Traceable export and transfer

Export strict selections to extxyz with labels and traceability metadata.
Transfer complete SQLite ledgers additively while preserving IDs, timestamps,
and post-ingestion tags.

### VASP evaluation adaptation

With the optional `vasp` extra, parse a VASP directory into properties, units,
`MethodSpec`, and `Provenance`. The caller supplies and validates the matching
ASE structure before ingestion.

### Local browsing

`stoms --ledger my.ledger serve` opens a read-only homepage on the local
machine: aggregation members, evaluation coverage and property histograms,
grouped extxyz export, and a structure viewer with slicing, Miller planes, and
force-difference colouring.

## Not provided

- A database server, multi-user coordination, authentication, or access control.
  `stoms serve` is a local, single-user, read-only view.
- A workflow scheduler, job submission system, retry engine, or workflow store.
- Analysis, metrics, model training, or scientific-equivalence inference. The
  homepage's histograms are a quick overview, not an analysis toolkit.
- Mutation/deletion of structures, evaluations, trajectories, or aggregation
  membership. Stored queries can be hidden/deleted; tags can only be added.
- Queries over numerical values, atom counts, array contents, or geometry.
- Unit conversion.
- A general input/output artifact store or automatic VASP ingestion.
- HDF5 support, including transfer or import/export.

## Operational constraints

Coordinate writers externally and never copy an active SQLite database. The
default `DELETE` journal mode leaves a quiescent database in one file. If using
WAL mode, call `SQLiteRepository.checkpoint()` and coordinate access before
copying. Broad structure, evaluation, and catalog iteration is cursor-backed;
trajectory, stored-query, and aggregation listing materializes results in memory.
