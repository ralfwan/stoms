import os
from collections.abc import Iterator
from uuid import uuid4

import pytest


@pytest.fixture
def postgres_schema() -> Iterator[tuple[str, str]]:
    """Provide a schema that is unique to, and removed after, one test."""
    dsn = os.environ.get("STOMS_POSTGRES_TEST_DSN")
    if dsn is None:
        pytest.skip("STOMS_POSTGRES_TEST_DSN is not configured")

    psycopg = pytest.importorskip(
        "psycopg", reason="install the postgres optional dependency"
    )
    schema = f"stoms_test_{uuid4().hex}"
    try:
        with (
            psycopg.connect(dsn, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SHOW server_version_num")
            version = int(cursor.fetchone()[0])
            if version < 160000:
                pytest.skip(
                    "PostgreSQL test service must be version 16 or newer"
                )
            cursor.execute(f'CREATE SCHEMA "{schema}"')
    except psycopg.OperationalError as error:
        pytest.skip(f"PostgreSQL test service is unavailable: {error}")

    try:
        yield dsn, schema
    finally:
        with (
            psycopg.connect(dsn, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = %s)",
                (schema,),
            )
            assert not cursor.fetchone()[0]
