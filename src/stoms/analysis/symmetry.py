"""Space group, Wyckoff positions and equivalent atoms of a crystal (spglib).

spglib is an optional dependency: ``pip install "stoms[symmetry]"``. Without
it, :func:`symmetry` raises an ``ImportError`` that names the extra, and the
viewers leave symmetry out (with a hint in the ledger viewer's Info tab).

Only structures with a 3D cell (periodic along a, b and c, with a volume)
have a space group; for molecules and slabs (a non-periodic axis) the result
says why it does not apply. Layer groups of slabs are not attempted.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from ase import Atoms

__all__ = [
    "DEFAULT_TOLERANCE",
    "INSTALL_HINT",
    "SymmetryResult",
    "symmetry",
    "symmetry_available",
]

# Distance tolerance (Å) of spglib's symmetry search (its ``symprec``).
DEFAULT_TOLERANCE = 0.01
# The range the viewers accept (MIN_SYMMETRY_TOLERANCE and
# MAX_SYMMETRY_TOLERANCE in viewer.js).
MIN_TOLERANCE = 1e-5
MAX_TOLERANCE = 1.0
INSTALL_HINT = (
    "Symmetry needs the optional extra stoms[symmetry]: pip install "
    '"stoms[symmetry]" (or uvx --from "stoms[symmetry]" stoms …)'
)

# Last space-group number of each crystal system.
_CRYSTAL_SYSTEMS = (
    (2, "triclinic"),
    (15, "monoclinic"),
    (74, "orthorhombic"),
    (142, "tetragonal"),
    (167, "trigonal"),
    (194, "hexagonal"),
    (230, "cubic"),
)


@dataclass(frozen=True)
class SymmetryResult:
    """Symmetry of one structure at one tolerance.

    ``applicable`` is False for structures without a 3D cell (``reason``
    says why); the space-group fields are then None and the per-atom tuples
    empty. When spglib finds no symmetry (overlapping atoms, say),
    ``reason`` holds its message.

    Per atom (in the structure's order): ``wyckoffs`` the Wyckoff letter,
    ``site_symmetries`` the site-symmetry symbol, ``equivalent_atoms`` the
    index of the first atom of the same orbit (atoms with the same value are
    symmetry-equivalent).
    """

    tolerance: float
    applicable: bool
    reason: str | None = None
    international: str | None = None
    number: int | None = None
    crystal_system: str | None = None
    hall: str | None = None
    point_group: str | None = None
    wyckoffs: tuple[str, ...] = ()
    site_symmetries: tuple[str, ...] = ()
    equivalent_atoms: tuple[int, ...] = ()

    @property
    def symbol(self) -> str | None:
        """Space group as "Fd-3m (227)", or None."""
        if self.international is None:
            return None
        return f"{self.international} ({self.number})"

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON (the viewers read this)."""
        data = asdict(self)
        for key in ("wyckoffs", "site_symmetries", "equivalent_atoms"):
            data[key] = list(data[key])
        return data


def _spglib() -> Any:
    try:
        import spglib
    except ImportError as error:
        raise ImportError(INSTALL_HINT) from error
    return spglib


def symmetry_available() -> bool:
    """Whether spglib can be imported (the ``symmetry`` extra)."""
    try:
        _spglib()
    except ImportError:
        return False
    return True


def crystal_system(number: int) -> str:
    """Crystal system of space group ``number`` (1 to 230)."""
    for last, name in _CRYSTAL_SYSTEMS:
        if number <= last:
            return name
    raise ValueError(f"no space group {number}")


def check_tolerance(tolerance: Any) -> float:
    """``tolerance`` as a float in [MIN_TOLERANCE, MAX_TOLERANCE] Å."""
    if isinstance(tolerance, bool):
        raise TypeError("the symmetry tolerance is a number (Å)")
    value = float(tolerance)
    if not (math.isfinite(value) and MIN_TOLERANCE <= value <= MAX_TOLERANCE):
        raise ValueError(
            f"the symmetry tolerance is {MIN_TOLERANCE:g} to "
            f"{MAX_TOLERANCE:g} Å, not {tolerance!r}"
        )
    return value


def symmetry(
    atoms: Atoms, tolerance: float = DEFAULT_TOLERANCE
) -> SymmetryResult:
    """Space group, crystal system and per-atom Wyckoff letters, site
    symmetries and equivalent atoms of ``atoms`` (spglib, ``symprec`` =
    ``tolerance`` in Å; default 0.01 Å).

    Raises ImportError (naming the ``stoms[symmetry]`` extra) without
    spglib. Structures without a 3D cell give ``applicable=False``.
    """
    spglib = _spglib()
    tolerance = check_tolerance(tolerance)
    if not all(atoms.pbc):
        axes = "".join(
            "abc"[k] for k, periodic in enumerate(atoms.pbc) if not periodic
        )
        return SymmetryResult(
            tolerance,
            False,
            f"not periodic along {axes}: no 3D cell, so no space group "
            "(layer groups of slabs are not computed)",
        )
    cell = np.asarray(atoms.cell.array, dtype=float)
    if abs(np.linalg.det(cell)) < 1e-6:
        return SymmetryResult(
            tolerance, False, "the cell has no volume: no space group"
        )
    if not len(atoms):
        return SymmetryResult(tolerance, False, "no atoms")
    message = "no symmetry found"
    # spglib 2.5+ warns about its old error handling (None and an error
    # message) on every call; both kinds of failure are handled here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            dataset = spglib.get_symmetry_dataset(
                (cell, atoms.get_scaled_positions(wrap=True), atoms.numbers),
                symprec=tolerance,
            )
        except spglib.SpglibError as error:
            dataset, message = None, str(error) or message
        if dataset is None and message == "no symmetry found":
            message = spglib.get_error_message() or message
    if dataset is None:
        return SymmetryResult(
            tolerance, True, f"spglib found no space group: {message}"
        )
    number = int(dataset.number)
    return SymmetryResult(
        tolerance=tolerance,
        applicable=True,
        international=str(dataset.international),
        number=number,
        crystal_system=crystal_system(number),
        hall=str(dataset.hall),
        point_group=str(dataset.pointgroup).strip(),
        wyckoffs=tuple(str(w) for w in dataset.wyckoffs),
        site_symmetries=tuple(
            str(s).strip() for s in dataset.site_symmetry_symbols
        ),
        equivalent_atoms=tuple(int(i) for i in dataset.equivalent_atoms),
    )


def symmetry_payload(
    atoms: Atoms, tolerance: float = DEFAULT_TOLERANCE
) -> dict[str, Any]:
    """What the viewers read: ``{"available": False, "install": hint}``
    without spglib, else the result's JSON with ``"available": True``."""
    try:
        result = symmetry(atoms, tolerance)
    except ImportError:
        return {"available": False, "install": INSTALL_HINT}
    return {"available": True, **result.to_dict()}
