# STOMS (Storage Tool Of Minor Significance)

AtomsLedger is an immutable, provenance-first record store for atomistic
research data. Every ledger has the same data model and behavior; ledger scopes
only describe the user's workflow and data-stewardship role.

## Ledger Scopes

**Dev-ledger**:
A SQLite ledger used for local experimentation, prototyping, or scoping. A
project may use any number of dev-ledgers at any point in its lifecycle.
_Avoid_: scratch ledger, test ledger

**Project-ledger**:
A SQLite ledger used as the authoritative record for one research project,
including production results and selected dev data.
_Avoid_: project namespace, project partition

**Research-ledger**:
A SQLite ledger that holds data from multiple research projects.
_Avoid_: master ledger, global ledger

**Promotion**:
The additive transfer of records from one ledger into another. It does not have
scope-specific storage semantics; target ledger-entry IDs are not transferred.
_Avoid_: sync, merge, move

**Ingestion**:
The creation of immutable ledger records from structures or calculation results
produced outside the ledger. Record provenance and tags are selected at this
boundary and cannot be changed afterward.
_Avoid_: import, tagging, annotation

**Tag**:
A user-defined exact, case-sensitive string. Ingestion tags are attached through
immutable record provenance; post-ingestion tags are mutable annotations stored
in SQLite association tables. Namespaced forms such as `project:foo` and
`split:train` are recommended but not enforced.
_Avoid_: label, mutable category

**Effective tags**:
The union of immutable ingestion tags and append-only post-ingestion tags. Reads,
queries, catalog entries, selections, and exports expose effective tags without
changing provenance or record fingerprints.
_Avoid_: rewritten provenance tags

**Minimum provenance**:
The required `created_by` and `purpose` values on every ingested structure and
evaluation. Immutable ingestion tags, notes, and strict JSON `metadata` provide
optional per-record audit context. Structure-production configuration belongs to
`StructureSourceSpec`; workflow definitions and parent lineage are outside the
ledger's scope.
_Avoid_: workflow specification, provenance registry

**Training dataset**:
An aggregation of selected structures for model training. Evaluations provide
labels for those structures but are not the dataset itself.
_Avoid_: saved query, mutable record collection

**Dynamic saved query**:
An immutable saved query whose criteria are evaluated against the ledger when
used, so matching membership may grow as records are ingested.
_Avoid_: live table, mutable query

**Frozen saved query**:
An immutable saved query that selects explicit record identities, fixing its
membership without duplicating record payloads.
_Avoid_: copied dataset, data snapshot

**Saved query**:
An optional immutable query definition with a user-supplied unique label. STOMS
does not save ordinary queries automatically and rejects a duplicate label. It
defines a view over structure criteria and evaluator requirements; listing saved
queries exposes both selections. Every saved query has exactly one evaluator
selector.
_Avoid_: dataset, query version

**Strict paired selection**:
A request for specified structures and evaluator requirements that succeeds
only when every requested structure has every required evaluation. Missing data
causes an error rather than producing a partial result.
_Avoid_: best-effort pairing, partial selection

**Catalog**:
A read-only facility for listing and searching ledger metadata and evaluation
availability before requesting strict data selections. For every matched
structure, it exposes available evaluator identities and property names without
loading numerical result payloads.
_Avoid_: data browser, mutable index

**Evaluator selector**:
A caller-defined set of exact `MethodSpec` field requirements used to select
evaluations. The caller chooses its granularity, from one supplied field to a
complete method specification; the ledger does not infer scientific equivalence.
For strict selection, it must match exactly one evaluation for every selected
structure; zero or multiple matches are errors.
_Avoid_: evaluator equivalence, fuzzy method match

**Evaluator label**:
The human-readable evaluator name stored in `MethodSpec.name`. Version, code,
model ID, and parameters provide structured disambiguation; tags do not define
evaluator identity.
_Avoid_: evaluator tag, method tag

**Record retrieval**:
The default read operation returns complete immutable structure and evaluation
records. Callers extract numerical properties for their own analysis.
_Avoid_: plot data, analysis result

**Numerical projection**:
An application-neutral read operation that returns aligned record identities
and NumPy values for one selected numerical property without computing analysis
metrics or plots. It retains the original selection query as metadata and fails
when the selected values have different declared units.
_Avoid_: parity data, metric result

**Default units**:
The units assigned during ingestion when a standard numerical property has no
explicit unit. Energy defaults to `eV`, forces to `eV/angstrom`, and node energy
to `eV`; an explicit unit overrides the corresponding default.
_Avoid_: implicit units, assumed units

**Node energy**:
A one-dimensional optional output from MACE with one value for every graph node.
For the current MACE inputs, its shape is `(n,)`, where `n` is the structure's
atom count. It is not a STOMS-defined per-atom-energy concept.
_Avoid_: per-atom energy, atomic energy

**Standard evaluation properties**:
The initial property contract comprises total `energy` as a scalar or
one-element array, optional `forces` with shape `(n, 3)`, and optional MACE
`node_energy` with shape `(n,)`, where `n` is the structure's atom count.
_Avoid_: calculator state, analysis result

**Export traceability**:
The structure and evaluation identities, tags, evaluator label, and declared
units retained with an exported extxyz frame.
_Avoid_: training metadata, plot metadata

**Default extxyz labels**:
An extxyz training export writes total energy as `REF_energy` in `Atoms.info`
and forces as `REF_forces` in `Atoms.arrays`. Optional `node_energy` is omitted
unless explicitly requested; when included, it is `REF_node_energy` in
`Atoms.arrays`. Callers may override all three labels.
_Avoid_: ASE calculator results, implicit export mapping

## Record Identity

**Ledger-entry ID**:
A target-owned identifier used to store a record in one ledger. It is local
bookkeeping and is not part of the immutable record data.
_Avoid_: record identity, portable ID

**Record identity**:
An opaque UUID minted when an immutable record is first created and preserved
when that record is promoted to another ledger.
_Avoid_: primary key, ledger-entry ID

**Creation timestamp**:
A required timezone-aware UTC timestamp recording when an immutable record was
created. It is preserved during promotion and is not optional provenance.
_Avoid_: optional metadata, transfer time

**Record fingerprint**:
A deterministic hash of every immutable part of a record except its
ledger-entry ID. It verifies that a promoted record is unchanged.
_Avoid_: content hash, primary key

**Scientific content equality**:
Equality of a record's scientific payload independent of provenance, timestamp,
and record identity. For structures, this is represented by
`structure_content_hash`, which covers the calculator-free ASE snapshot.
_Avoid_: record equality, transfer equality

**Structure content hash**:
A deterministic hash of the calculator-free ASE arrays, cell, PBC, `Atoms.info`,
and constraints stored in a structure record. It identifies scientific
structure content independently of provenance and record identity.
_Avoid_: structure record ID, provenance fingerprint

**Structure content conflict**:
An ingestion input whose calculator-free content matches an existing structure
but whose immutable ingestion provenance differs. Single ingestion reports
`StructureContentMatch` values without inserting; a conflicting batch is
rolled back and raises `StructureContentConflictError`, unless the caller opts
into equivalent-atoms insertion with `allow_equivalent_atoms=True`.
_Avoid_: duplicate record, equivalent record insertion
