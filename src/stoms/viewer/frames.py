"""ASE structures as the structure JSON the browser viewer draws.

The viewer (``web/static/viewer.js``) draws a *structure*: plain JSON with
``id``, ``symbols``, ``positions``, ``cell`` and ``pbc``, and optional per-atom
``arrays`` for tooltips and colouring. The ledger server builds the same shape
from ledger records; this module builds it from ASE ``Atoms`` directly, with
no ledger. Nothing here imports :mod:`stoms.atomsledger`.

Calculator results are read from ``atoms.calc.results`` only: nothing is
computed, and calculators are never serialized.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np
from ase import Atoms

# More frames than this are refused (as by ``stoms serve --frames``): every
# frame is copied into the page.
MAX_FRAMES = 10_000

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
# ASE's units for calculator results.
CALCULATOR_UNITS = {
    "energy": "eV",
    "free_energy": "eV",
    "energies": "eV",
    "forces": "eV/Å",
    "stress": "eV/Å³",
    "stresses": "eV/Å³",
    "magmom": "μB",
    "magmoms": "μB",
    "charges": "e",
    "dipole": "e·Å",
}


def structure_level(name: str) -> bool:
    """Whether a property name ("stress", "REF_stress", "dft.virial") names
    a property of the whole structure."""
    base = name.rsplit(".", 1)[-1].lower()
    return base in STRUCTURE_LEVEL or any(
        base.endswith(f"_{level}") for level in STRUCTURE_LEVEL
    )


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


def per_atom(value: Any, natoms: int) -> dict[str, Any] | None:
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
    return {
        "kind": "number" if array.ndim == 1 else "vector",
        "values": [
            _finite(v) if array.ndim == 1 else [_finite(c) for c in v]
            for v in values
        ],
    }


def _scalar(value: Any) -> float | int | bool | str | None:
    """A JSON number, bool or string for one plain value, else None."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _finite(value)
    array = np.asarray(value) if isinstance(value, np.ndarray) else None
    if array is not None and array.size == 1 and array.dtype.kind in "biuf":
        return _finite(float(array.reshape(())))
    return None


def _vector(value: Any) -> list[float | None] | None:
    """A short numeric vector (stress, dipole) as a JSON list, else None."""
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return None
    if array.ndim == 0 or array.size > 9:
        return None
    return [_finite(v) for v in np.round(array.ravel(), 6).tolist()]


def frame_payload(atoms: Atoms, index: int) -> dict[str, Any]:
    """The structure JSON for frame ``index`` of the shown images.

    ``arrays`` holds per-atom values (ASE arrays, per-atom lists in
    ``atoms.info`` and per-atom calculator results, such as forces);
    ``properties`` the scalar and short vector values of the whole structure
    (calculator results such as the energy, and numbers in ``atoms.info``).
    """
    if not isinstance(atoms, Atoms):
        raise TypeError(
            f"frame {index} is a {type(atoms).__name__}, not an ase.Atoms"
        )
    natoms = len(atoms)
    positions = np.asarray(atoms.positions, dtype=float)
    cell = np.asarray(atoms.cell.array, dtype=float)
    if not (np.isfinite(positions).all() and np.isfinite(cell).all()):
        raise ValueError(f"frame {index} has non-finite positions or cell")
    arrays: list[dict[str, Any]] = []
    for name in sorted(atoms.arrays):
        if name in STRUCTURE_ARRAYS_SHOWN:
            continue
        values = per_atom(atoms.arrays[name], natoms)
        if values is not None:
            arrays.append({"name": name, "source": "arrays", **values})
    properties: list[dict[str, Any]] = []
    for key, value in sorted(atoms.info.items(), key=lambda kv: str(kv[0])):
        name = str(key)
        if not structure_level(name) and isinstance(
            value, list | tuple | np.ndarray
        ):
            values = per_atom(value, natoms)
            if values is not None:
                arrays.append({"name": name, "source": "info", **values})
                continue
        scalar = _scalar(value)
        if scalar is not None:
            properties.append(
                {"name": name, "source": "info", "value": scalar}
            )
    # Results already computed; get_property would run the calculator.
    results = getattr(atoms.calc, "results", None) or {}
    for name in sorted(results):
        value = results[name]
        unit = CALCULATOR_UNITS.get(name)
        if not structure_level(name):
            values = per_atom(value, natoms)
            if values is not None:
                arrays.append(
                    {
                        "name": name,
                        "source": "calculator",
                        "unit": unit,
                        **values,
                    }
                )
                continue
        scalar = _scalar(value)
        vector = None if scalar is not None else _vector(value)
        if scalar is not None or vector is not None:
            properties.append(
                {
                    "name": name,
                    "source": "calculator",
                    "unit": unit,
                    "value": scalar if scalar is not None else vector,
                }
            )
    return {
        # Unique per frame: the viewer caches bonds by structure ID.
        "id": f"frame-{index}",
        "frame": index,
        "formula": atoms.get_chemical_formula(),
        "numbers": atoms.numbers.tolist(),
        "symbols": atoms.get_chemical_symbols(),
        "positions": np.round(positions, 6).tolist(),
        "cell": np.round(cell, 6).tolist(),
        "pbc": [bool(p) for p in atoms.pbc],
        "mass": float(atoms.get_masses().sum()) if natoms else 0.0,
        "arrays": arrays,
        "properties": properties,
        # Fields of the ledger's structure JSON that the renderer reads.
        "tags": [],
        "evaluations": [],
    }


def as_images(images: Any) -> list[Atoms]:
    """``images`` as a list of Atoms: one Atoms, a sequence or iterable of
    them (an ASE Trajectory, a generator), or a file name read with ASE.

    The Atoms are copied (calculator results kept), so later changes to the
    caller's objects change neither the view nor ``selected_atoms``.
    """
    if isinstance(images, str | os.PathLike):
        from ase.io import read

        images = read(os.fspath(images), index=":")
    if isinstance(images, Atoms):
        images = [images]
    elif isinstance(images, Mapping) or not isinstance(images, Iterable):
        raise TypeError(
            "view() takes an ase.Atoms, a list or trajectory of them, or a "
            f"file name, not a {type(images).__name__}"
        )
    if isinstance(images, Sequence) or hasattr(images, "__len__"):
        count = len(images)  # type: ignore[arg-type]
        if count > MAX_FRAMES:
            raise _too_many(count)
    found: list[Atoms] = []
    for item in images:
        if len(found) == MAX_FRAMES:
            raise _too_many(None)
        if not isinstance(item, Atoms):
            raise TypeError(
                f"frame {len(found)} is a {type(item).__name__}, not an ase.Atoms"
            )
        found.append(_copy(item))
    if not found:
        raise ValueError("there is nothing to view: no frames")
    return found


def _copy(atoms: Atoms) -> Atoms:
    """A copy of ``atoms`` with its calculator results, but no calculator."""
    from ase.calculators.calculator import all_properties
    from ase.calculators.singlepoint import SinglePointCalculator

    copy = atoms.copy()
    results = getattr(atoms.calc, "results", None) or {}
    kept = {
        name: np.array(value) if isinstance(value, np.ndarray) else value
        for name, value in results.items()
        if name in all_properties
    }
    if kept:
        copy.calc = SinglePointCalculator(copy, **kept)
    return copy


def _too_many(count: int | None) -> ValueError:
    many = f"{count:,} frames" if count is not None else "more frames"
    return ValueError(
        f"{many} are too many to show at once (at most {MAX_FRAMES:,}); "
        "pass every n-th frame, for example images[::10]"
    )
