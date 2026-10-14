from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar, cast

from .exceptions import (
    DuplicateRecordError,
    IntegrityError,
    RecordNotFoundError,
)
from .model import (
    Aggregation,
    EvaluationRecord,
    StoredQuery,
    StructureRecord,
    TrajectoryRecord,
)
from .repository import Repository
from .serialization import record_fingerprint

ConflictPolicy = Literal["error", "skip", "verify"]
RecordT = TypeVar(
    "RecordT",
    StructureRecord,
    EvaluationRecord,
    TrajectoryRecord,
    StoredQuery,
    Aggregation,
)


@dataclass(frozen=True, slots=True)
class TransferReport:
    structures_written: int = 0
    structures_existing: int = 0
    evaluations_written: int = 0
    evaluations_existing: int = 0
    trajectories_written: int = 0
    trajectories_existing: int = 0
    stored_queries_written: int = 0
    stored_queries_existing: int = 0
    aggregations_written: int = 0
    aggregations_existing: int = 0

    @property
    def written(self) -> int:
        return (
            self.structures_written
            + self.evaluations_written
            + self.trajectories_written
            + self.stored_queries_written
            + self.aggregations_written
        )

    @property
    def existing(self) -> int:
        return (
            self.structures_existing
            + self.evaluations_existing
            + self.trajectories_existing
            + self.stored_queries_existing
            + self.aggregations_existing
        )


@dataclass(frozen=True, slots=True)
class _CollectionResult:
    written: int
    existing: int


def _chunks(
    records: Sequence[RecordT], size: int
) -> Iterable[Sequence[RecordT]]:
    for start in range(0, len(records), size):
        yield records[start : start + size]


def _transfer_collection(
    records: Iterable[RecordT],
    *,
    getter: Callable[[str], RecordT],
    batch_writer: Callable[[Sequence[RecordT]], None],
    conflict: ConflictPolicy,
    batch_size: int,
) -> _CollectionResult:
    missing: list[RecordT] = []
    existing = 0
    for record in records:
        try:
            current = getter(record.id)
        except RecordNotFoundError:
            missing.append(record)
            continue

        if conflict == "error":
            raise DuplicateRecordError(f"Record already exists: {record.id}")
        if conflict == "verify" and record_fingerprint(
            current
        ) != record_fingerprint(record):
            raise IntegrityError(
                f"Existing record {record.id} has different immutable content"
            )
        existing += 1

    for batch in _chunks(missing, batch_size):
        batch_writer(batch)
    return _CollectionResult(written=len(missing), existing=existing)


def _write_stored_queries(
    target: Repository, records: Sequence[StoredQuery]
) -> None:
    for record in records:
        target.put_stored_query(record)


