"""Load one extxyz file into a ledger so the homepage can show it.

Every frame becomes its own structure, in file order, even when frames repeat:
the file is shown as given. A frame's energy, forces and other labelled
properties become at most one evaluation of that frame. The frames form one
aggregation named after the file.

Evaluations are found in three forms:

- Files exported by STOMS (``atomsledger_*`` keys) keep their method, units
  and tags; the energy and forces labels (``REF_`` by default) and ``eval_``
  properties are read back.
- Labelled properties such as ``REF_energy`` and ``REF_forces``: the label is
  the method and the properties are named without it.
- Plain ``energy``, ``forces`` and ``stress``, which ASE reads as calculator
  results.

Frames with several of these, for example both ``REF_`` and ``MACE_``
properties, are not supported yet.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.io import Trajectory, read
from ase.io.formats import UnknownFileTypeError, filetype, string2index

from ..atomsledger import (
    Aggregation,
    AggregationMemberInput,
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)
from ..atomsledger.exceptions import SerializationError
from ..atomsledger.serialization import json_dumps
from .access import AccessOptions

CREATED_BY = "stoms serve"
# ASE's extxyz conventions; STOMS exports carry their own units.
DEFAULT_UNITS = {
    "energy": "eV",
    "free_energy": "eV",
    "forces": "eV/angstrom",
    "stress": "eV/angstrom^3",
    "node_energy": "eV",
}
STOMS_PREFIX = "atomsledger_"
STOMS_EVALUATION_KEYS = {
    "atomsledger_evaluation_id",
    "atomsledger_evaluation_hash",
    "atomsledger_evaluation_created_at",
    "atomsledger_method_family",
    "atomsledger_method_name",
    "atomsledger_evaluator_label",
    "atomsledger_units",
    "atomsledger_evaluation_tags",
    "atomsledger_method_version",
    "atomsledger_method_code",
    "atomsledger_method_identifier",
    "atomsledger_exported_properties",
}
# A label is the part before "_energy" (info) or "_forces" (arrays).
LABEL_ENERGY = re.compile(r"^(.+?)_energy$")
LABEL_FORCES = re.compile(r"^(.+?)_forces$")


# More frames than this are read only when chosen (``frames``): copying every
# frame into the ledger takes about 1.5 ms each, and the pages list them all.
MAX_FRAMES = 10_000


class ExtxyzLoadError(ValueError):
    """The file cannot be shown, for example a frame has several evaluations."""


def frame_selection(frames: str) -> int | slice:
    """``frames`` in ASE's index syntax (``:500``, ``::100``, ``-200:``, ``7``)."""
    try:
        selection = string2index(frames)
    except ValueError:
        selection = None
    # ASE passes other text on unchanged (some formats name their frames).
    if not isinstance(selection, int | slice):
        raise ExtxyzLoadError(
            f"--frames {frames!r} is not a frame, or a slice such as "
            "':500' (the first 500), '::100' (every 100th) or '-200:' "
            "(the last 200)"
        )
    return selection


def _frame_count(path: Path, file_format: str | None) -> int | None:
    """Frames in ``path`` without reading them, for ASE trajectories and
    extxyz; None for other formats (read in full to count)."""
    try:
        kind = file_format or filetype(str(path), read=True)
    except Exception:  # unknown: reading reports it
        return None
    if kind == "traj":
        try:
            with Trajectory(str(path)) as trajectory:
                return len(trajectory)
        except Exception:  # malformed: reading reports it
            return None
    if kind in ("extxyz", "xyz"):
        spans = _frame_spans(path)
        return len(spans) if spans is not None else None
    return None


def _chosen(total: int, selection: int | slice) -> list[int]:
    """File frame numbers that ``selection`` picks out of ``total`` frames."""
    if isinstance(selection, slice):
        return list(range(total)[selection])
    if not -total <= selection < total:
        raise ExtxyzLoadError(
            f"there is no frame {selection}: the file has {total}"
        )
    return [range(total)[selection]]


