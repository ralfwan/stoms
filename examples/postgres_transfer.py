"""Transfer between a PostgreSQL operational ledger and SQLite archives.

Install ``stoms[postgres]`` and set ``ATOMSLEDGER_POSTGRES_DSN``, for example:

    export ATOMSLEDGER_POSTGRES_DSN=postgresql://atomsledger:secret@localhost/materials
"""

import os

from stoms.atomsledger import AtomsLedger, PostgresRepository


def main() -> None:
    dsn = os.environ["ATOMSLEDGER_POSTGRES_DSN"]
    postgres = AtomsLedger(PostgresRepository(dsn, schema="atomsledger"))

    # Portable SQLite -> PostgreSQL. Repeating this call is safe because the
    # default conflict policy verifies existing immutable records.
    import_report = postgres.import_database("portable.atomsledger")
    print(import_report)

    # PostgreSQL -> a fresh portable SQLite file.
    export_report = postgres.export_database(
        "postgres-export.atomsledger",
        overwrite=True,
    )
    print(export_report)


if __name__ == "__main__":
    main()