def transfer_repository(
    source: Repository,
    target: Repository,
    *,
    conflict: ConflictPolicy = "verify",
    batch_size: int = 256,
    verify_after: bool = True,
) -> TransferReport:
    """Copy every record while preserving IDs, timestamps, and provenance.

    Records are copied in dependency order. With ``conflict='verify'`` an ID
    already present in the target is accepted only if its complete immutable
    fingerprint matches the source record. The target may contain additional
    records; transfer never deletes or rewrites them.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")

    source_structures = list(source.iter_structures())
    source_evaluations = list(source.iter_evaluations())
    source_tag_reader = cast(
        Callable[[str], frozenset[str]] | None,
        getattr(source, "get_post_ingestion_tags", None),
    )
    target_tag_writer = getattr(target, "add_tags_many", None)
    annotation_tags: dict[str, frozenset[str]] = {}
    if source_tag_reader is not None:
        for record in source_structures:
            tags = source_tag_reader(record.id)
            if tags:
                annotation_tags[record.id] = tags
        for evaluation in source_evaluations:
            tags = source_tag_reader(evaluation.id)
            if tags:
                annotation_tags[evaluation.id] = tags
        if annotation_tags and target_tag_writer is None:
            raise IntegrityError(
                "Target repository cannot preserve post-ingestion tags"
            )

    structures = _transfer_collection(
        source_structures,
        getter=target.get_structure,
        batch_writer=target.put_structures,
        conflict=conflict,
        batch_size=batch_size,
    )
    evaluations = _transfer_collection(
        source_evaluations,
        getter=target.get_evaluation,
        batch_writer=target.put_evaluations,
        conflict=conflict,
        batch_size=batch_size,
    )
    trajectories = _transfer_collection(
        source.iter_trajectories(),
        getter=target.get_trajectory,
        batch_writer=target.put_trajectories,
        conflict=conflict,
        batch_size=batch_size,
    )
    stored_queries = _transfer_collection(
        source.iter_stored_queries(),
        getter=target.get_stored_query,
        batch_writer=lambda records: _write_stored_queries(target, records),
        conflict=conflict,
        batch_size=batch_size,
    )

    aggregations = _CollectionResult(0, 0)
    source_aggregations = getattr(source, "iter_aggregations", None)
    target_aggregation_getter = getattr(target, "get_aggregation", None)
    target_aggregation_writer = getattr(target, "put_aggregations", None)
    if source_aggregations is not None:
        source_aggregation_records = list(source_aggregations())
        if source_aggregation_records and (
            target_aggregation_getter is None
            or target_aggregation_writer is None
        ):
            raise IntegrityError(
                "Target repository cannot preserve aggregations"
            )
        if (
            target_aggregation_getter is not None
            and target_aggregation_writer is not None
        ):
            aggregations = _transfer_collection(
                source_aggregation_records,
                getter=target_aggregation_getter,
                batch_writer=target_aggregation_writer,
                conflict=conflict,
                batch_size=batch_size,
            )

    if annotation_tags:
        assert target_tag_writer is not None
        target_tag_writer(annotation_tags)

    if verify_after:
        verify_repository_subset(source, target)

    return TransferReport(
        structures_written=structures.written,
        structures_existing=structures.existing,
        evaluations_written=evaluations.written,
        evaluations_existing=evaluations.existing,
        trajectories_written=trajectories.written,
        trajectories_existing=trajectories.existing,
        stored_queries_written=stored_queries.written,
        stored_queries_existing=stored_queries.existing,
        aggregations_written=aggregations.written,
        aggregations_existing=aggregations.existing,
    )


def verify_repository_subset(source: Repository, target: Repository) -> None:
    """Verify that every source record exists identically in the target."""
    collections = (
        (source.iter_structures(), target.get_structure),
        (source.iter_evaluations(), target.get_evaluation),
        (source.iter_trajectories(), target.get_trajectory),
        (source.iter_stored_queries(), target.get_stored_query),
    )
    for records, getter in collections:
        for record in records:
            try:
                target_record = getter(record.id)
            except RecordNotFoundError as error:
                raise IntegrityError(
                    f"Transferred record is missing from target: {record.id}"
                ) from error
            if record_fingerprint(record) != record_fingerprint(target_record):
                raise IntegrityError(
                    f"Transferred record differs in target: {record.id}"
                )
    source_aggregations = getattr(source, "iter_aggregations", None)
    target_aggregation_getter = getattr(target, "get_aggregation", None)
    if (
        source_aggregations is not None
        and target_aggregation_getter is not None
    ):
        for record in source_aggregations():
            try:
                target_record = target_aggregation_getter(record.id)
            except RecordNotFoundError as error:
                raise IntegrityError(
                    f"Transferred aggregation is missing from target: {record.id}"
                ) from error
            if record_fingerprint(record) != record_fingerprint(target_record):
                raise IntegrityError(
                    f"Transferred aggregation differs in target: {record.id}"
                )
    for record in source.iter_stored_queries():
        try:
            target_record = target.get_stored_query(record.id)
        except RecordNotFoundError as error:
            raise IntegrityError(
                f"Transferred record is missing from target: {record.id}"
            ) from error
        if record_fingerprint(record) != record_fingerprint(target_record):
            raise IntegrityError(
                f"Transferred record differs in target: {record.id}"
            )


def _export_hdf5(
    source: Repository,
    destination: str | Path,
    *,
    overwrite: bool = False,
    batch_size: int = 256,
) -> TransferReport:
    """Retained HDF5 export implementation for future reactivation."""
    path = Path(destination)
    if path.exists():
        if not overwrite:
            raise FileExistsError(path)
        path.unlink()
    lock_path = Path(str(path) + ".lock")
    if lock_path.exists():
        lock_path.unlink()
    from .backends.hdf5 import HDF5Repository

    return transfer_repository(
        source,
        HDF5Repository(path),  # type: ignore[arg-type]
        conflict="error",
        batch_size=batch_size,
        verify_after=True,
    )


def _import_hdf5(
    source: str | Path,
    target: Repository,
    *,
    conflict: ConflictPolicy = "verify",
    batch_size: int = 256,
) -> TransferReport:
    """Retained HDF5 import implementation for future reactivation."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    from .backends.hdf5 import HDF5Repository

    return transfer_repository(
        HDF5Repository(path),  # type: ignore[arg-type]
        target,
        conflict=conflict,
        batch_size=batch_size,
        verify_after=True,
    )


def export_sqlite(
    source: Repository,
    destination: str | Path,
    *,
    overwrite: bool = False,
    batch_size: int = 256,
) -> TransferReport:
    """Create a portable, indexed SQLite export from any backend."""
    from .backends.sqlite import SQLiteRepository

    path = Path(destination)
    if path.exists():
        if not overwrite:
            raise FileExistsError(path)
        path.unlink()
    for suffix in ("-wal", "-shm"):  # stale WAL sidecars must not survive
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    return transfer_repository(
        source,
        SQLiteRepository(path),
        conflict="error",
        batch_size=batch_size,
        verify_after=True,
    )


def import_sqlite(
    source: str | Path,
    target: Repository,
    *,
    conflict: ConflictPolicy = "verify",
    batch_size: int = 256,
) -> TransferReport:
    """Import a complete SQLite repository into another backend."""
    from .backends.sqlite import SQLiteRepository

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    return transfer_repository(
        SQLiteRepository(path, initialize=False),
        target,
        conflict=conflict,
        batch_size=batch_size,
        verify_after=True,
    )