def load_extxyz(
    ledger: AtomsLedger,
    path: Path,
    *,
    file_format: str | None = "extxyz",
    name: str | None = None,
    frames: str | None = None,
) -> Aggregation:
    """Add every frame of ``path`` to ``ledger``; return the file's aggregation.

    ``file_format`` None lets ASE choose the format from the file (POSCAR,
    CIF, OUTCAR, ...); ``name`` names the aggregation instead of the file.
    ``frames`` (ASE's index syntax, see frame_selection) reads only those
    frames; each is tagged ``frame:<number in the file>``. Without it, a file
    of more than MAX_FRAMES frames is refused.
    """
    selection = frame_selection(frames) if frames is not None else None
    total = _frame_count(path, file_format)
    if selection is None and total is not None and total > MAX_FRAMES:
        raise _too_many(path, total)
    # Trajectories and extxyz read only the chosen frames; other formats are
    # read in full and the frames picked afterwards.
    chosen = (
        None
        if total is None or selection is None
        else _chosen(total, selection)
    )
    try:
        if chosen is not None:
            read_frames = (
                read(str(path), index=selection, format=file_format)
                if chosen
                else []
            )
        else:
            read_frames = read(str(path), index=":", format=file_format)
    except UnknownFileTypeError as error:
        # ASE says only the type it does not know, for example "yaml".
        hint = (
            f"; phonopy input is viewed with `stoms --file {path.name} serve`"
            if path.suffix.lower() in (".yaml", ".yml")
            else ""
        )
        raise ExtxyzLoadError(
            f"cannot read {path.name}: not a structure file ASE knows "
            f"(extxyz, xyz, POSCAR/CONTCAR, CIF, OUTCAR, vasprun.xml, …){hint}"
        ) from error
    except Exception as error:  # ASE raises many types for malformed files
        kind = f" as {file_format}" if file_format else ""
        raise ExtxyzLoadError(
            f"cannot read {path.name}{kind}: {error}"
        ) from error
    if not isinstance(read_frames, list):
        read_frames = [read_frames]
    if total is None:
        total = len(read_frames)
        if selection is None and total > MAX_FRAMES:
            raise _too_many(path, total)
        if selection is not None:
            chosen = _chosen(total, selection)
            read_frames = [read_frames[i] for i in chosen]
    numbers = chosen if chosen is not None else list(range(len(read_frames)))
    if not read_frames:
        raise ExtxyzLoadError(
            f"--frames {frames} picks none of the {total} frames of {path.name}"
            if selection is not None
            else f"{path} contains no frames"
        )

    source = StructureSourceSpec(
        kind="file", name=name or path.name, tool=file_format or "ase"
    )
    structures = []
    evaluations: dict[int, dict[str, Any]] = {}
    for index, (number, frame) in enumerate(
        zip(numbers, read_frames, strict=True)
    ):
        structure, provenance, evaluation = _split_frame(
            frame, number, path, chosen=selection is not None
        )
        structures.append({"atoms": structure, "provenance": provenance})
        if evaluation is not None:
            evaluations[index] = evaluation

    # The frame index in each provenance keeps repeated frames apart.
    structure_ids = ledger.add_structures(
        structures, source_spec=source, allow_equivalent_atoms=True
    )
    if len(set(structure_ids)) != len(read_frames):
        raise ExtxyzLoadError(
            "frames were merged; every frame must stay a record"
        )
    evaluation_ids = dict(
        zip(
            evaluations,
            ledger.add_evaluations(
                [
                    {"structure_id": structure_ids[index], **evaluation}
                    for index, evaluation in evaluations.items()
                ]
            ),
            strict=True,
        )
    )
    members = [
        AggregationMemberInput(structure_id, evaluation_ids.get(index))
        for index, structure_id in enumerate(structure_ids)
    ]
    picked = (
        f"Frames {frames} of {total}" if selection is not None else "Frames"
    )
    return ledger.create_aggregation(
        name=name or path.name,
        description=f"{picked} of {path}, in file order",
        members=members,
        metadata={
            "file": str(path),
            "frames": len(read_frames),
            **(
                {"selection": frames, "file_frames": total}
                if selection is not None
                else {}
            ),
        },
    )


