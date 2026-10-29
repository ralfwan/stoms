"""Local, read-only browser homepage for one STOMS ledger.

The server uses only the standard library. It binds to the loopback interface
by default and serves a static single-page app plus a small JSON API. Requests
are handled on separate threads so an idle browser connection (for example a
speculative preconnect) cannot stall others; this is safe because the SQLite
repository opens a fresh connection for every transaction.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import ipaddress
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
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, unquote, urlsplit

import numpy as np
from ase.io import write

from ..analysis import find_rings
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
    from ..parsers.v_sim import Modes
    from .extxyz import ExtxyzSource
    from .phonons import PhononModel
from ..atomsledger.serialization import (
    json_dumps,
    method_to_dict,
    provenance_to_dict,
    structure_source_to_dict,
    to_plain,
)
from .linked_pages import URL_PREFIX, LinkedPage

STATIC_FILES = (
    "index.html",
    "app.js",
    "app.css",
    "viewer.js",
)
HISTOGRAM_BINS = 40
# Structure IDs per query when checking linked-page manifests.
ID_BATCH = 500
# Linked pages run as their own origin, cut off from the API and storage,
# without dialogs or downloads. Links may open new tabs, and those are not
# sandboxed, so a link back to the viewer opens a working viewer; anything
# served under /linked/ carries this policy again and stays sandboxed.
LINKED_PAGE_SANDBOX = (
    "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox"
)
# The viewer's own pages: scripts and connections only from this server,
# no inline scripts or event handlers (styles may be inline: el() sets
# style attributes), and no framing by other sites. Linked pages have their
# own policy (LINKED_PAGE_SANDBOX).
VIEWER_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)
VIEWER_HEADERS = {
    "Content-Security-Policy": VIEWER_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
MAX_REQUEST_BYTES = 5_000_000
# Keyword arguments of find_rings accepted from the viewer, and the largest
# ring searched (the shortest-path search grows quickly with it).
RING_OPTIONS = {
    "elements",
    "heights",
    "cutoffs",
    "alternating",
    "count",
    "method",
    "enclosed",
    "max_size",
}
MAX_RING_SIZE = 24
# Added structure files (base64 in JSON).
MAX_UPLOAD_BYTES = 200_000_000


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


def _per_atom(value: Any, natoms: int) -> dict[str, Any] | None:
    """One value per atom, for colouring atoms: numbers, 3-vectors or text.

    Returns ``{"kind": "number" | "vector" | "text", "values": [...]}`` (non-finite
    numbers become null), or None when ``value`` is not one value per atom.
    """
    try:
        array = np.asarray(value)
    except (TypeError, ValueError):
        return None
    if natoms < 1 or array.ndim not in (1, 2) or array.shape[0] != natoms:
        return None
    if array.ndim == 2 and array.shape[1] == 1:
        array = array[:, 0]
    if array.dtype.kind in "US" and array.ndim == 1:
        return {"kind": "text", "values": [str(v) for v in array]}
    if array.dtype.kind not in "biuf" or not (
        array.ndim == 1 or array.shape[1] == 3
    ):
        return None
    values = np.round(array.astype(float), 6).tolist()

    def finite(v: float) -> float | None:
        return v if math.isfinite(v) else None

    return {
        "kind": "number" if array.ndim == 1 else "vector",
        "values": [
            finite(v) if array.ndim == 1 else [finite(c) for c in v]
            for v in values
        ],
    }


# ASE arrays every structure has; shown by the viewer in other ways.
STRUCTURE_ARRAYS_SHOWN = {"numbers", "positions"}
# Properties of the whole structure: never one value per atom, even when
# their length equals the number of atoms (a Voigt stress on six atoms).
STRUCTURE_LEVEL = {
    "energy",
    "free_energy",
    "stress",
    "virial",
    "dipole",
    "magmom",
    "charge",
    "cell",
    "pbc",
}


def _structure_level(name: str) -> bool:
    """Whether a property name ("stress", "REF_stress", "dft.virial") names
    a property of the whole structure."""
    base = name.rsplit(".", 1)[-1].lower()
    return base in STRUCTURE_LEVEL or any(
        base.endswith(f"_{level}") for level in STRUCTURE_LEVEL
    )


def _structure_arrays(structure: Any, atoms: Any) -> list[dict[str, Any]]:
    """Per-atom arrays of a structure, for colouring atoms in the viewer.

    Found in the ASE arrays (for example ``tags``, ``initial_magmoms`` or extra
    extxyz columns), and as lists with one entry per atom in ``atoms.info`` or
    the structure's provenance metadata (one level of nesting).
    """
    natoms = len(atoms)
    found: list[dict[str, Any]] = []
    for name in sorted(atoms.arrays):
        if name in STRUCTURE_ARRAYS_SHOWN:
            continue
        values = _per_atom(atoms.arrays[name], natoms)
        if values is not None:
            found.append({"name": name, "source": "arrays", **values})
    for source, mapping in (
        ("info", atoms.info),
        ("metadata", structure.provenance.metadata),
    ):
        for key, value in sorted(mapping.items(), key=lambda kv: str(kv[0])):
            nested = value.items() if isinstance(value, Mapping) else ()
            for name, item in [(str(key), value)] + [
                (f"{key}.{k}", v) for k, v in nested
            ]:
                if not isinstance(
                    item, list | tuple | np.ndarray
                ) or _structure_level(name):
                    continue
                values = _per_atom(item, natoms)
                if values is not None:
                    found.append({"name": name, "source": source, **values})
    return found


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
        linked_pages: tuple[LinkedPage, ...] = (),
        modes: dict[str, tuple[Modes, ...]] | None = None,
        phonons: dict[str, PhononModel] | None = None,
    ) -> None:
        self.ledger = ledger
        self.label = label
        # Set when serving one extxyz file: its frames export verbatim.
        self.source = source
        self.linked_pages = {page.name: page for page in linked_pages}
        self._ring_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._ring_lock = threading.Lock()
        # Vibrational modes by structure ID (serving v_sim files); never
        # stored in the ledger.
        self.modes = modes or {}
        # phonopy calculations by structure ID (serving phonopy input):
        # modes at any q, bands and DOS, computed on request.
        self.phonons = phonons or {}

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

    def _links(self, structure_id: str) -> list[dict[str, str]]:
        """The linked pages whose manifest lists ``structure_id``."""
        return [
            {
                "name": page.name,
                "title": page.title,
                "description": page.description,
                "url": page.url(structure_id),
            }
            for page in self.linked_pages.values()
            if structure_id in page.structure_ids
        ]

    def _member_links(
        self, members: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Name each member's linked pages; describe each page once.

        A large aggregation would otherwise repeat every page's title,
        description and URL in every row. The browser builds a member's URL
        from ``url_template``.
        """
        used: set[str] = set()
        for row in members:
            names = [
                name
                for name, page in self.linked_pages.items()
                if row["structure_id"] in page.structure_ids
            ]
            row["linked_pages"] = names
            used.update(names)
        return [
            {
                "name": page.name,
                "title": page.title,
                "description": page.description,
                "url_template": page.url_template,
            }
            for page in self.linked_pages.values()
            if page.name in used
        ]

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
        linked_pages = self._member_links(members)
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
                "linked_pages": linked_pages,
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
            atom_values = []
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
                elif array.shape in (
                    (natoms,),
                    (natoms, 1),
                ) and not _structure_level(name):
                    atom_values.append(
                        {"name": name, "unit": evaluation.units.get(name)}
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
                    "atom_values": atom_values,
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
                # Total mass (u), for the viewer's Info tab; per-atom arrays,
                # info and metadata come from structure_extras when needed.
                "mass": float(atoms.get_masses().sum()),
                "evaluations": evaluations,
                "linked_pages": self._links(structure.id),
                "has_modes": structure.id in self.modes
                or structure.id in self.phonons,
                "has_phonons": structure.id in self.phonons,
            }
        )

    def structure_extras(self, structure_id: str) -> dict[str, Any]:
        """Data the viewer loads only when it shows it: per-atom arrays (for
        colouring atoms), ASE info and provenance metadata (Info tab)."""
        structure = self.ledger.repository.get_structure(structure_id)
        atoms = structure.atoms
        return to_plain(
            {
                "id": structure.id,
                "arrays": _structure_arrays(structure, atoms),
                "info": atoms.info,
                "metadata": structure.provenance.metadata,
            }
        )

    def structure_modes(
        self,
        structure_id: str,
        q: str | None = None,
        direction: str | None = None,
        nac: str | None = None,
    ) -> dict[str, Any]:
        """Vibrational modes of a structure served from v_sim or phonopy.

        Per q-point: frequencies in THz and, per mode and atom, the
        displacement as [Re x, Re y, Re z, Im x, Im y, Im z]. From phonopy,
        the one q-point ``q`` ("qa,qb,qc", default Γ) is computed and
        ``any_q`` is true; with NAC, ``direction`` (same form) is where
        q = 0 is approached from, and ``nac`` "0" leaves NAC out.
        """
        if structure_id in self.phonons:
            point = _vector(q or "0,0,0", "q")
            towards = (
                None if direction is None else _vector(direction, "direction")
            )
            return {
                "structure_id": structure_id,
                "unit": "THz",
                "any_q": True,
                "qpoints": [
                    self.phonons[structure_id].modes(point, towards, _nac(nac))
                ],
            }
        if structure_id not in self.modes:
            raise RecordNotFoundError(f"Structure {structure_id} has no modes")
        return {
            "structure_id": structure_id,
            "unit": "THz",
            "qpoints": [
                {
                    "q": np.round(group.qpoint, 6).tolist(),
                    "frequencies": np.round(group.frequencies, 6).tolist(),
                    "displacements": np.round(
                        np.concatenate(
                            [
                                group.displacements.real,
                                group.displacements.imag,
                            ],
                            axis=2,
                        ),
                        6,
                    ).tolist(),
                }
                for group in self.modes[structure_id]
            ],
        }

    def _phonons(self, structure_id: str) -> PhononModel:
        if structure_id not in self.phonons:
            raise RecordNotFoundError(
                f"Structure {structure_id} has no phonon calculation"
            )
        return self.phonons[structure_id]

    def phonon_bands(
        self, structure_id: str, nac: str | None = None
    ) -> dict[str, Any]:
        """Band structure of a structure served from phonopy input."""
        return self._phonons(structure_id).bands(_nac(nac))

    def phonon_dos(
        self, structure_id: str, nac: str | None = None
    ) -> dict[str, Any]:
        """Phonon DOS of a structure served from phonopy input."""
        return self._phonons(structure_id).dos(_nac(nac))

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

    def rings(self, structure_id: str, settings: str) -> dict[str, Any]:
        """Rings of one structure (:func:`stoms.analysis.find_rings`).

        ``settings`` is a JSON object of its keyword arguments; results are
        cached, as structures never change.
        """
        try:
            options = json.loads(settings or "{}")
        except json.JSONDecodeError as error:
            raise BadRequest("ring settings are not JSON") from error
        if not isinstance(options, dict) or not set(options) <= RING_OPTIONS:
            raise BadRequest(
                f"ring settings take only: {', '.join(sorted(RING_OPTIONS))}"
            )
        max_size = options.get("max_size", 12)
        if not isinstance(max_size, int) or not 3 <= max_size <= MAX_RING_SIZE:
            raise BadRequest(
                f"max_size is a whole number, 3 to {MAX_RING_SIZE}"
            )
        heights = options.get("heights", {})
        if not isinstance(heights, dict) or not all(
            isinstance(window, list) and len(window) == 2
            for window in heights.values()
        ):
            raise BadRequest(
                "ring heights map elements to [low, high] (null = open)"
            )
        key = (structure_id, json.dumps(options, sort_keys=True))
        with self._ring_lock:
            if key in self._ring_cache:
                return self._ring_cache[key]
        atoms = self.ledger.repository.get_structure(structure_id).atoms
        options["heights"] = {
            symbol: tuple(window) for symbol, window in heights.items()
        }
        try:
            result = find_rings(atoms, **options).to_dict()
        except (TypeError, ValueError, KeyError) as error:
            raise BadRequest(f"ring settings: {error}") from error
        with self._ring_lock:
            if len(self._ring_cache) > 512:
                self._ring_cache.clear()
            self._ring_cache[key] = result
        return result

    def evaluation_atom_values(
        self, evaluation_id: str, name: str
    ) -> dict[str, Any]:
        """One per-atom scalar property (for example charges) of an evaluation."""
        evaluation = self.ledger.load_evaluation(evaluation_id)
        if name not in evaluation.properties:
            raise RecordNotFoundError(
                f"Evaluation {evaluation_id} has no property {name}"
            )
        natoms = len(
            self.ledger.repository.get_structure(evaluation.structure_id).atoms
        )
        values = _per_atom(evaluation.properties[name], natoms)
        if (
            values is None
            or values["kind"] != "number"
            or _structure_level(name)
        ):
            raise RecordNotFoundError(
                f"Property {name} of {evaluation_id} is not one number per atom"
            )
        return {
            "evaluation_id": evaluation.id,
            "name": name,
            "unit": evaluation.units.get(name),
            "values": values["values"],
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
        self,
        structure_id: str,
        evaluation_id: str | None,
        file_format: str = "extxyz",
    ) -> Download:
        """One structure as extxyz (verbatim from a served file, else with
        the given evaluation or none), or as a VASP POSCAR or CIF file
        (geometry only)."""
        suffix = _export_suffix(file_format)
        if file_format != "extxyz":
            structure = self.ledger.repository.get_structure(structure_id)
            atoms = structure.atoms
            body = _write_geometry([atoms], file_format)
            name = _safe_filename(
                f"{atoms.get_chemical_formula()}_{structure_id}"
            )
            return Download(f"{name}{suffix}", body)
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
        file_format = str(request.get("format") or "extxyz")
        suffix = _export_suffix(file_format)
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
                if not name.endswith(suffix):
                    name += suffix
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
                if file_format != "extxyz":
                    # Geometry only: no evaluation needed. VASP holds one
                    # structure per file, so each member gets its own.
                    frames = [
                        repository.get_structure(
                            members[ordinal].structure_id
                        ).atoms
                        for ordinal in ordered
                    ]
                    if file_format == "cif" or len(frames) == 1:
                        outputs.append(
                            (name, _write_geometry(frames, file_format))
                        )
                    else:
                        stem = name[: -len(suffix)]
                        for ordinal, atoms in zip(
                            ordered, frames, strict=True
                        ):
                            formula = atoms.get_chemical_formula()
                            outputs.append(
                                (
                                    f"{stem}/{ordinal:05d}_{formula}{suffix}",
                                    _write_geometry([atoms], file_format),
                                )
                            )
                    continue
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


