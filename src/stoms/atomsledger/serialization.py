from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

import numpy as np
from ase import Atoms
from ase.constraints import dict2constraint

from .exceptions import SerializationError
from .model import (
    Aggregation,
    DatasetQuery,
    EvaluationQuery,
    EvaluatorSelector,
    MethodSpec,
    Provenance,
    StoredQuery,
    StructureQuery,
    StructureRecord,
    StructureSourceSpec,
    TrajectoryFrame,
    TrajectoryRecord,
)


def to_plain(value: Any) -> Any:
    if isinstance(value, MappingProxyType | Mapping):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple | list):
        return [to_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return to_plain(asdict(value))
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise SerializationError(
        f"Value is not JSON serializable: {type(value)!r}"
    )


def json_dumps(value: Any) -> str:
    return json.dumps(
        to_plain(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def json_loads(value: str) -> Any:
    return json.loads(value)


def provenance_to_dict(value: Provenance) -> dict[str, Any]:
    return {
        "created_by": value.created_by,
        "purpose": value.purpose,
        "tags": list(value.tags),
        "notes": value.notes,
        "metadata": to_plain(value.metadata),
    }


def provenance_from_dict(value: Mapping[str, Any]) -> Provenance:
    return Provenance(
        created_by=value["created_by"],
        purpose=value["purpose"],
        tags=tuple(value.get("tags", ())),
        notes=value.get("notes"),
        metadata=value.get("metadata", {}),
    )


def structure_source_to_dict(value: StructureSourceSpec) -> dict[str, Any]:
    return {
        "kind": value.kind,
        "name": value.name,
        "version": value.version,
        "tool": value.tool,
        "model_identifier": value.model_identifier,
        "parameters": to_plain(value.parameters),
    }


def structure_source_from_dict(
    value: Mapping[str, Any],
) -> StructureSourceSpec:
    return StructureSourceSpec(
        kind=value["kind"],
        name=value["name"],
        version=value.get("version"),
        tool=value.get("tool"),
        model_identifier=value.get("model_identifier"),
        parameters=value.get("parameters", {}),
    )


def structure_source_content_hash(source: StructureSourceSpec) -> str:
    """Return the stable identity used for shared source storage."""
    return hashlib.sha256(
        json_dumps(structure_source_to_dict(source)).encode()
    ).hexdigest()


def method_to_dict(value: MethodSpec) -> dict[str, Any]:
    return {
        "method_identifier": value.method_identifier,
        "family": value.family,
        "name": value.name,
        "version": value.version,
        "code": value.code,
        "parameters": to_plain(value.parameters),
    }


def method_from_dict(value: Mapping[str, Any]) -> MethodSpec:
    return MethodSpec(
        method_identifier=value["method_identifier"],
        family=value["family"],
        name=value["name"],
        version=value.get("version"),
        code=value.get("code"),
        parameters=value.get("parameters", {}),
    )


def method_content_hash(method: MethodSpec) -> str:
    """Return the stable identity used for shared method storage."""
    return hashlib.sha256(
        json_dumps(method_to_dict(method)).encode()
    ).hexdigest()


def atoms_constraints_to_plain(atoms: Atoms) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    for constraint in atoms.constraints:
        if not hasattr(constraint, "todict"):
            raise SerializationError(
                f"Constraint {type(constraint).__name__} has no todict() method"
            )
        constraints.append(to_plain(constraint.todict()))
    return constraints


def structure_content_hash(atoms: Atoms) -> str:
    digest = hashlib.sha256()
    for name in sorted(atoms.arrays):
        array = np.ascontiguousarray(atoms.arrays[name])
        digest.update(name.encode())
        digest.update(array.dtype.str.encode())
        digest.update(str(array.shape).encode())
        digest.update(array.tobytes())
    cell = np.ascontiguousarray(atoms.cell.array, dtype=np.float64)
    pbc = np.ascontiguousarray(atoms.pbc, dtype=np.bool_)
    digest.update(cell.tobytes())
    digest.update(pbc.tobytes())
    digest.update(json_dumps(atoms.info).encode())
    digest.update(json_dumps(atoms_constraints_to_plain(atoms)).encode())
    return digest.hexdigest()


def provenance_content_hash(provenance: Provenance) -> str:
    """Hash immutable ingestion provenance, excluding record annotations."""
    return hashlib.sha256(
        json_dumps(provenance_to_dict(provenance)).encode()
    ).hexdigest()


def _hash_value(digest: Any, name: str, value: Any) -> None:
    digest.update(name.encode())
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        digest.update(b"ndarray")
        digest.update(array.dtype.str.encode())
        digest.update(str(array.shape).encode())
        digest.update(array.tobytes())
    else:
        digest.update(b"json")
        digest.update(json_dumps(value).encode())


def evaluation_content_hash(
    structure_id: str,
    method: MethodSpec,
    properties: Mapping[str, Any],
    units: Mapping[str, str],
) -> str:
    digest = hashlib.sha256()
    digest.update(structure_id.encode())
    digest.update(json_dumps(method_to_dict(method)).encode())
    for name in sorted(properties):
        _hash_value(digest, name, properties[name])
    digest.update(json_dumps(units).encode())
    return digest.hexdigest()


def aggregation_membership_hash(
    members: Sequence[tuple[str, str | None]],
) -> str:
    """Hash an aggregation's ordered structure/evaluation pairs canonically."""
    canonical = "\n".join(
        [
            "aggregation-members-v1",
            *(
                f"{ordinal}:{structure_id}:{evaluation_id or ''}"
                for ordinal, (structure_id, evaluation_id) in enumerate(
                    members
                )
            ),
        ]
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def structure_query_to_dict(query: StructureQuery) -> dict[str, Any]:
    return to_plain(query)


def structure_query_from_dict(value: Mapping[str, Any]) -> StructureQuery:
    return StructureQuery(
        ids=tuple(value["ids"]) if value.get("ids") is not None else None,
        structure_content_hash=value.get("structure_content_hash"),
        formula=value.get("formula"),
        tags_all=tuple(value.get("tags_all", ())),
        tags_any=tuple(value.get("tags_any", ())),
        tags_none=tuple(value.get("tags_none", ())),
        purpose_contains=value.get("purpose_contains"),
        created_after=(
            datetime.fromisoformat(value["created_after"])
            if value.get("created_after")
            else None
        ),
        created_before=(
            datetime.fromisoformat(value["created_before"])
            if value.get("created_before")
            else None
        ),
    )


def evaluation_query_to_dict(query: EvaluationQuery) -> dict[str, Any]:
    return to_plain(query)


def evaluation_query_from_dict(value: Mapping[str, Any]) -> EvaluationQuery:
    return EvaluationQuery(
        ids=tuple(value["ids"]) if value.get("ids") is not None else None,
        structure_ids=(
            tuple(value["structure_ids"])
            if value.get("structure_ids") is not None
            else None
        ),
        method_families=tuple(value.get("method_families", ())),
        method_names=tuple(value.get("method_names", ())),
        method_versions=tuple(value.get("method_versions", ())),
        method_codes=tuple(value.get("method_codes", ())),
        method_identifiers=tuple(value.get("method_identifiers", ())),
        properties_all=tuple(value.get("properties_all", ())),
        tags_all=tuple(value.get("tags_all", ())),
        tags_any=tuple(value.get("tags_any", ())),
        tags_none=tuple(value.get("tags_none", ())),
        created_after=(
            datetime.fromisoformat(value["created_after"])
            if value.get("created_after")
            else None
        ),
        created_before=(
            datetime.fromisoformat(value["created_before"])
            if value.get("created_before")
            else None
        ),
    )


def evaluator_selector_to_dict(value: EvaluatorSelector) -> dict[str, Any]:
    return {
        "method": method_to_dict(value.method),
        "exact_match": value.exact_match,
    }


def evaluator_selector_from_dict(
    value: Mapping[str, Any],
) -> EvaluatorSelector:
    return EvaluatorSelector(
        method=method_from_dict(value["method"]),
        exact_match=bool(value.get("exact_match", False)),
    )


def dataset_query_to_dict(query: DatasetQuery) -> dict[str, Any]:
    return {
        "structures": structure_query_to_dict(query.structures),
        "evaluations": (
            evaluation_query_to_dict(query.evaluations)
            if query.evaluations is not None
            else None
        ),
        "require_evaluation": query.require_evaluation,
    }


def dataset_query_from_dict(value: Mapping[str, Any]) -> DatasetQuery:
    evaluation = value.get("evaluations")
    return DatasetQuery(
        structures=structure_query_from_dict(value.get("structures", {})),
        evaluations=(
            evaluation_query_from_dict(evaluation)
            if evaluation is not None
            else None
        ),
        require_evaluation=bool(value.get("require_evaluation", False)),
    )


def trajectory_frames_to_dict(
    frames: tuple[TrajectoryFrame, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "structure_id": frame.structure_id,
            "evaluation_ids": list(frame.evaluation_ids),
        }
        for frame in frames
    ]


def _npz_dumps(arrays: Mapping[str, np.ndarray]) -> bytes:
    buffer = io.BytesIO()
    array_values: dict[str, Any] = dict(arrays)
    np.savez_compressed(buffer, **array_values)
    return buffer.getvalue()


def _npz_loads(payload: bytes) -> dict[str, np.ndarray]:
    with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        return {
            name: np.array(archive[name], copy=True) for name in archive.files
        }


def atoms_to_binary_payload(atoms: Atoms) -> tuple[dict[str, Any], bytes]:
    """Encode ASE metadata as JSON-compatible data and arrays as an NPZ blob."""
    arrays: dict[str, np.ndarray] = {
        f"array_{index}": np.asarray(array)
        for index, (_, array) in enumerate(sorted(atoms.arrays.items()))
    }
    array_names = [name for name, _ in sorted(atoms.arrays.items())]
    arrays["cell"] = np.asarray(atoms.cell.array)
    arrays["pbc"] = np.asarray(atoms.pbc, dtype=np.bool_)
    metadata = {
        "array_names": array_names,
        "info": to_plain(atoms.info),
        "constraints": atoms_constraints_to_plain(atoms),
    }
    return metadata, _npz_dumps(arrays)


def atoms_from_binary_payload(
    metadata: Mapping[str, Any], payload: bytes
) -> Atoms:
    arrays = _npz_loads(payload)
    named_arrays = {
        name: arrays[f"array_{index}"]
        for index, name in enumerate(metadata["array_names"])
    }
    try:
        numbers = named_arrays.pop("numbers")
        positions = named_arrays.pop("positions")
    except KeyError as error:
        raise SerializationError(
            "Atoms payload lacks numbers or positions"
        ) from error
    atoms = Atoms(
        numbers=numbers,
        positions=positions,
        cell=arrays["cell"],
        pbc=np.asarray(arrays["pbc"], dtype=bool),
        info=dict(metadata.get("info", {})),
    )
    for name, array in named_arrays.items():
        atoms.new_array(name, array)
    constraints = metadata.get("constraints", ())
    if constraints:
        atoms.set_constraint([dict2constraint(item) for item in constraints])
    return atoms


def properties_to_binary_payload(
    properties: Mapping[str, Any],
) -> tuple[dict[str, Any], bytes]:
    """Encode supported evaluation values into metadata and a NumPy payload."""
    metadata: dict[str, Any] = {}
    arrays: dict[str, np.ndarray] = {}
    for index, (name, value) in enumerate(sorted(properties.items())):
        if isinstance(value, np.ndarray):
            key = f"value_{index}"
            arrays[key] = np.asarray(value)
            metadata[name] = {"encoding": "ndarray", "key": key}
        else:
            metadata[name] = {"encoding": "json", "value": to_plain(value)}
    return metadata, _npz_dumps(arrays)


def properties_from_binary_payload(
    metadata: Mapping[str, Any], payload: bytes
) -> dict[str, Any]:
    arrays = _npz_loads(payload)
    properties: dict[str, Any] = {}
    for name, descriptor in metadata.items():
        if descriptor["encoding"] == "ndarray":
            properties[name] = arrays[descriptor["key"]]
        else:
            properties[name] = descriptor.get("value")
    return properties


def record_fingerprint(record: Any) -> str:
    """Fingerprint persisted immutable fields, including provenance metadata.

    This uses the same serialization as SQLite persistence. Consequently, an
    evaluation's ``MethodSpec.model_id`` is not represented by the fingerprint.
    """
    if isinstance(record, StructureRecord):
        payload = {
            "type": "structure",
            "id": record.id,
            "created_at": record.created_at,
            "structure_content_hash": record.structure_content_hash,
            "source_spec": structure_source_to_dict(record.source_spec),
            "provenance": provenance_to_dict(record.provenance),
        }
    elif hasattr(record, "method") and hasattr(record, "structure_id"):
        payload = {
            "type": "evaluation",
            "id": record.id,
            "structure_id": record.structure_id,
            "created_at": record.created_at,
            "content_hash": record.content_hash,
            "method": method_to_dict(record.method),
            "units": to_plain(record.units),
            "provenance": provenance_to_dict(record.provenance),
        }
    elif isinstance(record, TrajectoryRecord):
        payload = {
            "type": "trajectory",
            "id": record.id,
            "created_at": record.created_at,
            "kind": record.kind,
            "frames": trajectory_frames_to_dict(record.frames),
            "provenance": provenance_to_dict(record.provenance),
        }
    elif isinstance(record, StoredQuery):
        payload = {
            "type": "stored_query",
            "id": record.id,
            "label": record.label,
            "description": record.description,
            "query": dataset_query_to_dict(record.query),
            "created_at": record.created_at,
            "hidden_at": record.hidden_at,
            "provenance": provenance_to_dict(record.provenance),
        }
    elif isinstance(record, Aggregation):
        payload = {
            "type": "aggregation",
            "id": record.id,
            "name": record.name,
            "description": record.description,
            "created_at": record.created_at,
            "metadata": to_plain(record.metadata),
            "source_stored_query_id": record.source_stored_query_id,
            "source_query_snapshot": to_plain(record.source_query_snapshot),
            "external_key": record.external_key,
            "membership_hash": record.membership_hash,
            "supersedes_id": record.supersedes_id,
            "members": [
                {
                    "ordinal": member.ordinal,
                    "structure_id": member.structure_id,
                    "evaluation_id": member.evaluation_id,
                }
                for member in record.members
            ],
        }
    else:
        raise TypeError(f"Unsupported record type: {type(record)!r}")
    return hashlib.sha256(json_dumps(payload).encode()).hexdigest()