def _too_many(path: Path, total: int) -> ExtxyzLoadError:
    step = -(-total // 1000)
    return ExtxyzLoadError(
        f"{path.name} has {total:,} frames, more than {MAX_FRAMES:,} at once; "
        f"choose some with `stoms --file {path.name} serve --frames ::{step}` "
        f"(every {step}th frame), `--frames :1000` (the first 1000) or "
        "`--frames -1000:` (the last 1000)"
    )


@dataclass(frozen=True)
class ExtxyzSource:
    """Where each frame of a served file sits, for verbatim exports.

    ``spans`` holds the byte range of every frame in file order, so frame
    ``i`` is aggregation member ``i``; ``frames`` maps structure IDs to frame
    indices. Without spans (an unusual layout) exports go through the ledger.
    """

    path: Path
    aggregation_id: str
    frames: dict[str, int]
    spans: tuple[tuple[int, int], ...] | None

    def text(self, indices: list[int]) -> bytes:
        """The given frames, byte for byte, in the given order."""
        if self.spans is None:
            raise ExtxyzLoadError(
                "frames of this file cannot be copied verbatim"
            )
        chunks = []
        with self.path.open("rb") as stream:
            for index in indices:
                start, end = self.spans[index]
                stream.seek(start)
                chunk = stream.read(end - start)
                chunks.append(
                    chunk if chunk.endswith(b"\n") else chunk + b"\n"
                )
        return b"".join(chunks)


def extxyz_source(path: Path, aggregation: Aggregation) -> ExtxyzSource:
    """Locate the frames of ``path``, loaded as ``aggregation`` (all of them,
    or those its ``selection`` chose)."""
    spans = _frame_spans(path)
    selection = aggregation.metadata.get("selection")
    if spans is not None and selection is not None:
        spans = tuple(
            spans[i] for i in _chosen(len(spans), frame_selection(selection))
        )
    if spans is not None and len(spans) != len(aggregation.members):
        spans = None
    return ExtxyzSource(
        path=path,
        aggregation_id=aggregation.id,
        frames={m.structure_id: m.ordinal for m in aggregation.members},
        spans=spans,
    )


def _frame_spans(path: Path) -> tuple[tuple[int, int], ...] | None:
    """Byte range of each frame: atom count line, comment line, atom lines.

    Blank lines between frames are skipped, as ASE does. ``None`` if the file
    does not follow this layout.
    """
    spans: list[tuple[int, int]] = []
    with path.open("rb") as stream:
        while True:
            start = stream.tell()
            line = stream.readline()
            if not line:
                return tuple(spans)
            if not line.strip():
                continue
            try:
                count = int(line.split()[0])
            except ValueError:
                return None
            for _ in range(count + 1):
                if not stream.readline():
                    return None
            spans.append((start, stream.tell()))


def serve_extxyz(
    path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    frames: str | None = None,
    access: AccessOptions | None = None,
) -> None:
    """Serve the homepage for one extxyz file until interrupted.

    Another format ASE recognises by name or content (traj, POSCAR, CIF, ...)
    is read as that format; ``frames`` chooses some of its frames (see
    load_extxyz). The frames live in a temporary ledger that is deleted on
    exit; the file itself is only read.
    """
    from .server import create_server, run

    file_format = served_format(path)
    with tempfile.TemporaryDirectory(prefix="stoms-extxyz-") as directory:
        ledger = AtomsLedger(Path(directory) / "view.ledger")
        aggregation = load_extxyz(
            ledger, path, file_format=file_format, frames=frames
        )
        if frames is not None:
            print(
                f"{path.name}: showing {len(aggregation.members):,} of "
                f"{aggregation.metadata['file_frames']:,} frames ({frames})",
                flush=True,
            )
        server = create_server(
            ledger,
            str(path),
            host=host,
            port=port,
            access=access,
            # Only extxyz frames can be copied byte for byte into exports.
            source=(
                extxyz_source(path, aggregation)
                if file_format == "extxyz"
                else None
            ),
        )
        run(
            server,
            path,
            open_browser=open_browser,
            page=f"#/aggregations/{aggregation.id}",
        )


def served_format(path: Path) -> str | None:
    """``extxyz`` for an extxyz file, or None to let ASE choose the format.

    A file named .extxyz or .xyz, or whose first frame reads as extxyz, is
    extxyz, so its errors stay extxyz errors; ASE's guess by name alone can
    be wrong (it takes a .dat file for GAMESS output).
    """
    if path.suffix.lower() in (".extxyz", ".xyz"):
        return "extxyz"
    try:
        read(str(path), index=0, format="extxyz")
    except Exception:  # ASE raises many types for other files
        return None
    return "extxyz"


def _split_frame(
    frame: Atoms, index: int, path: Path, *, chosen: bool = False
) -> tuple[Atoms, Provenance, dict[str, Any] | None]:
    """Separate one frame into structure, its provenance and its evaluation.

    ``index`` is the frame's number in the file; ``chosen`` (some frames of
    the file) also tags it ``frame:<index>``, which labels it in the viewer.
    """
    info = dict(frame.info)
    results = dict(frame.calc.results) if frame.calc is not None else {}
    stoms = STOMS_EVALUATION_KEYS & info.keys()
    labels = {
        match.group(1)
        for key in info
        if not key.startswith(STOMS_PREFIX)
        and (match := LABEL_ENERGY.match(key))
    } | {
        match.group(1)
        for key in frame.arrays
        if (match := LABEL_FORCES.match(key))
    }
    sources = sorted(labels) + (["calculator results"] if results else [])
    if len(sources) > 1:
        raise ExtxyzLoadError(
            f"frame {index} has several evaluations ({', '.join(sources)}); "
            "files with more than one evaluation per frame are not supported yet"
        )

    structure = frame.copy()
    structure.calc = None
    properties: dict[str, Any] = {}
    label = labels.pop() if labels else None
    if label is not None:
        prefix = f"{label}_"
        for key in list(structure.info):
            if key.startswith(prefix):
                properties[key[len(prefix) :]] = structure.info.pop(key)
        for key in list(structure.arrays):
            if key.startswith(prefix):
                properties[key[len(prefix) :]] = structure.arrays.pop(key)
    if stoms:
        for key in list(structure.info):
            if key.startswith("eval_"):
                properties[key[len("eval_") :]] = structure.info.pop(key)
        for key in list(structure.arrays):
            if key.startswith("eval_"):
                properties[key[len("eval_") :]] = structure.arrays.pop(key)
    properties.update(results)

    exported = {
        key: structure.info.pop(key)
        for key in list(structure.info)
        if key.startswith(STOMS_PREFIX)
    }
    tags = _split_tags(exported.get("atomsledger_structure_tags"))
    if chosen:
        tags = (*tags, f"frame:{index}")
    metadata: dict[str, Any] = {"file": str(path), "frame": index}
    # What stays on the structure is stored as JSON info and plain arrays:
    # info values of other types (such as a CIF reader's spacegroup object)
    # are left out and named in the metadata, and text columns are stored as
    # strings. Values JSON cannot hold (NaN) still fail with a clear error.
    dropped = []
    for key in list(structure.info):
        try:
            json_dumps(structure.info[key])
        except (SerializationError, TypeError):
            del structure.info[key]
            dropped.append(str(key))
        except ValueError:
            pass
    if dropped:
        metadata["dropped_info"] = dropped
    for key, array in list(structure.arrays.items()):
        if array.dtype == object:
            structure.arrays[key] = array.astype(str)
    for key in (
        "atomsledger_structure_id",
        "atomsledger_structure_created_at",
    ):
        if key in exported:
            metadata[key.removeprefix(STOMS_PREFIX)] = exported[key]
    provenance = Provenance(
        created_by=CREATED_BY,
        purpose=str(
            exported.get("atomsledger_structure_purpose")
            or f"frame {index} of {path.name}"
        ),
        tags=tags,
        metadata=metadata,
    )
    if not properties:
        return structure, provenance, None

    evaluation = {
        "method": _method(exported, label),
        "properties": {
            name: _plain(value) for name, value in properties.items()
        },
        "units": _units(exported, properties),
        "provenance": Provenance(
            created_by=CREATED_BY,
            purpose=f"properties of frame {index} of {path.name}",
            tags=_split_tags(exported.get("atomsledger_evaluation_tags")),
            metadata={
                "file": str(path),
                "frame": index,
                "label": label,
                **(
                    {"evaluation_id": exported["atomsledger_evaluation_id"]}
                    if "atomsledger_evaluation_id" in exported
                    else {}
                ),
            },
        ),
    }
    return structure, provenance, evaluation


def _method(exported: dict[str, Any], label: str | None) -> MethodSpec:
    """The exported method, else one named after the label."""
    if "atomsledger_method_name" in exported:
        name = str(exported["atomsledger_method_name"])
        return MethodSpec(
            method_identifier=str(
                exported.get("atomsledger_method_identifier") or name
            ),
            family=str(exported.get("atomsledger_method_family") or "unknown"),
            name=name,
            version=_optional(exported.get("atomsledger_method_version")),
            code=_optional(exported.get("atomsledger_method_code")),
        )
    name = label or "extxyz"
    return MethodSpec(method_identifier=name, family="unknown", name=name)


def _units(
    exported: dict[str, Any], properties: dict[str, Any]
) -> dict[str, str]:
    units = exported.get("atomsledger_units")
    if isinstance(units, str):
        try:
            units = json.loads(units)
        except json.JSONDecodeError:
            units = None
    if not isinstance(units, dict):
        units = DEFAULT_UNITS
    return {name: str(units[name]) for name in properties if name in units}


def _split_tags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(
        tag for tag in (part.strip() for part in value.split(",")) if tag
    )


def _optional(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _plain(value: Any) -> Any:
    """Numpy scalars as Python numbers; arrays stay arrays."""
    if isinstance(value, np.generic):
        return value.item()
    return value
