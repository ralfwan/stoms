from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from .model import StructureCatalogEntry, StructureQuery

if TYPE_CHECKING:
    from .backends.sqlite import SQLiteRepository


class SQLiteCatalog:
    """Read-only metadata catalog backed by an existing SQLite ledger."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self._repository = repository

    def search(
        self, query: StructureQuery | None = None
    ) -> tuple[StructureCatalogEntry, ...]:
        """Find structures and inspect evaluator availability without payloads."""
        return self._repository.catalog_structures(query)

    def iter_search(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureCatalogEntry]:
        """Stream catalog entries for broad discovery workloads."""
        return self._repository.iter_catalog_structures(query)
