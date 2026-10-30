import pytest


def test_postgres_schema_is_isolated(postgres_schema: tuple[str, str]) -> None:
    dsn, schema = postgres_schema

    psycopg = pytest.importorskip("psycopg")

    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(f'CREATE TABLE "{schema}".probe (id INTEGER)')
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s",
            (schema,),
        )
        assert cursor.fetchone() == ("probe",)
