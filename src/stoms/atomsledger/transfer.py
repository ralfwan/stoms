from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeVar, cast

from .exceptions import (
    AggregationValidationError,
    DuplicateRecordError,
    IntegrityError,
    LedgerOverwriteError,
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

    path = _prepare_sqlite_destination(
        destination, overwrite=overwrite, source=source
    )
    return transfer_repository(
        source,
        SQLiteRepository(path),
        conflict="error",
        batch_size=batch_size,
        verify_after=True,
    )


def export_aggregation_sqlite(
    source: Repository,
    aggregation_id: str,
    destination: str | Path,
    *,
    overwrite: bool = False,
    batch_size: int = 256,
) -> TransferReport:
    """Export one aggregation into a new SQLite ledger, preserving IDs.

    The new ledger holds the aggregation, its member structures, and the one
    evaluation paired with each member, with IDs, timestamps, provenance, and
    post-ingestion tags unchanged. A source stored query is copied as a
    definition. An aggregation that supersedes another is rejected because
    its predecessor would be missing.
    """
    from .backends.sqlite import SQLiteRepository

    subset = _AggregationSubset(source, aggregation_id)
    path = _prepare_sqlite_destination(
        destination, overwrite=overwrite, source=source
    )
    return transfer_repository(
        subset,  # type: ignore[arg-type]
        SQLiteRepository(path),
        conflict="error",
        batch_size=batch_size,
        verify_after=True,
    )


# The first 16 bytes of every SQLite database file.
SQLITE_HEADER = b"SQLite format 3\x00"


def is_sqlite_file(path: Path) -> bool:
    """Whether ``path`` is a SQLite database file (such as a ledger)."""
    try:
        with path.open("rb") as stream:
            return stream.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def refuse_source_destination(source: Repository, destination: Path) -> None:
    """Refuse a destination that is the source ledger's own file, also
    through a symbolic or hard link; overwriting it would destroy the
    ledger being read. Repositories without a file (PostgreSQL) pass."""
    path = getattr(source, "path", None)
    if path is None:
        return
    with contextlib.suppress(OSError):  # either file missing
        if os.path.samefile(path, destination):
            raise LedgerOverwriteError(
                f"destination is the source ledger ({destination}); "
                "choose another file"
            )


def _prepare_sqlite_destination(
    destination: str | Path, *, overwrite: bool, source: Repository
) -> Path:
    path = Path(destination)
    refuse_source_destination(source, path)
    if path.exists():
        if not overwrite:
            raise FileExistsError(path)
        path.unlink()
    for suffix in ("-wal", "-shm"):  # stale WAL sidecars must not survive
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    return path


class _AggregationSubset:
    """Read-only transfer source restricted to one aggregation."""

    def __init__(self, source: Repository, aggregation_id: str) -> None:
        aggregation = source.get_aggregation(aggregation_id)
        if aggregation.supersedes_id is not None:
            raise AggregationValidationError(
                f"Aggregation {aggregation_id} supersedes "
                f"{aggregation.supersedes_id} and cannot be exported alone"
            )
        self._source = source
        self._aggregation = aggregation
        members = aggregation.members
        self._structure_ids = tuple(
            dict.fromkeys(member.structure_id for member in members)
        )
        self._evaluation_ids = tuple(
            dict.fromkeys(
                member.evaluation_id
                for member in members
                if member.evaluation_id is not None
            )
        )
        query_id = aggregation.source_stored_query_id
        self._stored_queries = (
            (source.get_stored_query(query_id),) if query_id else ()
        )

    def iter_structures(self) -> Iterable[StructureRecord]:
        return (
            self._source.get_structure(record_id)
            for record_id in self._structure_ids
        )

    def iter_evaluations(self) -> Iterable[EvaluationRecord]:
        return (
            self._source.get_evaluation(record_id)
            for record_id in self._evaluation_ids
        )

    def iter_trajectories(self) -> Iterable[TrajectoryRecord]:
        return ()

    def iter_stored_queries(self) -> Iterable[StoredQuery]:
        return self._stored_queries

    def iter_aggregations(self) -> Iterable[Aggregation]:
        return (self._aggregation,)

    def get_post_ingestion_tags(self, record_id: str) -> frozenset[str]:
        reader = getattr(self._source, "get_post_ingestion_tags", None)
        return reader(record_id) if reader is not None else frozenset()


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
