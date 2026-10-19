[![Documentation](https://img.shields.io/badge/docs-online-blue.svg)](https://ralfwan.github.io/stoms/)



# STOMS

STOMS (Storage Tool of Minor Significance) is an SQLite-first immutable,
provenance-first ledger for ASE structures and their numerical evaluations.
The public library is `stoms.atomsledger`.

SQLite and PostgreSQL are supported backends; SQLite is the portable archive
format. Structures, evaluations, trajectories, stored queries, and aggregations
are immutable; post-ingestion tags are append-only annotations.

## PostgreSQL

PostgreSQL 16 or newer is a supported operational backend. SQLite remains the
sole portable archive format. Install the optional driver dependency:

```bash
uv sync --extra postgres --dev
```

Construct a ledger from a normal DSN and a schema it exclusively owns:

```python
from stoms.atomsledger import AtomsLedger, PostgresRepository

ledger = AtomsLedger(
    PostgresRepository("postgresql://user:password@host/database", schema="project")
)
```

`PostgresRepository` creates and validates its tables in the selected schema.
Do not share that schema with unrelated applications. Export a portable SQLite
archive with `ledger.export_database("archive.atomsledger", overwrite=True)`.
See the [PostgreSQL operational ledger guide](docs/postgres.md) for project
setup and bidirectional SQLite synchronization.

Integration tests read `STOMS_POSTGRES_TEST_DSN`. The DSN must identify a
disposable database; each test creates and drops its own schema.

Start the local PostgreSQL 16 test service with Docker (Engine + the Compose
plugin):

```bash
docker compose up -d postgres
export STOMS_POSTGRES_TEST_DSN='postgresql://stoms:stoms@localhost:54329/stoms_test'
uv run pytest tests/postgres
```

If that fails with a permission error connecting to the Docker socket, your
user cannot talk to the Docker daemon yet. Adding yourself to the `docker`
group (`sudo usermod -aG docker $USER`, then a full logout/login) is the usual
fix, but it does not always take effect right away; `sudo docker compose up -d
postgres` works as a reliable fallback.

The Compose database uses in-memory storage and test-only credentials. Stop it
after testing with `docker compose down`; do not use this service for data that
must persist.

## Install

Add STOMS as a dependency:

```bash
uv add stoms
# or
pip install stoms
```

Optional extras: `stoms[postgres]` and `stoms[vasp]`.

### Development setup

To work on STOMS itself:

```bash
uv sync --dev
uv run pytest
```

Install the optional VASP parser with:

```bash
uv sync --extra vasp --dev
```

## Documentation

The documentation is ready for MkDocs publication:

- [Overview](docs/index.md)
- [Researcher quick start](docs/researcher-guide.md)
- [Getting started](docs/getting-started.md)
- [Use cases and boundaries](docs/use-cases.md)
- [Public API](docs/api.md)
- [VASP parser](docs/vasp-parser.md)
- [Limitations](docs/limitations.md)

Serve it locally:

```bash
uv sync --group docs
uv run --group docs mkdocs serve
```

## License

Copyright 2026 Ralf Wanzenböck.

STOMS is licensed under the Apache License 2.0; see [LICENSE](LICENSE).

The structure viewer of `stoms serve` uses the
[Jmol element colours](https://jmol.sourceforge.net/jscolors/#Atoms) and the
covalent radii of B. Cordero et al., "Covalent radii revisited",
*Dalton Trans.* (2008) 2832–2838,
[doi:10.1039/B801115J](https://doi.org/10.1039/B801115J).
