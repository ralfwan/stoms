"""Local, read-only browser homepage for one STOMS ledger.

The server uses only the standard library. It binds to the loopback interface
by default and serves a static single-page app plus a small JSON API. Requests
are handled on separate threads so an idle browser connection (for example a
speculative preconnect) cannot stall others; this is safe because the SQLite
repository opens a fresh connection for every transaction.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import mimetypes
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, unquote, urlsplit

import numpy as np
from ase.io import write

from ..atomsledger import (
    AggregationNotFoundError,
    AtomsLedger,
    DatasetQuery,
    EvaluationQuery,
    RecordNotFoundError,
    SelectedRecord,
    StrictSelection,
    StrictSelectionError,
    StructureQuery,
)

if TYPE_CHECKING:
    from .extxyz import ExtxyzSource
from ..atomsledger.serialization import (
    json_dumps,
    method_to_dict,
    provenance_to_dict,
    structure_source_to_dict,
    to_plain,
)

STATIC_FILES = (
    "index.html",
    "app.js",
    "app.css",
    "viewer.js",
)
HISTOGRAM_BINS = 40
MAX_REQUEST_BYTES = 5_000_000


class BadRequest(ValueError):
    """A request the client must fix (answered with HTTP 400)."""


class UnknownRoute(Exception):
    """No API endpoint matches the path (answered with HTTP 404)."""


def _safe_filename(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._+-]+", "_", name).strip("._") or "export"
    return stem[:120]


@dataclass(frozen=True)
class Download:
    """A file response offered to the browser as an attachment."""

    filename: str
    body: bytes
    content_type: str = "application/octet-stream"


def _stats(values: np.ndarray) -> dict[str, Any]:
    if not values.size:
        return {"n": 0}
    return {
        "n": int(values.size),
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "std": float(values.std()),
    }


def _histogram(values: np.ndarray) -> dict[str, Any]:
    if not values.size:
        return {"edges": [], "counts": []}
    low, high = float(values.min()), float(values.max())
    if low == high:
        low, high = low - 0.5, high + 0.5
    counts, edges = np.histogram(
        values, bins=HISTOGRAM_BINS, range=(low, high)
    )
    return {"edges": edges.tolist(), "counts": counts.tolist()}


def _numeric(value: Any) -> np.ndarray | None:
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return None
    return array


class _PropertySeries:
    """Collects one method/property pair across aggregation members.

    Every series has one value per member (used for filtering members); per-atom
    properties additionally pool every atom into a distribution.
    """

    def __init__(self, method: str, name: str, unit: str | None) -> None:
        self.method = method
        self.name = name
        self.unit = unit
        self.kind: str | None = None
        self.ordinals: list[int] = []
        self.values: list[float] = []
        self.natoms: list[int] = []
        self.pooled: list[np.ndarray] = []

    def add(self, ordinal: int, natoms: int, array: np.ndarray) -> None:
        if array.ndim == 0:
            kind, value, pooled = "scalar", float(array), None
        elif array.ndim == 1 and array.shape[0] == natoms:
            kind, value, pooled = "per_atom", float(array.mean()), array
        elif array.ndim == 2 and array.shape == (natoms, 3):
            norms = np.linalg.norm(array, axis=1)
            kind, value, pooled = "per_atom_vector", float(norms.max()), norms
        else:
            kind, value, pooled = "array", float(np.linalg.norm(array)), None
        if self.kind is None:
            self.kind = kind
        elif self.kind != kind:
            self.kind = "array"
        if math.isfinite(value):
            self.ordinals.append(ordinal)
            self.values.append(value)
            self.natoms.append(natoms)
        if pooled is not None:
            self.pooled.append(pooled[np.isfinite(pooled)])

    def to_dict(self) -> dict[str, Any]:
        per_member = {
            "scalar": "value",
            "per_atom": "mean over atoms",
            "per_atom_vector": "max |vector| over atoms",
        }.get(self.kind or "array", "norm")
        result: dict[str, Any] = {
            "method": self.method,
            "property": self.name,
            "unit": self.unit,
            "kind": self.kind,
            "per_member": per_member,
            "ordinals": self.ordinals,
            "values": self.values,
            "natoms": self.natoms,
            "stats": _stats(np.asarray(self.values)),
            "pooled": None,
        }
        if self.pooled and self.kind in ("per_atom", "per_atom_vector"):
            pooled = np.concatenate(self.pooled)
            result["pooled"] = {
                "label": (
                    "|vector| of every atom"
                    if self.kind == "per_atom_vector"
                    else "every atom"
                ),
                "stats": _stats(pooled),
                "histogram": _histogram(pooled),
            }
        return result


def _iteration(tags: Any) -> str | None:
    iterations = [
        tag.removeprefix("iteration:")
        for tag in tags
        if tag.startswith("iteration:")
    ]
    return iterations[0] if len(iterations) == 1 and iterations[0] else None


def _source_label(structure: Any) -> str:
    return _spec_label(structure.source_spec)


def _spec_label(spec: Any) -> str:
    return "/".join(part for part in (spec.name, spec.tool, spec.kind) if part)


def _atom_count(formula: str) -> int:
    """Atoms in a chemical formula such as ``O84Sr25Ti32`` (141)."""
    return sum(
        int(count or 1)
        for _, count in re.findall(r"([A-Z][a-z]*)(\d*)", formula)
    )


def _evaluation_header(evaluation: Any) -> dict[str, Any]:
    """Method and provenance of one evaluation, as shown in detail panels."""
    provenance = provenance_to_dict(evaluation.provenance)
    provenance["effective_tags"] = list(evaluation.effective_tags)
    return {
        "id": evaluation.id,
        "method": (
            f"{evaluation.method.name}/{evaluation.method.method_identifier}"
        ),
        "method_spec": method_to_dict(evaluation.method),
        "provenance": provenance,
    }


def _property_overview(
    name: str, value: Any, unit: str | None
) -> dict[str, Any]:
    """Shape and value (scalars) or summary statistics (arrays)."""
    array = _numeric(value)
    if array is None:
        return {"name": name, "unit": unit, "shape": None}
    overview: dict[str, Any] = {
        "name": name,
        "unit": unit,
        "shape": list(array.shape),
    }
    if array.size == 1:
        overview["value"] = float(array.reshape(()))
        return overview
    overview["stats"] = _stats(array.ravel())
    if array.ndim == 2 and array.shape[1] == 3:
        overview["max_norm"] = float(np.linalg.norm(array, axis=1).max())
    return overview


def _summary_to_dict(summary: Any) -> dict[str, Any]:
    return to_plain(
        {
            "id": summary.id,
            "name": summary.name,
            "description": summary.description,
            "created_at": summary.created_at.isoformat(),
            "metadata": summary.metadata,
            "source_stored_query_id": summary.source_stored_query_id,
            "external_key": summary.external_key,
            "membership_hash": summary.membership_hash,
            "supersedes_id": summary.supersedes_id,
            "member_count": summary.member_count,
        }
    )


def _member_row(member: Any, entry: Any) -> dict[str, Any]:
    """A member table row from catalog metadata, without atom arrays or
    evaluation properties: thousands of rows stay fast."""
    tags = list(entry.tags)
    evaluation = next(
        (e for e in entry.evaluators if e.id == member.evaluation_id), None
    )
    return {
        "ordinal": member.ordinal,
        "structure_id": entry.id,
        "formula": entry.formula,
        "natoms": _atom_count(entry.formula),
        "source": _spec_label(entry.source_spec),
        "iteration": _iteration(tags),
        "tags": tags,
        "evaluation_id": evaluation.id if evaluation else None,
        "method": (
            f"{evaluation.method.name}/{evaluation.method.method_identifier}"
            if evaluation is not None
            else None
        ),
        "properties": (
            [
                {"name": name, "unit": evaluation.units.get(name)}
                for name in sorted(evaluation.property_names)
            ]
            if evaluation is not None
            else []
        ),
    }


@dataclass(frozen=True)
class _Summary:
    """What a step list needs of a structure (no atom arrays)."""

    id: str
    formula: str
    tags: tuple[str, ...]
    created_at: Any


def _related_entries(summaries: list[_Summary]) -> list[dict[str, Any]]:
    """Step-through entries labelled by the tags that set structures apart."""
    shared = (
        set.intersection(*(set(item.tags) for item in summaries))
        if summaries
        else set()
    )
    return [
        {
            "id": item.id,
            "formula": item.formula,
            "iteration": _iteration(item.tags),
            "distinct_tags": [
                tag
                for tag in item.tags
                if tag not in shared and not tag.startswith("iteration:")
            ],
        }
        for item in summaries
    ]


class LedgerView:
    """JSON-ready read models built from an open ledger."""

    def __init__(
        self,
        ledger: AtomsLedger,
        label: str,
        source: ExtxyzSource | None = None,
    ) -> None:
        self.ledger = ledger
        self.label = label
        # Set when serving one extxyz file: its frames export verbatim.
        self.source = source

    def overview(self) -> dict[str, Any]:
        return {"ledger": self.label, "file": self.source is not None}

    def _verbatim(self, aggregation_id: str) -> ExtxyzSource | None:
        """The served file, if ``aggregation_id`` holds its frames in order."""
        source = self.source
        if (
            source is not None
            and source.aggregation_id == aggregation_id
            and source.spans is not None
        ):
            return source
        return None

    def aggregations(self) -> list[dict[str, Any]]:
        summaries = sorted(
            self.ledger.list_aggregations(),
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )
        return [_summary_to_dict(summary) for summary in summaries]

    def aggregation(self, aggregation_id: str) -> dict[str, Any]:
        aggregation = self.ledger.get_aggregation(aggregation_id)
        entries = self._catalog_entries(
            tuple(dict.fromkeys(m.structure_id for m in aggregation.members))
        )
        members = (
            [
                _member_row(member, entries[member.structure_id])
                for member in aggregation.members
            ]
            if entries is not None
            else [
                self._loaded_member_row(member)
                for member in aggregation.members
            ]
        )
        return to_plain(
            {
                "id": aggregation.id,
                "name": aggregation.name,
                "description": aggregation.description,
                "created_at": aggregation.created_at.isoformat(),
                "metadata": aggregation.metadata,
                "source_stored_query_id": aggregation.source_stored_query_id,
                "source_query_snapshot": aggregation.source_query_snapshot,
                "external_key": aggregation.external_key,
                "members": members,
            }
        )

    def member(self, aggregation_id: str, ordinal: int) -> dict[str, Any]:
        aggregation = self.ledger.get_aggregation(aggregation_id)
        member = next(
            (item for item in aggregation.members if item.ordinal == ordinal),
            None,
        )
        if member is None:
            raise RecordNotFoundError(
                f"Aggregation {aggregation_id} has no member {ordinal}"
            )
        repository = self.ledger.repository
        structure = repository.get_structure(member.structure_id)
        structure_provenance = provenance_to_dict(structure.provenance)
        structure_provenance["effective_tags"] = list(structure.effective_tags)
        detail: dict[str, Any] = {
            "ordinal": member.ordinal,
            "structure_id": structure.id,
            "source": _source_label(structure),
            "source_spec": structure_source_to_dict(structure.source_spec),
            "structure_provenance": structure_provenance,
            "evaluation": None,
        }
        if member.evaluation_id is not None:
            detail["evaluation"] = _evaluation_header(
                repository.get_evaluation(member.evaluation_id)
            )
        return to_plain(detail)

    def structure(self, structure_id: str) -> dict[str, Any]:
        """Geometry and every evaluation recorded for one structure."""
        structure = self.ledger.repository.get_structure(structure_id)
        atoms = structure.atoms
        natoms = len(atoms)
        evaluations = []
        for evaluation in self.ledger.find_evaluations(
            EvaluationQuery(structure_ids=(structure.id,))
        ):
            spec = method_to_dict(evaluation.method)
            vectors = []
            scalars = []
            for name in sorted(evaluation.properties):
                array = _numeric(evaluation.properties[name])
                if array is None:
                    continue
                if array.shape == (natoms, 3):
                    vectors.append(
                        {"name": name, "unit": evaluation.units.get(name)}
                    )
                elif array.size == 1:
                    scalars.append(
                        {
                            "name": name,
                            "unit": evaluation.units.get(name),
                            "value": float(array.reshape(())),
                        }
                    )
            evaluations.append(
                {
                    "id": evaluation.id,
                    "created_at": evaluation.created_at.isoformat(),
                    "method": (
                        f"{evaluation.method.name}/"
                        f"{evaluation.method.method_identifier}"
                    ),
                    "family": evaluation.method.family,
                    "spec_hash": hashlib.sha256(
                        json_dumps(spec).encode()
                    ).hexdigest()[:8],
                    "tags": list(evaluation.effective_tags),
                    "vectors": vectors,
                    "scalars": scalars,
                }
            )
        evaluations.sort(key=lambda item: (item["method"], item["created_at"]))
        return to_plain(
            {
                "id": structure.id,
                "formula": atoms.get_chemical_formula(),
                "created_at": structure.created_at.isoformat(),
                "source": _source_label(structure),
                "tags": list(structure.effective_tags),
                "numbers": atoms.numbers.tolist(),
                "symbols": atoms.get_chemical_symbols(),
                "positions": np.round(atoms.positions, 5).tolist(),
                "cell": np.round(atoms.cell.array, 5).tolist(),
                "pbc": atoms.pbc.tolist(),
                "evaluations": evaluations,
            }
        )

    def evaluation(self, evaluation_id: str) -> dict[str, Any]:
        """Method, provenance, and a per-property overview of an evaluation."""
        evaluation = self.ledger.load_evaluation(evaluation_id)
        detail = _evaluation_header(evaluation)
        detail["structure_id"] = evaluation.structure_id
        detail["created_at"] = evaluation.created_at.isoformat()
        detail["properties"] = [
            _property_overview(
                name, evaluation.properties[name], evaluation.units.get(name)
            )
            for name in sorted(evaluation.properties)
        ]
        return to_plain(detail)

    def evaluation_vector(
        self, evaluation_id: str, name: str
    ) -> dict[str, Any]:
        """One per-atom vector property (for example forces) of an evaluation."""
        evaluation = self.ledger.load_evaluation(evaluation_id)
        if name not in evaluation.properties:
            raise RecordNotFoundError(
                f"Evaluation {evaluation_id} has no property {name}"
            )
        array = _numeric(evaluation.properties[name])
        if array is None or array.ndim != 2 or array.shape[1] != 3:
            raise RecordNotFoundError(
                f"Property {name} of {evaluation_id} is not a per-atom vector"
            )
        return {
            "evaluation_id": evaluation.id,
            "name": name,
            "unit": evaluation.units.get(name),
            "values": np.round(array, 6).tolist(),
        }

    def _catalog_entries(self, ids: tuple[str, ...]) -> dict[str, Any] | None:
        """Catalog entries of the given structures by ID, or None without a
        catalog (only SQLite ledgers have one)."""
        try:
            catalog = self.ledger.catalog
        except TypeError:
            return None
        return {
            entry.id: entry
            for entry in catalog.iter_search(StructureQuery(ids=ids))
        }

    def _loaded_member_row(self, member: Any) -> dict[str, Any]:
        """A member table row from the full structure and evaluation."""
        repository = self.ledger.repository
        structure = repository.get_structure(member.structure_id)
        evaluation = (
            repository.get_evaluation(member.evaluation_id)
            if member.evaluation_id is not None
            else None
        )
        tags = list(structure.effective_tags)
        return {
            "ordinal": member.ordinal,
            "structure_id": structure.id,
            "formula": structure.atoms.get_chemical_formula(),
            "natoms": len(structure.atoms),
            "source": _source_label(structure),
            "iteration": _iteration(tags),
            "tags": tags,
            "evaluation_id": evaluation.id if evaluation else None,
            "method": (
                f"{evaluation.method.name}/{evaluation.method.method_identifier}"
                if evaluation is not None
                else None
            ),
            "properties": (
                [
                    {"name": name, "unit": evaluation.units.get(name)}
                    for name in sorted(evaluation.properties)
                ]
                if evaluation is not None
                else []
            ),
        }

    def _summaries(self, query: StructureQuery) -> dict[str, _Summary]:
        """Formula and effective tags of matching structures, by ID.

        SQLite answers from its metadata catalog without reading atom arrays,
        which matters for step lists of thousands of structures; other
        backends load the structures.
        """
        try:
            catalog = self.ledger.catalog
        except TypeError:
            return {
                record.id: _Summary(
                    record.id,
                    record.atoms.get_chemical_formula(),
                    tuple(record.effective_tags),
                    record.created_at,
                )
                for record in self.ledger.find_structures(query)
            }
        return {
            entry.id: _Summary(
                entry.id, entry.formula, tuple(entry.tags), entry.created_at
            )
            for entry in catalog.iter_search(query)
        }

    def related(self, structure_id: str, prefix: str) -> dict[str, Any]:
        """Structures sharing a tag with ``prefix``, ordered by iteration."""
        structure = self.ledger.repository.get_structure(structure_id)
        tags = tuple(
            tag for tag in structure.effective_tags if tag.startswith(prefix)
        )
        if not prefix or not tags:
            return {"prefix": prefix, "tags": [], "structures": []}
        summaries = list(
            self._summaries(StructureQuery(tags_any=tags)).values()
        )
        summaries.sort(
            key=lambda item: (
                _iteration(item.tags) or "",
                item.created_at,
                item.id,
            )
        )
        return {
            "prefix": prefix,
            "tags": list(tags),
            "structures": _related_entries(summaries),
        }

    def related_members(self, aggregation_id: str) -> dict[str, Any]:
        """Distinct member structures of one aggregation in member order.

        A structure listed with several evaluations appears once, at its
        first ordinal.
        """
        aggregation = self.ledger.get_aggregation(aggregation_id)
        ordinals: dict[str, int] = {}
        for member in aggregation.members:
            ordinals.setdefault(member.structure_id, member.ordinal)
        summaries = self._summaries(StructureQuery(ids=tuple(ordinals)))
        entries = _related_entries([summaries[sid] for sid in ordinals])
        for entry in entries:
            entry["ordinal"] = ordinals[entry["id"]]
        return {
            "aggregation": {"id": aggregation.id, "name": aggregation.name},
            "structures": entries,
        }

    def summary(self, aggregation_id: str) -> dict[str, Any]:
        """Evaluation coverage and property distributions for one aggregation."""
        aggregation = self.ledger.get_aggregation(aggregation_id)
        repository = self.ledger.repository
        iterations: dict[str | None, dict[str, int]] = {}
        series: dict[tuple[str, str], _PropertySeries] = {}
        for member in aggregation.members:
            structure = repository.get_structure(member.structure_id)
            natoms = len(structure.atoms)
            counts = iterations.setdefault(
                _iteration(structure.effective_tags),
                {"evaluated": 0, "missing": 0},
            )
            if member.evaluation_id is None:
                counts["missing"] += 1
                continue
            counts["evaluated"] += 1
            evaluation = repository.get_evaluation(member.evaluation_id)
            method = (
                f"{evaluation.method.name}/"
                f"{evaluation.method.method_identifier}"
            )
            for name in sorted(evaluation.properties):
                array = _numeric(evaluation.properties[name])
                if array is None:
                    continue
                key = (method, name)
                if key not in series:
                    series[key] = _PropertySeries(
                        method, name, evaluation.units.get(name)
                    )
                series[key].add(member.ordinal, natoms, array)
        ordered = sorted(
            iterations.items(),
            key=lambda item: (item[0] is None, item[0] or ""),
        )
        return {
            "members": len(aggregation.members),
            "evaluated": sum(c["evaluated"] for c in iterations.values()),
            "missing": sum(c["missing"] for c in iterations.values()),
            "iterations": [
                {"iteration": iteration, **counts}
                for iteration, counts in ordered
            ],
            "properties": [series[key].to_dict() for key in sorted(series)],
        }

    def structure_extxyz(
        self, structure_id: str, evaluation_id: str | None
    ) -> Download:
        """One structure as extxyz: verbatim from a served file, else with
        the given evaluation (or none)."""
        source = self.source
        if (
            source is not None
            and source.spans is not None
            and structure_id in source.frames
        ):
            frame = source.frames[structure_id]
            stem = source.path.name.rsplit(".", 1)[0]
            return Download(
                _safe_filename(f"{stem}_frame{frame}") + ".extxyz",
                source.text([frame]),
            )
        repository = self.ledger.repository
        structure = repository.get_structure(structure_id)
        evaluation = None
        if evaluation_id is not None:
            evaluation = repository.get_evaluation(evaluation_id)
            if evaluation.structure_id != structure_id:
                raise BadRequest(
                    f"Evaluation {evaluation_id} belongs to another structure"
                )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "structure.extxyz"
            _write_frames(destination, [(structure, evaluation)], {})
            body = destination.read_bytes()
        return Download(f"{_safe_filename(structure_id)}.extxyz", body)

    def extxyz(
        self, aggregation_id: str, options: dict[str, list[str]]
    ) -> Download:
        """Export an aggregation with the same options as the CLI command."""
        source = self._verbatim(aggregation_id)
        if source is not None:
            body = source.text(list(range(len(source.spans or ()))))
            return Download(_safe_filename(source.path.name), body)
        labels = _export_labels(
            {key: values[0] for key, values in options.items() if values}
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "aggregation.extxyz"
            self.ledger.to_extxyz(
                destination, aggregation_id=aggregation_id, **labels
            )
            body = destination.read_bytes()
        return Download(f"{aggregation_id}.extxyz", body)

    def extxyz_files(
        self, aggregation_id: str, request: dict[str, Any]
    ) -> Download:
        """Export chosen members into one or more extxyz files.

        ``request["files"]`` lists ``{"name": ..., "ordinals": [...]}``; each
        file keeps the aggregation's member order. One file is returned as
        extxyz, several as a zip archive. Members without an evaluation are
        refused unless ``request["include_unevaluated"]`` is true; then they
        are written as structures only. Frames of a served extxyz file are
        copied verbatim.
        """
        files = request.get("files")
        if not isinstance(files, list) or not files:
            raise BadRequest("files must be a non-empty list")
        aggregation = self.ledger.get_aggregation(aggregation_id)
        members = {member.ordinal: member for member in aggregation.members}
        repository = self.ledger.repository
        labels = _export_labels(request)
        include_unevaluated = request.get("include_unevaluated") is True
        source = self._verbatim(aggregation_id)
        names: set[str] = set()
        outputs: list[tuple[str, bytes]] = []
        with tempfile.TemporaryDirectory() as directory:
            for entry in files:
                if not isinstance(entry, dict):
                    raise BadRequest("each file must be an object")
                ordinals = entry.get("ordinals")
                if not isinstance(ordinals, list) or not ordinals:
                    raise BadRequest(
                        "each file needs a non-empty ordinals list"
                    )
                name = _safe_filename(str(entry.get("name", "export")))
                if not name.endswith(".extxyz"):
                    name += ".extxyz"
                if name in names:
                    raise BadRequest(f"duplicate file name: {name}")
                names.add(name)
                for ordinal in ordinals:
                    if not isinstance(ordinal, int) or ordinal not in members:
                        raise RecordNotFoundError(
                            f"Aggregation {aggregation_id} has no member {ordinal}"
                        )
                ordered = sorted(set(ordinals))
                destination = Path(directory) / name
                if source is not None:
                    destination.write_bytes(source.text(ordered))
                    outputs.append((name, destination.read_bytes()))
                    continue
                records = []
                for ordinal in ordered:
                    member = members[ordinal]
                    if (
                        member.evaluation_id is None
                        and not include_unevaluated
                    ):
                        raise StrictSelectionError(
                            f"Aggregation {aggregation_id} member "
                            f"{ordinal} has no evaluation"
                        )
                    records.append(
                        (
                            repository.get_structure(member.structure_id),
                            None
                            if member.evaluation_id is None
                            else repository.get_evaluation(
                                member.evaluation_id
                            ),
                        )
                    )
                if all(evaluation is not None for _, evaluation in records):
                    self.ledger.to_extxyz(
                        destination,
                        selection=StrictSelection(
                            query=DatasetQuery(),
                            records=tuple(
                                SelectedRecord(structure, evaluation)
                                for structure, evaluation in records
                                if evaluation is not None
                            ),
                        ),
                        **labels,
                    )
                else:
                    _write_frames(destination, records, labels)
                outputs.append((name, destination.read_bytes()))
        if len(outputs) == 1:
            return Download(*outputs[0])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, body in outputs:
                archive.writestr(name, body)
        archive_name = _safe_filename(
            str(request.get("archive_name") or aggregation_id)
        )
        return Download(
            f"{archive_name}.zip", buffer.getvalue(), "application/zip"
        )


def _write_frames(
    destination: Path,
    records: list[tuple[Any, Any]],
    labels: dict[str, Any],
) -> None:
    """Write structure/evaluation pairs as extxyz; evaluations may be None."""
    write(
        str(destination),
        [
            AtomsLedger._export_frame(structure, evaluation, **labels)
            for structure, evaluation in records
        ],
        format="extxyz",
        write_info=True,
        write_results=False,
    )


def _export_labels(options: dict[str, Any]) -> dict[str, Any]:
    """extxyz label options shared by the GET and POST export endpoints."""

    def option(name: str, default: str) -> str:
        value = str(options.get(name) or "").strip()
        return value or default

    return {
        "energy_label": option("energy_label", "REF_energy"),
        "forces_label": option("forces_label", "REF_forces"),
        "node_energy_label": option("node_energy_label", "REF_node_energy"),
        "include_node_energy": options.get("include_node_energy")
        in (True, "1", "true"),
    }


def _route(
    view: LedgerView, path: str, query: dict[str, list[str]] | None = None
) -> Any:
    parts = [unquote(part) for part in path.strip("/").split("/")]
    match parts:
        case ["api", "ledger"]:
            return view.overview()
        case ["api", "aggregations"]:
            return view.aggregations()
        case ["api", "aggregations", aggregation_id]:
            return view.aggregation(aggregation_id)
        case ["api", "aggregations", aggregation_id, "members", ordinal]:
            if not ordinal.isdigit():
                raise RecordNotFoundError(f"Invalid member ordinal: {ordinal}")
            return view.member(aggregation_id, int(ordinal))
        case ["api", "aggregations", aggregation_id, "summary"]:
            return view.summary(aggregation_id)
        case ["api", "aggregations", aggregation_id, "extxyz"]:
            return view.extxyz(aggregation_id, query or {})
        case ["api", "structures", structure_id]:
            return view.structure(structure_id)
        case ["api", "structures", structure_id, "extxyz"]:
            evaluation = (query or {}).get("evaluation", [None])[0]
            return view.structure_extxyz(structure_id, evaluation or None)
        case ["api", "structures", structure_id, "related"]:
            query = query or {}
            if "aggregation" in query:
                return view.related_members(query["aggregation"][0])
            prefix = query.get("prefix", ["run:"])[0]
            return view.related(structure_id, prefix)
        case ["api", "evaluations", evaluation_id]:
            return view.evaluation(evaluation_id)
        case ["api", "evaluations", evaluation_id, "vectors", name]:
            return view.evaluation_vector(evaluation_id, name)
    raise UnknownRoute(path)


def _handler(view: LedgerView) -> type[BaseHTTPRequestHandler]:
    static = resources.files(__package__).joinpath("static")

    class Handler(BaseHTTPRequestHandler):
        server_version = "stoms"

        def do_GET(self) -> None:  # noqa: N802
            url = urlsplit(self.path)
            path = url.path
            if path.startswith("/api/"):
                self._api(path, parse_qs(url.query))
                return
            name = path.lstrip("/") or "index.html"
            if name not in STATIC_FILES:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            body = static.joinpath(*name.split("/")).read_bytes()
            content_type = mimetypes.guess_type(name)[0] or "text/plain"
            self._send(body, f"{content_type}; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            match = re.fullmatch(r"/api/aggregations/([^/]+)/extxyz", path)
            if match is None:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            # A JSON content type forces a CORS preflight for cross-site pages.
            if not self.headers.get("Content-Type", "").startswith(
                "application/json"
            ):
                self._send_json(
                    {"error": "Expected application/json"},
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                )
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_REQUEST_BYTES:
                self._send_json(
                    {"error": "Request too large"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json(
                    {"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST
                )
                return
            if not isinstance(request, dict):
                self._send_json(
                    {"error": "Expected a JSON object"}, HTTPStatus.BAD_REQUEST
                )
                return
            aggregation_id = unquote(match.group(1))
            self._respond(lambda: view.extxyz_files(aggregation_id, request))

        def _api(self, path: str, query: dict[str, list[str]]) -> None:
            self._respond(lambda: _route(view, path, query))

        def _respond(self, produce: Any) -> None:
            try:
                payload = produce()
            except BadRequest as error:
                self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except UnknownRoute:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            except (AggregationNotFoundError, RecordNotFoundError) as error:
                self._send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
            except StrictSelectionError as error:
                self._send_json({"error": str(error)}, HTTPStatus.CONFLICT)
            except sqlite3.DatabaseError as error:
                self._send_json(
                    {"error": str(error)}, HTTPStatus.INTERNAL_SERVER_ERROR
                )
            else:
                if isinstance(payload, Download):
                    self._send(
                        payload.body,
                        payload.content_type,
                        headers={
                            "Content-Disposition": (
                                f'attachment; filename="{payload.filename}"'
                            )
                        },
                    )
                else:
                    self._send_json(payload)

        def _send_json(
            self, payload: Any, status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode()
            self._send(body, "application/json", status)

        def _send(
            self,
            body: bytes,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            if "Cache-Control" not in (headers or {}):
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def create_server(
    ledger: AtomsLedger,
    label: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    source: ExtxyzSource | None = None,
) -> ThreadingHTTPServer:
    """Build a threaded HTTP server for one open ledger."""
    server = ThreadingHTTPServer(
        (host, port), _handler(LedgerView(ledger, label, source))
    )
    server.daemon_threads = True
    return server


def serve(
    path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
) -> None:
    """Serve the homepage for the SQLite ledger at ``path`` until interrupted."""
    server = create_server(AtomsLedger(path), str(path), host=host, port=port)
    run(server, path, open_browser=open_browser)


def _interrupt(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt


def open_browser_page(url: str) -> threading.Thread | None:
    """Open ``url`` in a browser; if that fails, say where to go instead.

    On Linux without ``BROWSER``, Python hands the address to ``xdg-open``
    without waiting, so its "not found" lines land in the terminal and a
    failure goes unnoticed. There ``xdg-open`` runs quietly in the background
    and its exit status decides; the returned thread is for tests.
    """
    if (
        sys.platform.startswith("linux")
        and not os.environ.get("BROWSER")
        and shutil.which("xdg-open")
    ):
        thread = threading.Thread(target=_xdg_open, args=(url,), daemon=True)
        thread.start()
        return thread
    import webbrowser

    try:
        opened = webbrowser.open(url)
    except webbrowser.Error:
        opened = False
    if not opened:
        _no_browser(url)
    return None


def _xdg_open(url: str) -> None:
    try:
        process = subprocess.Popen(
            ["xdg-open", url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        status = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        return  # still running: it found a browser that has not returned yet
    except OSError:
        status = 1
    if status != 0:
        _no_browser(url)


def _no_browser(url: str) -> None:
    lines = [
        "Could not open a web browser. Open this address in your browser:",
        f"  {url}",
    ]
    if _on_wsl():
        lines.append(
            "On WSL, open it in your Windows browser, or install wslu and "
            "set BROWSER=wslview to make --open work."
        )
    print("\n".join(lines), file=sys.stderr, flush=True)


def _on_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def run(
    server: ThreadingHTTPServer,
    path: Path,
    *,
    open_browser: bool = False,
    page: str = "",
) -> None:
    """Serve until interrupted; ``page`` is the start page's URL fragment."""
    host, port = server.server_address[:2]
    if isinstance(host, bytes):
        host = host.decode()
    url = f"http://{host}:{port}/"
    print(f"Serving {path} at {url} (Ctrl+C to stop)", flush=True)
    if open_browser:
        open_browser_page(url + page)
    # Stop on SIGTERM as on Ctrl+C, so callers' cleanup (such as a temporary
    # ledger) still runs.
    signal.signal(signal.SIGTERM, _interrupt)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