class AddedStructures:
    """The ledger's view, plus structure files added in the browser.

    Added files go into a temporary ledger that lives as long as the
    server; the served ledger (or file) is never changed. Requests about a
    record (every LedgerView method takes the record's ID first) go to the
    ledger that holds it, so added structures can be viewed, stepped through,
    compared and exported like any other.
    """

    def __init__(self, main: LedgerView) -> None:
        self.main = main
        self.added: LedgerView | None = None
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._lock = threading.Lock()
        self._count = 0
        # IDs of the structures, evaluations and aggregations added.
        self._added_ids: set[str] = set()

    def overview(self) -> dict[str, Any]:
        return {**self.main.overview(), "can_add": True}

    def aggregations(self) -> list[dict[str, Any]]:
        added = self.added.aggregations() if self.added is not None else []
        return self.main.aggregations() + [
            {**item, "added": True} for item in added
        ]

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self.main, name)
        if not callable(attribute):
            # Settings of the served ledger, such as its linked pages.
            return attribute

        def call(record_id: str, *args: Any, **kwargs: Any) -> Any:
            view = (
                self.added
                if self.added is not None and record_id in self._added_ids
                else self.main
            )
            return getattr(view, name)(record_id, *args, **kwargs)

        return call

    def add_file(self, name: str, data: bytes) -> dict[str, Any]:
        """Read every structure of one file (any format ASE reads, chosen by
        its name and content) into a new aggregation named after it."""
        from .extxyz import ExtxyzLoadError, load_extxyz

        filename = _safe_filename(Path(name).name)
        with self._lock:
            if self._directory is None:
                self._directory = tempfile.TemporaryDirectory(
                    prefix="stoms-added-"
                )
                root = Path(self._directory.name)
                self.added = LedgerView(
                    AtomsLedger(root / "added.ledger"), "added structures"
                )
            assert self.added is not None
            self._count += 1
            folder = Path(self._directory.name) / f"{self._count:04d}"
            folder.mkdir()
            path = folder / filename
            path.write_bytes(data)
            taken = {item["name"] for item in self.aggregations()}
            label, copy = filename, 1
            while label in taken:
                copy += 1
                label = f"{filename} ({copy})"
            try:
                aggregation = load_extxyz(
                    self.added.ledger, path, file_format=None, name=label
                )
            except ExtxyzLoadError as error:
                raise BadRequest(str(error)) from error
            except Exception as error:  # unusual content ASE accepted
                raise BadRequest(f"cannot add {filename}: {error}") from error
            self._added_ids.add(aggregation.id)
            for member in aggregation.members:
                self._added_ids.add(member.structure_id)
                if member.evaluation_id is not None:
                    self._added_ids.add(member.evaluation_id)
        return {
            "id": aggregation.id,
            "name": aggregation.name,
            "member_count": len(aggregation.members),
            "structure_ids": [m.structure_id for m in aggregation.members],
        }


