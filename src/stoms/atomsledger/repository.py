from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol, runtime_checkable

from .model import (
    Aggregation,
    AggregationSummary,
    EvaluationQuery,
    EvaluationRecord,
    RecordId,
    StoredQuery,
    StoredQuerySummary,
    StructureQuery,
    StructureRecord,
    TrajectoryRecord,
)


@runtime_checkable
class Repository(Protocol):
    """Complete storage boundary implemented by every supported backend.

    Backends must provide every capability used by ``AtomsLedger`` and transfer,
    including post-ingestion tags and aggregations. Optional method lookups are
    deliberately not part of this boundary.

    The retained HDF5 module is stale and does not implement the current model.
    It is not a supported protocol implementation.
    """

    def validate(self) -> None: ...

    def put_structure(self, record: StructureRecord) -> None: ...

    def put_structures(self, records: Sequence[StructureRecord]) -> None: ...

    def put_structures_deduplicating(
        self, records: Sequence[StructureRecord]
    ) -> Sequence[StructureRecord]: ...

    def put_structures_content_aware(
        self,
        records: Sequence[StructureRecord],
        *,
        allow_equivalent_atoms: bool = False,
    ) -> Sequence[StructureRecord]: ...

    def get_structure(self, record_id: RecordId) -> StructureRecord: ...

    def iter_structures(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureRecord]: ...

    def put_evaluation(self, record: EvaluationRecord) -> None: ...

    def put_evaluations(self, records: Sequence[EvaluationRecord]) -> None: ...

    def get_evaluation(self, record_id: RecordId) -> EvaluationRecord: ...

    def iter_evaluations(
        self, query: EvaluationQuery | None = None
    ) -> Iterable[EvaluationRecord]: ...

    def list_method_identifiers(self) -> Iterable[str]: ...

    def get_post_ingestion_tags(
        self, record_id: RecordId
    ) -> frozenset[str]: ...

    def add_tags_many(
        self, records: Mapping[RecordId, Iterable[str]]
    ) -> dict[RecordId, frozenset[str]]: ...

    def get_tags(self, record_id: RecordId) -> frozenset[str]: ...

    def put_trajectory(self, record: TrajectoryRecord) -> None: ...

    def put_trajectories(
        self, records: Sequence[TrajectoryRecord]
    ) -> None: ...

    def get_trajectory(self, record_id: RecordId) -> TrajectoryRecord: ...

    def iter_trajectories(self) -> Iterable[TrajectoryRecord]: ...

    def put_stored_query(self, record: StoredQuery) -> None: ...
    def get_stored_query(self, record_id: RecordId) -> StoredQuery: ...
    def iter_stored_queries(self) -> Iterable[StoredQuery]: ...
    def iter_stored_query_summaries(
        self,
    ) -> Iterable[StoredQuerySummary]: ...
    def hide_stored_query(self, record_id: RecordId) -> None: ...
    def delete_stored_query(
        self, record_id: RecordId, *, force: bool = False
    ) -> None: ...

    def put_aggregation(self, record: Aggregation) -> Aggregation: ...
    def put_aggregations(self, records: Sequence[Aggregation]) -> None: ...
    def get_aggregation(
        self, aggregation_id: str, *, include_members: bool = True
    ) -> Aggregation: ...
    def get_aggregation_by_external_key(
        self, external_key: str, *, include_members: bool = True
    ) -> Aggregation: ...
    def iter_aggregations(self) -> Iterable[Aggregation]: ...
    def iter_aggregation_summaries(
        self,
        *,
        name: str | None = None,
        source_stored_query_id: str | None = None,
    ) -> Iterable[AggregationSummary]: ...
