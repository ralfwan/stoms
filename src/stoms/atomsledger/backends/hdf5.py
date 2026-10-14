from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import h5py
import numpy as np
from ase import Atoms
from ase.constraints import dict2constraint
from filelock import FileLock

from ..exceptions import (
    DuplicateRecordError,
    IntegrityError,
    RecordNotFoundError,
    StructureContentConflictError,
)
from ..model import (
    EvaluationQuery,
    EvaluationRecord,
    QueryTemplateRecord,
    RecordId,
    StructureContentConflict,
    StructureContentMatch,
    StructureQuery,
    StructureRecord,
    TrajectoryFrame,
    TrajectoryRecord,
)
from ..serialization import (
    dataset_query_from_dict,
    dataset_query_to_dict,
    evaluation_content_hash,
    json_dumps,
    json_loads,
    method_content_hash,
    method_from_dict,
    method_to_dict,
    provenance_from_dict,
    provenance_to_dict,
    structure_content_hash,
    trajectory_frames_to_dict,
)

# Retained for future restoration; this adapter is not currently supported.
SCHEMA_NAME = "atomsledger"
SCHEMA_VERSION = 3
_UTF8 = h5py.string_dtype(encoding="utf-8")


def _text(group: h5py.Group, name: str, value: str) -> None:
    group.create_dataset(name, data=value, dtype=_UTF8)


def _read_text(group: h5py.Group, name: str) -> str:
    value = group[name][()]
    return value.decode() if isinstance(value, bytes) else str(value)


def _write_properties(
    group: h5py.Group, properties: Mapping[str, Any]
) -> None:
    for name, value in properties.items():
        item = group.create_group(quote(name, safe=""))
        item.attrs["name"] = name
        if isinstance(value, np.ndarray):
            item.attrs["encoding"] = "ndarray"
            kwargs = {"compression": "gzip"} if value.ndim > 0 else {}
            item.create_dataset("value", data=value, **kwargs)
        elif isinstance(value, np.generic | int | float | bool):
            item.attrs["encoding"] = "scalar"
            item.create_dataset("value", data=value)
        else:
            item.attrs["encoding"] = "json"
            _text(item, "value", json_dumps(value))


def _read_properties(group: h5py.Group) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for item in group.values():
        name = str(item.attrs["name"])
        encoding = str(item.attrs["encoding"])
        if encoding == "ndarray":
            values[name] = np.asarray(item["value"])
        elif encoding == "scalar":
            value = item["value"][()]
            values[name] = (
                value.item() if isinstance(value, np.generic) else value
            )
        else:
            values[name] = json_loads(_read_text(item, "value"))
    return values


_RecordWriter = tuple[str, Callable[[h5py.Group], None]]


