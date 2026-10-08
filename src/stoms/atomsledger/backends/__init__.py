from .sqlite import SQLiteRepository

__all__ = ["SQLiteRepository"]

try:
    from .postgres import PostgresRepository  # noqa: F401
except ModuleNotFoundError as error:
    if error.name != "psycopg":
        raise
else:
    __all__.append("PostgresRepository")
