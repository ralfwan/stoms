# PostgreSQL operational ledger

Use PostgreSQL when a project needs a shared operational ledger. SQLite remains
the portable archive format.

## When to choose PostgreSQL

Choose the backend by how the ledger is accessed, not by its size. A SQLite
ledger stays small and fast well beyond typical project sizes: 5,000
structures of 108 atoms with three evaluations each (energy, forces, one
scalar) take about 100 MB, roughly 20 kB per structure including its
evaluations.

| Access pattern | Backend |
| --- | --- |
| One user or ingest process, ledger on a local disk | SQLite |
| Several processes or agents on one machine, ledger on a local disk, occasional batch writes | SQLite |
| Processes on different machines or cluster nodes, or a ledger file on NFS, Lustre, or another network filesystem | PostgreSQL |
| Frequent or long write transactions, writers failing with `database is locked` | PostgreSQL |
| Access control or remote access for several users | PostgreSQL |

SQLite allows one writer at a time. Content-aware structure ingestion takes
the write lock before checking for duplicates, so concurrent writers on one
machine cannot create duplicate structures; they queue instead, each waiting up
to `SQLiteRepository(timeout=30.0)` seconds before failing with `database is
locked`. In the default `DELETE` journal mode, a commit also waits for active
readers, so long streaming queries can delay writers. For several concurrent
local processes, open the ledger in WAL mode, where readers and the writer do
not block each other:

```python
from stoms.atomsledger import AtomsLedger, SQLiteRepository

ledger = AtomsLedger(
    SQLiteRepository("project.atomsledger", journal_mode="WAL")
)
```

Every process sharing the file must use the same journal mode, because each
connection sets it. In WAL mode, call `ledger.repository.checkpoint()` from
time to time if long-lived readers keep the `-wal` file growing.

SQLite file locking, and WAL in particular, is not reliable on network
filesystems, so processes on several machines or nodes must not share one
SQLite file. Use PostgreSQL there. There is no need to switch early: migration
with `import_sqlite` (below) preserves IDs, provenance, tags, and aggregations.
Keep exporting SQLite snapshots from PostgreSQL for archiving and for browsing
with `stoms serve`.

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
