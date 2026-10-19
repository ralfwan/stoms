from stoms.atomsledger.backends.sqlite import SQLiteRepository
from stoms.atomsledger.repository import Repository


def test_sqlite_repository_implements_complete_contract() -> None:
    assert isinstance(SQLiteRepository(":memory:"), Repository)
