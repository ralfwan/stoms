# VASP Parser

`stoms.parsers.vasp` is an optional adapter from a VASP calculation directory
to values accepted by `stoms.atomsledger`. It is deliberately outside
`atomsledger`: VASP and pymatgen compatibility belongs at the ingestion
boundary, while the ledger remains independent of both.

Install the optional dependency with:

```bash
uv sync --extra vasp
```

Importing `stoms` and `stoms.atomsledger` does not require pymatgen. Importing
`stoms.parsers.vasp` does require it and fails clearly when it is unavailable.

## Sources

`vasprun.xml` is the primary source for VASP version, explicit and effective
INCAR values, actual k-points and weights, run type, final energy and forces,
convergence, ionic-step count, energy components, and POTCAR titles where
available. Original `INCAR`, `KPOINTS`, and `POTCAR` files enrich that data.

`explicit_incar` describes the original input. `effective_incar` describes the
values VASP used, including defaults exposed by pymatgen. `original_kpoints`
preserves the parsed original KPOINTS representation, while
`actual_kpoints` and `actual_kpoint_weights` come from `vasprun.xml` and are
used for method identity.

Only ordered POTCAR dataset metadata is returned: title, symbol, and embedded
SHA-256 value. Full POTCAR contents are never returned or persisted.

## Hashes And Recovery

The default whole-file SHA-256 set is `INCAR`, `KPOINTS`, and `POTCAR`.
`VaspParser(..., hash_files=...)` accepts a sequence of relative filenames, so
callers can explicitly hash `POSCAR` or other files. Present selected files are
hashed; missing selected files are silently omitted. `source_files` reports
only known relevant VASP files present in the directory, independently of this
selection.

Malformed or truncated XML raises `VaspParseError` by default. Setting
`allow_incomplete_xml=True` first attempts a strict parse and only asks
pymatgen to recover when that fails. A warning is recorded only when recovery
succeeds; valid XML is not labelled incomplete. Missing values are not treated
as complete data. Recoverable failures in original INCAR and KPOINTS enrichment
are recorded as warnings when XML data remain available. A missing POTCAR can
fall back to XML dataset titles. A present POTCAR that yields no parseable
datasets is fatal.

On pymatgen versions that do not expose `exception_on_bad_xml`, STOMS cannot
request a distinct recovery parse; `allow_incomplete_xml=True` does not extend
what that pymatgen version can parse.

The parsed result does not contain POSCAR or CONTCAR structures. Use the
result's `to_method_spec()` for the detailed scientific evaluator identity.
Pass `method_identifier` for the exact opaque workflow identity and `name`
separately for its human-readable method name. The parser-derived properties,
units, method parameters, and provenance remain based on the calculation
directory. Use `StructureSourceSpec` for the parser/source identity, and
`to_provenance()` for convergence, source hashes, warnings, and execution
metadata. The parser does not duplicate method or source inputs in provenance.
It does not ingest data, construct ASE structures, or parse POSCAR or CONTCAR
into a ledger structure. Callers must supply and validate the matching structure
before calling `AtomsLedger.add_evaluation`.
