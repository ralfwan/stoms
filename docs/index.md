# STOMS

STOMS (Storage Tool Of Minor Significance) is an immutable, provenance-first
ledger for atomistic research data. Its public package is `stoms.atomsledger`.

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
- A read-only local homepage (`stoms serve`) for browsing aggregations,
  property summaries, extxyz export, and a structure viewer; it can also show
  a single extxyz file.

## Support boundary

SQLite and PostgreSQL are supported storage backends. SQLite is the sole
portable archive format; PostgreSQL is an operational server backend requiring
PostgreSQL 16 or newer and the optional `postgres` dependency. HDF5 is not a
supported public API or interchangeable format.

STOMS is a library, not a database server, workflow engine, or scientific
analysis application. `stoms serve` is a single-user, read-only browser for
one ledger on the local machine. Read [Use cases and boundaries](use-cases.md) before adopting it.

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
- [Getting started](getting-started.md)
- [Use cases and boundaries](use-cases.md)
- [Public API](api.md)
- [Limitations](limitations.md)