# Download formats: extxyz keeps evaluations; VASP and CIF hold geometry only.
EXPORT_FORMATS = {"extxyz": ".extxyz", "vasp": ".vasp", "cif": ".cif"}


def _export_suffix(file_format: str) -> str:
    if file_format not in EXPORT_FORMATS:
        raise BadRequest(
            f"Unknown format {file_format!r}; "
            f"choose one of {', '.join(EXPORT_FORMATS)}"
        )
    return EXPORT_FORMATS[file_format]


def _write_geometry(frames: list[Any], file_format: str) -> bytes:
    """Structures as VASP POSCAR (one frame) or CIF (one block per frame)."""
    for atoms in frames:
        if abs(atoms.cell.volume) < 1e-9:
            raise BadRequest(
                f"{atoms.get_chemical_formula()} has no 3D cell; "
                f"{file_format.upper()} needs one (use extxyz)"
            )
    with tempfile.TemporaryDirectory() as directory:
        destination = (
            Path(directory) / f"structures{EXPORT_FORMATS[file_format]}"
        )
        if file_format == "vasp":
            write(
                str(destination),
                frames[0],
                format="vasp",
                direct=True,
                sort=False,
            )
        else:
            write(str(destination), frames, format="cif")
        return destination.read_bytes()


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


def _vector(text: str, name: str) -> tuple[float, float, float]:
    """Three finite numbers from "a,b,c", else BadRequest."""
    try:
        values = tuple(float(x) for x in text.split(","))
    except ValueError:
        values = ()
    if len(values) != 3 or not all(map(math.isfinite, values)):
        raise BadRequest(f"Expected {name} as three numbers, got {text!r}")
    return values  # type: ignore[return-value]


