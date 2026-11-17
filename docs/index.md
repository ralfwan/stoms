# STOMS

STOMS (Storage Tool Of Minor Significance) has two parts: a structure viewer
that runs in your browser (`stoms serve`), and an immutable, provenance-first
ledger for atomistic research data, whose public package is
`stoms.atomsledger`.

To look at a ledger, an extxyz file or phonopy output, start the viewer with
`uvx stoms --ledger data.ledger serve --open` (or `--file frames.extxyz`); see
[Viewing a ledger](viewing-a-ledger.md). In a Jupyter notebook,
`stoms.viewer.view(atoms)` shows any ASE `Atoms`, list of them or trajectory
with the same viewer and SVG export, without a ledger; see
[ASE structures in Jupyter](jupyter.md).

The ledger stores calculator-free ASE `Atoms` snapshots separately from their
numerical evaluations. One structure can therefore receive multiple labels
without rewriting its immutable structure record.

## What it provides

- Portable, indexed SQLite storage and PostgreSQL operational storage for ASE
  structures and evaluations.
- Required provenance and content-aware structure ingestion.
- Metadata queries, a metadata-only catalog, and append-only tags.
- Strict one-structure/one-evaluation selections and numerical projections.
- Immutable stored query definitions and frozen ordered aggregations.
- Traceable extxyz export and additive verified SQLite/PostgreSQL transfer.
- An optional VASP `vasprun.xml` parser that produces evaluation inputs.
- A read-only viewer in the browser (`stoms serve`) for ledgers, extxyz and
  other structure files, and phonopy output: aggregation summaries and
  exports, a structure viewer with measurements, colouring by properties,
  ring analysis, comparisons and movies, and animated vibrational modes with
  phonon band structures and DOS.
- A notebook viewer for ASE structures (`stoms.viewer`, optional `jupyter`
  dependency): linked to Python, with vector SVG export, force arrows,
  measurements, colouring by per-atom properties, reproducible settings, and
  phonopy modes, bands and DOS.

## Support boundary

SQLite and PostgreSQL are supported storage backends. SQLite is the sole
portable archive format; PostgreSQL is an operational server backend requiring
PostgreSQL 16 or newer and the optional `postgres` dependency. HDF5 is not a
supported public API or interchangeable format.

STOMS is a library and a local viewer, not a database server or workflow
engine. `stoms serve` is a single-user, read-only viewer on the local machine. Read [Use cases and boundaries](use-cases.md) before adopting it.

## Install

From the `pyproject.toml` directory of the project where you will use STOMS,
add it as a dependency:

```bash
uv add stoms
```

This records STOMS in the project's `pyproject.toml`, updates its lockfile, and
creates or updates its virtual environment.

Add the optional VASP parser with:

```bash
uv add "stoms[vasp]"
```

## Next steps

- [Researcher quick start](researcher-guide.md)
- [ASE structures in Jupyter](jupyter.md)
- [Getting started](getting-started.md)
- [Use cases and boundaries](use-cases.md)
- [Public API](api.md)
- [Limitations](limitations.md)
