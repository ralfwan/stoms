# PostgreSQL operational ledger

Use PostgreSQL when a project needs a shared operational ledger. SQLite remains
the portable archive format.

## Install and connect

In the project that uses STOMS, install the PostgreSQL extra:

```bash
uv add "stoms[postgres]"
```

Construct the ledger with the database DSN and a schema owned only by STOMS:

```python
import os

from stoms.atomsledger import AtomsLedger, PostgresRepository

ledger = AtomsLedger(
    PostgresRepository(
        os.environ["PROJECT_LEDGER_DSN"],
        schema="project_ledger",
    )
)
```

`PostgresRepository` creates and validates its tables in that schema. Keep the
DSN in the project environment, not in source control. Do not share the schema
with unrelated applications.

Use this `ledger` exactly like a SQLite ledger for ingestion, queries, tags,
stored queries, aggregations, and exports.

## Synchronize SQLite and PostgreSQL

Transfers are additive: they copy records missing from the target and verify
the fingerprint of records already present. They preserve IDs, provenance,
post-ingestion tags, trajectories, stored queries, and aggregations. Transfers
never delete records from either side.

Import a portable SQLite archive into PostgreSQL:

```python
from stoms.atomsledger import import_sqlite

report = import_sqlite("project.atomsledger", ledger.repository)
print(report)
```

Export the PostgreSQL ledger as a fresh portable SQLite archive:

```python
report = ledger.export_database("project-backup.atomsledger", overwrite=True)
print(report)
```

For an existing SQLite target, use `transfer_repository` directly:

```python
from stoms.atomsledger import SQLiteRepository, transfer_repository

report = transfer_repository(
    ledger.repository,
    SQLiteRepository("project-copy.atomsledger"),
)
print(report)
```

The default conflict policy is `"verify"`: a matching ID with different
immutable content raises `IntegrityError`. Use `conflict="error"` to reject
every pre-existing record, or `conflict="skip"` only when intentional.

## Concurrency

PostgreSQL, not STOMS, provides the base guarantees for multiple simultaneous
users: transactional isolation, row-level locking, and connection
authentication/authorization through normal PostgreSQL roles and `pg_hba.conf`
rules. STOMS adds no server, authorization layer, or connection pool of its
own; provision and secure the database the way you would for any other
PostgreSQL-backed application.

On top of that, `PostgresRepository` guarantees ledger-specific correctness
under concurrent STOMS writers: content-aware structure ingestion is
serialized with advisory locks so concurrent inserts of the same structure
content cannot create duplicate records, batch writes are atomic and roll back
together on failure, and aggregation creation with a repeated `external_key`
is idempotent under concurrent retries rather than racing into duplicate or
conflicting aggregations.
