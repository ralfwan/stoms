from __future__ import annotations

from .model import StructureContentConflict


class AtomsLedgerError(Exception):
    """Base exception for atomsledger."""


class RecordNotFoundError(AtomsLedgerError, KeyError):
    """Raised when a record ID does not exist."""


class AggregationNotFoundError(RecordNotFoundError):
    """Raised when an aggregation ID or external key does not exist."""


class DuplicateRecordError(AtomsLedgerError):
    """Raised when attempting to overwrite an immutable record."""


class AggregationConflictError(AtomsLedgerError):
    """Raised when an idempotency key is reused incompatibly."""


class AggregationValidationError(AtomsLedgerError, ValueError):
    """Raised when an aggregation request is invalid."""


class StoredQueryInUseError(AtomsLedgerError):
    """Raised when a stored query is referenced by aggregations."""

    def __init__(self, stored_query_id: str, aggregation_ids: tuple[str, ...]):
        self.stored_query_id = stored_query_id
        self.aggregation_ids = tuple(aggregation_ids)
        super().__init__(
            f"Stored query {stored_query_id} is referenced by aggregations: "
            + ", ".join(self.aggregation_ids)
        )


class IntegrityError(AtomsLedgerError):
    """Raised when a reference or content hash is inconsistent."""


class StrictSelectionError(IntegrityError):
    """Raised when a strict selection has zero or multiple matches."""

    def __init__(
        self,
        message: str,
        *,
        missing_structure_ids: tuple[str, ...] = (),
        ambiguous_structure_ids: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.missing_structure_ids = missing_structure_ids
        self.ambiguous_structure_ids = ambiguous_structure_ids


class EquivalentAtomsWarning(UserWarning):
    """Warn when structure IDs for equivalent atoms are reused or returned."""


class StructureContentConflictError(AtomsLedgerError):
    """Raised when atomic batch ingestion finds content conflicts.

    No item from the batch is inserted. ``conflicts`` identifies input items by
    position and includes all matching persisted content records. An empty
    ``matches`` tuple means the conflict is between different provenances in
    the same incoming batch.
    """

    def __init__(
        self,
        conflicts: tuple[StructureContentConflict, ...],
    ) -> None:
        self.conflicts = tuple(conflicts)
        details: list[str] = []
        for conflict in self.conflicts:
            if conflict.matches:
                matches = "; ".join(
                    f"{match.id} (hash={match.structure_content_hash}, "
                    f"provenance={match.provenance!r})"
                    for match in conflict.matches
                )
                details.append(
                    f"input index {conflict.input_index} matches "
                    f"existing records: {matches}"
                )
            else:
                details.append(
                    f"input index {conflict.input_index} conflicts with "
                    "another incoming item"
                )
        super().__init__(
            "Structure batch contains content conflicts: "
            + " | ".join(details)
        )


class StructureContentMismatchError(IntegrityError):
    """Raised when supplied atoms do not match a stored structure."""

    def __init__(
        self,
        structure_id: str,
        *,
        expected_structure_content_hash: str,
        actual_structure_content_hash: str,
    ) -> None:
        self.structure_id = structure_id
        self.expected_structure_content_hash = expected_structure_content_hash
        self.actual_structure_content_hash = actual_structure_content_hash
        super().__init__(
            f"Structure {structure_id} has content hash "
            f"{expected_structure_content_hash}, but supplied atoms have "
            f"{actual_structure_content_hash}"
        )


class SerializationError(AtomsLedgerError):
    """Raised when an ASE object or evaluation value cannot be serialized."""