def _nac(text: str | None) -> bool:
    """The ``nac`` query value: "1" (the default) or "0", else BadRequest."""
    if text in (None, "1"):
        return True
    if text == "0":
        return False
    raise BadRequest(f"Expected nac as 0 or 1, got {text!r}")


def _route(
    view: Any, path: str, query: dict[str, list[str]] | None = None
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
            file_format = (query or {}).get("format", ["extxyz"])[0]
            return view.structure_extxyz(
                structure_id, evaluation or None, file_format
            )
        case ["api", "structures", structure_id, "extras"]:
            return view.structure_extras(structure_id)
        case ["api", "structures", structure_id, "rings"]:
            settings = (query or {}).get("settings", ["{}"])[0]
            return view.rings(structure_id, settings)
        case ["api", "structures", structure_id, "modes"]:
            q = (query or {}).get("q", [None])[0]
            direction = (query or {}).get("direction", [None])[0]
            nac = (query or {}).get("nac", [None])[0]
            return view.structure_modes(structure_id, q, direction, nac)
        case ["api", "structures", structure_id, "phonons", "bands"]:
            nac = (query or {}).get("nac", [None])[0]
            return view.phonon_bands(structure_id, nac)
        case ["api", "structures", structure_id, "phonons", "dos"]:
            nac = (query or {}).get("nac", [None])[0]
            return view.phonon_dos(structure_id, nac)
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
        case ["api", "evaluations", evaluation_id, "atoms", name]:
            return view.evaluation_atom_values(evaluation_id, name)
    raise UnknownRoute(path)


def _add_file(view: AddedStructures, request: dict[str, Any]) -> Any:
    """``{"name": file name, "data": base64 content}`` → the new aggregation."""
    name, data = request.get("name"), request.get("data")
    if not isinstance(name, str) or not name or not isinstance(data, str):
        raise BadRequest("expected a file name and base64 data")
    try:
        content = base64.b64decode(data, validate=True)
    except ValueError as error:
        raise BadRequest("data is not base64") from error
    return view.add_file(name, content)


def host_allowed(header: str | None, port: int, host: str) -> bool:
    """Whether a Host header names this server: an IP address, ``localhost``
    or the ``host`` it was started with, on its ``port``.

    DNS rebinding lets a web page reach this server under the page's own
    domain name; its requests name that domain and are refused.
    """
    try:
        url = urlsplit(f"//{header}")
        name, named_port = url.hostname, url.port or 80
    except ValueError:  # a malformed port
        return False
    if not header or not name or named_port != port:
        return False
    if name in ("localhost", host.lower()):
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def _handler(
    view: AddedStructures, host: str = "127.0.0.1"
) -> type[BaseHTTPRequestHandler]:
    static = resources.files(__package__).joinpath("static")

    class Handler(BaseHTTPRequestHandler):
        server_version = "stoms"

        def _misdirected(self) -> bool:
            """Refuse a request whose Host header names another server."""
            port = cast(ThreadingHTTPServer, self.server).server_port
            if host_allowed(self.headers.get("Host"), port, host):
                return False
            self._send_json(
                {"error": "Host not allowed"}, HTTPStatus.MISDIRECTED_REQUEST
            )
            return True

        def do_GET(self) -> None:  # noqa: N802
            if self._misdirected():
                return
            url = urlsplit(self.path)
            path = url.path
            if path.startswith("/api/"):
                self._api(path, parse_qs(url.query))
                return
            if path.startswith(URL_PREFIX):
                self._linked(unquote(path[len(URL_PREFIX) :]))
                return
            name = path.lstrip("/") or "index.html"
            if name not in STATIC_FILES:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            body = static.joinpath(*name.split("/")).read_bytes()
            content_type = mimetypes.guess_type(name)[0] or "text/plain"
            self._send(body, f"{content_type}; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802
            if self._misdirected():
                return
            path = urlsplit(self.path).path
            match = re.fullmatch(r"/api/aggregations/([^/]+)/extxyz", path)
            if match is None and path != "/api/structures":
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            limit = MAX_UPLOAD_BYTES if match is None else MAX_REQUEST_BYTES
            # A JSON content type forces a CORS preflight for cross-site pages.
            if not self.headers.get("Content-Type", "").startswith(
                "application/json"
            ):
                self._send_json(
                    {"error": "Expected application/json"},
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                )
                return
            # A body of the stated length only: a missing, negative or
            # malformed length would read until the client stops sending.
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            if length < 0:
                self._send_json(
                    {"error": "Content-Length required"},
                    HTTPStatus.LENGTH_REQUIRED,
                )
                return
            if length > limit:
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
            if match is None:
                self._respond(lambda: _add_file(view, request))
                return
            aggregation_id = unquote(match.group(1))
            self._respond(lambda: view.extxyz_files(aggregation_id, request))

        def _linked(self, path: str) -> None:
            """Stream one file of a linked page.

            The files are static, so the browser may keep them and ask again
            with If-None-Match rather than download them on every visit. The
            ETag changes with the size or the nanosecond modification time,
            also when a file is replaced by an older copy. No charset is
            added: the files are not ours, so the browser reads it from them.

            The sandbox gives the pages an origin of their own: their scripts
            run, but cannot call this server's API or read the viewer's
            browser storage.
            """
            # "/linked/<name>/" serves the entry; without the slash, the
            # page's relative links would miss its directory.
            name, slash, relative = path.partition("/")
            page = view.linked_pages.get(name)
            file = (
                page.file(relative or page.entry) if page and slash else None
            )
            try:
                if file is None:
                    raise FileNotFoundError(path)
                stream = file.open("rb")
            except OSError:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            with stream:
                stat = os.fstat(stream.fileno())
                etag = f'"{stat.st_size:x}-{stat.st_mtime_ns:x}"'
                headers = {
                    "ETag": etag,
                    "Cache-Control": "no-cache",
                    "Content-Security-Policy": LINKED_PAGE_SANDBOX,
                }
                wanted = self.headers.get("If-None-Match", "")
                # Weak comparison, as for If-None-Match: proxies may mark an
                # ETag weak (W/) when they compress the body.
                tags = (
                    tag.strip().removeprefix("W/") for tag in wanted.split(",")
                )
                if etag in tags:
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    for header, value in headers.items():
                        self.send_header(header, value)
                    self.end_headers()
                    return
                content_type = mimetypes.guess_type(file.name)[0]
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type", content_type or "application/octet-stream"
                )
                self.send_header("Content-Length", str(stat.st_size))
                for header, value in headers.items():
                    self.send_header(header, value)
                self.end_headers()
                # The browser may close the tab or cancel the request.
                with contextlib.suppress(
                    BrokenPipeError, ConnectionResetError
                ):
                    shutil.copyfileobj(stream, self.wfile)

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
            for name, value in {**VIEWER_HEADERS, **(headers or {})}.items():
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
    linked_pages: tuple[LinkedPage, ...] = (),
    modes: dict[str, tuple[Modes, ...]] | None = None,
    phonons: dict[str, PhononModel] | None = None,
) -> ThreadingHTTPServer:
    """Build a threaded HTTP server for one open ledger."""
    server = ThreadingHTTPServer(
        (host, port),
        _handler(
            AddedStructures(
                LedgerView(ledger, label, source, linked_pages, modes, phonons)
            ),
            host,
        ),
    )
    server.daemon_threads = True
    return server