class HDF5Repository:
    """Append-only HDF5 repository with serialized, atomic batch writes.

    A whole batch is prepared under ``/__pending__`` and only then moved into
    its final collection. Normal Python exceptions are rolled back. A process
    crash may leave pending groups, but never exposes them as committed records.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self.path) + ".lock")
        with self._locked_file("a") as handle:
            if "schema_name" in handle.attrs:
                if handle.attrs["schema_name"] != SCHEMA_NAME:
                    raise IntegrityError("Not an atomsledger HDF5 file")
                if int(handle.attrs["schema_version"]) != SCHEMA_VERSION:
                    raise IntegrityError(
                        "Unsupported atomsledger schema version"
                    )
            else:
                handle.attrs["schema_name"] = SCHEMA_NAME
                handle.attrs["schema_version"] = SCHEMA_VERSION
                handle.attrs["created_at"] = datetime.now(UTC).isoformat()
            for name in (
                "structures",
                "method_specs",
                "evaluations",
                "trajectories",
                "templates",
                "__pending__",
            ):
                handle.require_group(name)

    @contextmanager
    def _locked_file(self, mode: str) -> Iterator[h5py.File]:
        with self._lock, h5py.File(self.path, mode) as handle:
            yield handle

    def _write_records(
        self, collection: str, records: Sequence[_RecordWriter]
    ) -> None:
        if not records:
            return
        record_ids = [record_id for record_id, _ in records]
        if len(record_ids) != len(set(record_ids)):
            raise DuplicateRecordError("Duplicate record ID inside batch")

        with self._locked_file("a") as handle:
            self._write_records_locked(handle, collection, records)

    @staticmethod
    def _write_records_locked(
        handle: h5py.File,
        collection: str,
        records: Sequence[_RecordWriter],
    ) -> None:
        record_ids = [record_id for record_id, _ in records]
        for record_id in record_ids:
            if f"/{collection}/{record_id}" in handle:
                raise DuplicateRecordError(
                    f"Record already exists: {record_id}"
                )

        pending_paths: dict[str, str] = {}
        moved_paths: list[str] = []
        try:
            for record_id, writer in records:
                pending_path = f"/__pending__/{uuid4().hex}"
                pending = handle.create_group(pending_path)
                pending.attrs["target_collection"] = collection
                pending.attrs["target_id"] = record_id
                writer(pending)
                pending_paths[record_id] = pending_path
            handle.flush()

            for record_id in record_ids:
                pending_path = pending_paths[record_id]
                final_path = f"/{collection}/{record_id}"
                handle.move(pending_path, final_path)
                moved_paths.append(final_path)
            handle.flush()
        except Exception:
            for final_path in moved_paths:
                if final_path in handle:
                    del handle[final_path]
            for pending_path in pending_paths.values():
                if pending_path in handle:
                    del handle[pending_path]
            handle.flush()
            raise

    def _write_record(
        self,
        collection: str,
        record_id: str,
        writer: Callable[[h5py.Group], None],
    ) -> None:
        self._write_records(collection, [(record_id, writer)])

    @staticmethod
    def _get_group(
        handle: h5py.File, collection: str, record_id: str
    ) -> h5py.Group:
        path = f"/{collection}/{record_id}"
        if path not in handle:
            raise RecordNotFoundError(record_id)
        return handle[path]

    @staticmethod
    def _structure_writer(
        record: StructureRecord,
    ) -> Callable[[h5py.Group], None]:
        atoms = record.atoms

        def writer(group: h5py.Group) -> None:
            group.attrs["id"] = record.id
            group.attrs["created_at"] = record.created_at.isoformat()
            group.attrs["structure_content_hash"] = (
                record.structure_content_hash
            )
            group.create_dataset("cell", data=np.asarray(atoms.cell.array))
            group.create_dataset(
                "pbc", data=np.asarray(atoms.pbc, dtype=np.bool_)
            )
            arrays = group.create_group("arrays")
            for name, array in atoms.arrays.items():
                arrays.create_dataset(name, data=array, compression="gzip")
            _text(group, "info_json", json_dumps(atoms.info))
            constraints = [
                constraint.todict() for constraint in atoms.constraints
            ]
            _text(group, "constraints_json", json_dumps(constraints))
            _text(
                group,
                "provenance_json",
                json_dumps(provenance_to_dict(record.provenance)),
            )

        return writer

    def put_structure(self, record: StructureRecord) -> None:
        self.put_structures([record])

    def put_structures(self, records: Sequence[StructureRecord]) -> None:
        for record in records:
            if (
                structure_content_hash(record.atoms)
                != record.structure_content_hash
            ):
                raise IntegrityError(
                    f"Structure content hash does not match payload: {record.id}"
                )
        self._write_records(
            "structures",
            [
                (record.id, self._structure_writer(record))
                for record in records
            ],
        )

    def put_structures_deduplicating(
        self, records: Sequence[StructureRecord]
    ) -> list[StructureRecord]:
        return self.put_structures_content_aware(records)

    def put_structures_content_aware(
        self,
        records: Sequence[StructureRecord],
        *,
        allow_equivalent_atoms: bool = False,
    ) -> list[StructureRecord]:
        if not records:
            return []
        for record in records:
            if (
                structure_content_hash(record.atoms)
                != record.structure_content_hash
            ):
                raise IntegrityError(
                    f"Structure content hash does not match payload: {record.id}"
                )

        with self._locked_file("a") as handle:
            existing = sorted(
                (
                    self._read_structure(group)
                    for group in handle["structures"].values()
                ),
                key=lambda record: (record.created_at, record.id),
            )
            persisted: list[StructureRecord] = []
            conflicts: list[StructureContentConflict] = []
            known: dict[str, list[StructureRecord]] = {}
            planned: dict[str, list[StructureRecord]] = {}
            to_write: list[StructureRecord] = []
            for input_index, record in enumerate(records):
                candidates = known.setdefault(
                    record.structure_content_hash,
                    [
                        candidate
                        for candidate in existing
                        if candidate.structure_content_hash
                        == record.structure_content_hash
                    ],
                )
                match = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate.provenance == record.provenance
                    ),
                    None,
                )
                if match is not None:
                    persisted.append(match)
                    continue
                if candidates and not allow_equivalent_atoms:
                    conflicts.append(
                        StructureContentConflict(
                            input_index=input_index,
                            matches=tuple(
                                StructureContentMatch(
                                    id=candidate.id,
                                    structure_content_hash=(
                                        candidate.structure_content_hash
                                    ),
                                    provenance=candidate.provenance,
                                )
                                for candidate in candidates
                            ),
                        )
                    )
                    continue

                planned_candidates = planned.setdefault(
                    record.structure_content_hash, []
                )
                match = next(
                    (
                        candidate
                        for candidate in planned_candidates
                        if candidate.provenance == record.provenance
                    ),
                    None,
                )
                if match is not None:
                    persisted.append(match)
                    continue
                if planned_candidates and not allow_equivalent_atoms:
                    conflicts.append(
                        StructureContentConflict(input_index=input_index)
                    )
                    continue
                planned_candidates.append(record)
                to_write.append(record)
                persisted.append(record)
            if conflicts:
                raise StructureContentConflictError(tuple(conflicts))
            if to_write:
                self._write_records_locked(
                    handle,
                    "structures",
                    [
                        (record.id, self._structure_writer(record))
                        for record in to_write
                    ],
                )
        return persisted

    def _read_structure(self, group: h5py.Group) -> StructureRecord:
        arrays = {
            name: np.asarray(dataset)
            for name, dataset in group["arrays"].items()
        }
        numbers = arrays.pop("numbers")
        positions = arrays.pop("positions")
        atoms = Atoms(
            numbers=numbers,
            positions=positions,
            cell=np.asarray(group["cell"]),
            pbc=np.asarray(group["pbc"], dtype=bool),
            info=json_loads(_read_text(group, "info_json")),
        )
        for name, array in arrays.items():
            atoms.new_array(name, array)
        constraints = json_loads(_read_text(group, "constraints_json"))
        if constraints:
            atoms.set_constraint(
                [dict2constraint(item) for item in constraints]
            )
        record = StructureRecord(
            id=str(group.attrs["id"]),
            created_at=datetime.fromisoformat(str(group.attrs["created_at"])),
            structure_content_hash=str(group.attrs["structure_content_hash"]),
            provenance=provenance_from_dict(
                json_loads(_read_text(group, "provenance_json"))
            ),
            _atoms=atoms,
        )
        if (
            structure_content_hash(record.atoms)
            != record.structure_content_hash
        ):
            raise IntegrityError(
                f"Structure hash verification failed: {record.id}"
            )
        return record

    def get_structure(self, record_id: RecordId) -> StructureRecord:
        with self._locked_file("r") as handle:
            return self._read_structure(
                self._get_group(handle, "structures", record_id)
            )

    def iter_structures(
        self, query: StructureQuery | None = None
    ) -> Iterable[StructureRecord]:
        query = query or StructureQuery()
        with self._locked_file("r") as handle:
            records = [
                self._read_structure(group)
                for group in handle["structures"].values()
            ]
        records.sort(key=lambda record: (record.created_at, record.id))
        return (record for record in records if query.matches(record))

    @staticmethod
    def _evaluation_writer(
        record: EvaluationRecord,
    ) -> Callable[[h5py.Group], None]:
        def writer(group: h5py.Group) -> None:
            group.attrs["id"] = record.id
            group.attrs["structure_id"] = record.structure_id
            group.attrs["created_at"] = record.created_at.isoformat()
            group.attrs["content_hash"] = record.content_hash
            _text(group, "method_id", method_content_hash(record.method))
            _text(group, "units_json", json_dumps(record.units))
            _text(
                group,
                "provenance_json",
                json_dumps(provenance_to_dict(record.provenance)),
            )
            _write_properties(
                group.create_group("properties"), record.properties
            )

        return writer

    def put_evaluation(self, record: EvaluationRecord) -> None:
        self.put_evaluations([record])

    def put_evaluations(self, records: Sequence[EvaluationRecord]) -> None:
        for record in records:
            expected_hash = evaluation_content_hash(
                record.structure_id,
                record.method,
                record.properties,
                record.units,
            )
            if expected_hash != record.content_hash:
                raise IntegrityError(
                    f"Evaluation content hash does not match payload: {record.id}"
                )
        with self._locked_file("r") as handle:
            for record in records:
                self._get_group(handle, "structures", record.structure_id)
        self._ensure_method_specs(records)
        self._write_records(
            "evaluations",
            [
                (record.id, self._evaluation_writer(record))
                for record in records
            ],
        )

    def _ensure_method_specs(
        self, records: Sequence[EvaluationRecord]
    ) -> None:
        methods = {
            method_content_hash(record.method): record.method
            for record in records
        }
        with self._locked_file("a") as handle:
            collection = handle["method_specs"]
            for method_id, method in methods.items():
                if method_id in collection:
                    stored = method_from_dict(
                        json_loads(
                            _read_text(collection[method_id], "specification")
                        )
                    )
                    if stored != method:
                        raise IntegrityError(
                            f"Method specification hash collision: {method_id}"
                        )
                    continue
                group = collection.create_group(method_id)
                group.attrs["id"] = method_id
                _text(
                    group, "specification", json_dumps(method_to_dict(method))
                )

    def _read_evaluation(
        self, handle: h5py.File, group: h5py.Group
    ) -> EvaluationRecord:
        method_id = _read_text(group, "method_id")
        method_group = self._get_group(handle, "method_specs", method_id)
        record = EvaluationRecord(
            id=str(group.attrs["id"]),
            structure_id=str(group.attrs["structure_id"]),
            created_at=datetime.fromisoformat(str(group.attrs["created_at"])),
            content_hash=str(group.attrs["content_hash"]),
            method=method_from_dict(
                json_loads(_read_text(method_group, "specification"))
            ),
            properties=_read_properties(group["properties"]),
            units=json_loads(_read_text(group, "units_json")),
            provenance=provenance_from_dict(
                json_loads(_read_text(group, "provenance_json"))
            ),
        )
        actual_hash = evaluation_content_hash(
            record.structure_id, record.method, record.properties, record.units
        )
        if actual_hash != record.content_hash:
            raise IntegrityError(
                f"Evaluation hash verification failed: {record.id}"
            )
        return record

    def get_evaluation(self, record_id: RecordId) -> EvaluationRecord:
        with self._locked_file("r") as handle:
            return self._read_evaluation(
                handle, self._get_group(handle, "evaluations", record_id)
            )

    def iter_evaluations(
        self, query: EvaluationQuery | None = None
    ) -> Iterable[EvaluationRecord]:
        query = query or EvaluationQuery()
        with self._locked_file("r") as handle:
            records = [
                self._read_evaluation(handle, group)
                for group in handle["evaluations"].values()
            ]
        records.sort(key=lambda record: (record.created_at, record.id))
        return (record for record in records if query.matches(record))

    @staticmethod
    def _trajectory_writer(
        record: TrajectoryRecord,
    ) -> Callable[[h5py.Group], None]:
        def writer(group: h5py.Group) -> None:
            group.attrs["id"] = record.id
            group.attrs["created_at"] = record.created_at.isoformat()
            group.attrs["kind"] = record.kind
            _text(
                group,
                "frames_json",
                json_dumps(trajectory_frames_to_dict(record.frames)),
            )
            _text(
                group,
                "provenance_json",
                json_dumps(provenance_to_dict(record.provenance)),
            )

        return writer

    def put_trajectory(self, record: TrajectoryRecord) -> None:
        self.put_trajectories([record])

    def put_trajectories(self, records: Sequence[TrajectoryRecord]) -> None:
        with self._locked_file("r") as handle:
            for record in records:
                for frame in record.frames:
                    self._get_group(handle, "structures", frame.structure_id)
                    for evaluation_id in frame.evaluation_ids:
                        evaluation = self._read_evaluation(
                            handle,
                            self._get_group(
                                handle, "evaluations", evaluation_id
                            ),
                        )
                        if evaluation.structure_id != frame.structure_id:
                            raise IntegrityError(
                                f"Evaluation {evaluation_id} does not belong to "
                                f"structure {frame.structure_id}"
                            )
        self._write_records(
            "trajectories",
            [
                (record.id, self._trajectory_writer(record))
                for record in records
            ],
        )

    def _read_trajectory(self, group: h5py.Group) -> TrajectoryRecord:
        frames = tuple(
            TrajectoryFrame(
                structure_id=item["structure_id"],
                evaluation_ids=tuple(item.get("evaluation_ids", ())),
            )
            for item in json_loads(_read_text(group, "frames_json"))
        )
        return TrajectoryRecord(
            id=str(group.attrs["id"]),
            created_at=datetime.fromisoformat(str(group.attrs["created_at"])),
            kind=str(group.attrs["kind"]),
            frames=frames,
            provenance=provenance_from_dict(
                json_loads(_read_text(group, "provenance_json"))
            ),
        )

    def get_trajectory(self, record_id: RecordId) -> TrajectoryRecord:
        with self._locked_file("r") as handle:
            return self._read_trajectory(
                self._get_group(handle, "trajectories", record_id)
            )

    def iter_trajectories(self) -> Iterable[TrajectoryRecord]:
        with self._locked_file("r") as handle:
            records = [
                self._read_trajectory(group)
                for group in handle["trajectories"].values()
            ]
        records.sort(key=lambda record: (record.created_at, record.id))
        return iter(records)

    @staticmethod
    def _template_writer(
        record: QueryTemplateRecord,
    ) -> Callable[[h5py.Group], None]:
        def writer(group: h5py.Group) -> None:
            group.attrs["id"] = record.id
            group.attrs["name"] = record.name
            group.attrs["created_at"] = record.created_at.isoformat()
            _text(group, "description", record.description)
            _text(
                group,
                "query_json",
                json_dumps(dataset_query_to_dict(record.query)),
            )
            _text(
                group,
                "provenance_json",
                json_dumps(provenance_to_dict(record.provenance)),
            )

        return writer

    def put_template(self, record: QueryTemplateRecord) -> None:
        self.put_templates([record])

    def put_templates(self, records: Sequence[QueryTemplateRecord]) -> None:
        self._write_records(
            "templates",
            [(record.id, self._template_writer(record)) for record in records],
        )

    def _read_template(self, group: h5py.Group) -> QueryTemplateRecord:
        return QueryTemplateRecord(
            id=str(group.attrs["id"]),
            name=str(group.attrs["name"]),
            description=_read_text(group, "description"),
            query=dataset_query_from_dict(
                json_loads(_read_text(group, "query_json"))
            ),
            created_at=datetime.fromisoformat(str(group.attrs["created_at"])),
            provenance=provenance_from_dict(
                json_loads(_read_text(group, "provenance_json"))
            ),
        )

    def get_template(self, record_id: RecordId) -> QueryTemplateRecord:
        with self._locked_file("r") as handle:
            return self._read_template(
                self._get_group(handle, "templates", record_id)
            )

    def iter_templates(
        self, name: str | None = None
    ) -> Iterable[QueryTemplateRecord]:
        with self._locked_file("r") as handle:
            records = [
                self._read_template(group)
                for group in handle["templates"].values()
            ]
        records.sort(key=lambda record: (record.created_at, record.id))
        return (
            record for record in records if name is None or record.name == name
        )