def serve(
    path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    linked_pages: tuple[LinkedPage, ...] = (),
) -> None:
    """Serve the homepage for the SQLite ledger at ``path`` until interrupted.

    The ledger is opened read-only: SQLite itself refuses any write.
    """
    ledger = AtomsLedger.open(path, read_only=True)
    for line in linked_page_report(ledger, linked_pages):
        print(line, flush=True)
    server = create_server(
        ledger, str(path), host=host, port=port, linked_pages=linked_pages
    )
    run(server, path, open_browser=open_browser)


def linked_page_report(
    ledger: AtomsLedger, linked_pages: tuple[LinkedPage, ...]
) -> list[str]:
    """One line per linked page, counting manifest IDs this ledger lacks."""
    lines = []
    for page in linked_pages:
        missing = len(
            page.structure_ids - _known_ids(ledger, page.structure_ids)
        )
        line = (
            f"Linked page {page.name!r} ({page.directory}): "
            f"{len(page.structure_ids)} structures"
        )
        if missing:
            line += f", warning: {missing} not in this ledger"
        lines.append(line)
    return lines


def _known_ids(ledger: AtomsLedger, ids: frozenset[str]) -> set[str]:
    """The structure IDs among ``ids`` that the ledger holds.

    The catalog (SQLite ledgers, as ``serve`` opens) reads no geometry;
    batches keep each query below SQLite's limit on bound parameters.
    """
    ordered = sorted(ids)
    known: set[str] = set()
    for start in range(0, len(ordered), ID_BATCH):
        batch = tuple(ordered[start : start + ID_BATCH])
        known.update(
            entry.id
            for entry in ledger.catalog.iter_search(StructureQuery(ids=batch))
        )
    return known


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
