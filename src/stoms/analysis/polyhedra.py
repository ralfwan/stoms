"""Coordination polyhedron of one atom: bond lengths, volume and distortion.

The ligands follow the rule of the structure viewer's polyhedra: the atoms of
a non-metal element (:data:`stoms.analysis.rings.NONMETALS`) bonded to the
centre, that is closer than the bond cutoff of their element pair. Any atom
can be the centre. ``polyhedronOf`` in ``viewer.js`` computes the same
numbers for the viewer's Measure tab.

Distortion measures:

- distortion index (Baur, Acta Cryst. B 30, 1195 (1974)):
  D = (1/n) Σ |l_i − l_av| / l_av;
- quadratic elongation (Robinson, Gibbs and Ribbe, Science 172, 567
  (1971)): <λ> = (1/n) Σ (l_i / l_0)², l_0 the centre-to-vertex distance of
  the regular polyhedron with the same volume;
- bond-angle variance (same paper): σ² = Σ (θ_i − θ_0)² / (m − 1) over the
  m = 6 ligand–centre–ligand angles of a tetrahedron (θ_0 = 109.47°) or the
  m = 12 cis angles of an octahedron (θ_0 = 90°; the 3 largest of the 15
  angles are taken as the trans ones);
- effective coordination number (Hoppe, Z. Kristallogr. 150, 23 (1979)), in
  the form VESTA uses (Momma and Izumi, J. Appl. Cryst. 44, 1272 (2011)):
  ECoN = Σ exp[1 − (l_i / l_w)⁶], l_w = Σ l_i w_i / Σ w_i with
  w_i = exp[1 − (l_i / l_min)⁶].

Quadratic elongation and bond-angle variance are given for 4 and 6 ligands
only (against the regular tetrahedron and octahedron).
"""

from __future__ import annotations

import functools
import math
import numbers
from collections.abc import Mapping
from typing import Any

import numpy as np
from ase import Atoms

from .rings import NONMETALS, default_cutoff, pair_key

__all__ = ["hull_volume", "polyhedron"]


def _hull_faces(points: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Convex hull faces (ordered polygon, outward normal) of a few points;
    ``hullFaces`` in ``viewer.js``, with its tolerances (0.05 Å)."""
    eps = 1e-3
    centroid = points.mean(axis=0)
    planes: dict[str, tuple[np.ndarray, float]] = {}
    n_points = len(points)
    for a in range(n_points):
        for b in range(a + 1, n_points):
            for c in range(b + 1, n_points):
                n = np.cross(points[b] - points[a], points[c] - points[a])
                length = float(np.linalg.norm(n))
                if length < eps:
                    continue
                n = n / length
                if np.dot(n, points[a] - centroid) < 0:
                    n = -n
                d = float(np.dot(n, points[a]))
                if np.any(points @ n - d > 0.05):
                    continue
                # As JavaScript's toFixed(2): -0.0 is "0.00", -0.001 "-0.00".
                key = ",".join(
                    f"{v:.2f}" if v < 0 else f"{abs(v):.2f}" for v in n
                )
                planes.setdefault(key, (n, d))
    faces = []
    for n, d in planes.values():
        on_face = points[np.abs(points @ n - d) < 0.05]
        if len(on_face) < 3:
            continue
        centre = on_face.mean(axis=0)
        u = on_face[0] - centre
        u = u / (np.linalg.norm(u) or 1.0)
        v = np.cross(n, u)
        rel = on_face - centre
        order = np.argsort(np.arctan2(rel @ v, rel @ u), kind="stable")
        faces.append((on_face[order], n))
    return faces


def hull_volume(points: Any) -> float | None:
    """Volume (Å³) of the convex hull of ``points`` (n × 3, Å); None for
    fewer than 4 points or a flat set."""
    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(pts) < 4:
        return None
    centroid = pts.mean(axis=0)
    volume = 0.0
    for face, normal in _hull_faces(pts):
        c = face.mean(axis=0)
        area = 0.0
        for k in range(len(face)):
            area += (
                float(
                    np.dot(
                        normal,
                        np.cross(face[k] - c, face[(k + 1) % len(face)] - c),
                    )
                )
                / 2
            )
        volume += abs(area) * abs(float(np.dot(normal, c - centroid))) / 3
    return volume if volume > 1e-6 else None


def _cutoff_table(
    symbols: list[str], cutoffs: Mapping[str, Any] | None
) -> dict[str, tuple[float, float]]:
    """``(minimum, maximum)`` bond length per element pair of ``symbols``:
    a cutoff is a number (the maximum; minimum 0) or a ``(min, max)`` pair."""
    given = {}
    for pair, value in (cutoffs or {}).items():
        a, b = pair if isinstance(pair, tuple) else str(pair).split("-")
        given[pair_key(a, b)] = bond_range(value)
    species = sorted(set(symbols))
    return {
        pair_key(a, b): given.get(pair_key(a, b), (0.0, default_cutoff(a, b)))
        for a in species
        for b in species
    }


def bond_range(value: Any) -> tuple[float, float]:
    """``(minimum, maximum)`` of a bond cutoff given as a number (the
    maximum) or as ``(min, max)``, in Å."""
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        low, high = 0.0, float(value)
    elif (
        isinstance(value, list | tuple)
        and len(value) == 2
        and all(
            isinstance(v, numbers.Real) and not isinstance(v, bool)
            for v in value
        )
    ):
        low, high = float(value[0]), float(value[1])
    else:
        raise ValueError(
            f"a bond cutoff is a number or (min, max) in Å, not {value!r}"
        )
    if not (
        low >= 0 and math.isfinite(low) and math.isfinite(high) and high >= 0
    ):
        raise ValueError("bond cutoffs are numbers ≥ 0 (Å)")
    if high and low > high:
        raise ValueError(
            f"a bond's minimum ({low:g} Å) is above its maximum ({high:g} Å)"
        )
    return low, high


def search_lattice(
    cell: Any, pbc: Any
) -> tuple[list[bool], np.ndarray] | None:
    """The lattice of the bond search, as ``searchLattice`` in ``viewer.js``:
    the periodic axes (pbc and a non-zero cell vector) and reciprocal vectors
    (rows, without 2π) of the cell with each non-periodic axis replaced by a
    unit vector perpendicular to the periodic ones. The norm of row k is 1 /
    the cell's width perpendicular to the other two axes. None without
    periodic axes or when the periodic vectors are not independent."""
    cell = np.asarray(cell, dtype=float).reshape(3, 3)
    periodic = [
        bool(pbc[k]) and float(np.linalg.norm(cell[k])) > 1e-8
        for k in range(3)
    ]
    count = sum(periodic)
    if not count:
        return None
    basis = cell.copy()
    if count == 2:
        k = periodic.index(False)
        n = np.cross(basis[(k + 1) % 3], basis[(k + 2) % 3])
        basis[k] = n / (np.linalg.norm(n) or 1.0)
    elif count == 1:
        k = periodic.index(True)
        u = cell[k] / np.linalg.norm(cell[k])
        helper = np.array([1.0, 0, 0] if abs(u[0]) < 0.9 else [0, 1.0, 0])
        v = np.cross(u, helper)
        v /= np.linalg.norm(v)
        basis[(k + 1) % 3] = v
        basis[(k + 2) % 3] = np.cross(u, v)
    volume = abs(float(np.dot(basis[0], np.cross(basis[1], basis[2]))))
    if not volume > 1e-8 * float(np.prod(np.linalg.norm(basis, axis=1))):
        return None
    recip = np.array(
        [
            np.cross(basis[1], basis[2]),
            np.cross(basis[2], basis[0]),
            np.cross(basis[0], basis[1]),
        ]
    ) / float(np.dot(basis[0], np.cross(basis[1], basis[2])))
    return periodic, recip


def image_ranges(
    d: np.ndarray,
    cutoff: float,
    lattice: tuple[list[bool], np.ndarray] | None,
    pbc: Any,
) -> list[range]:
    """Cell offsets n along each axis that can bring the vector ``d`` (from
    one atom to another) within ``cutoff``: |f + n| · width < cutoff, f the
    fractional components of d (``neighbours`` in ``viewer.js``)."""
    if lattice is None:
        return [range(-1, 2) if pbc[k] else range(1) for k in range(3)]
    periodic, recip = lattice
    ranges = []
    for k in range(3):
        if not periodic[k]:
            ranges.append(range(1))
            continue
        f = float(np.dot(d, recip[k]))
        r = cutoff * float(np.linalg.norm(recip[k])) + 1e-9
        ranges.append(range(math.ceil(-f - r), math.floor(-f + r) + 1))
    return ranges


def _by_length(a: tuple, b: tuple) -> int:
    if abs(a[0] - b[0]) > 1e-9:
        return -1 if a[0] < b[0] else 1
    first, second = (a[1], *a[2]), (b[1], *b[2])
    return (first > second) - (first < second)


def polyhedron(
    atoms: Atoms,
    index: int,
    cutoffs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The coordination polyhedron of atom ``index`` of ``atoms``.

    ``cutoffs`` maps element pairs ("O-Ti", either order) to bond cutoffs in
    Å: the longest bond, or ``(min, max)`` for a shortest one as well; other
    pairs use :func:`~stoms.analysis.rings.default_cutoff` (no bonds between
    two metals). The ligands are the non-metal atoms at least the minimum
    and less than the cutoff away from the centre, in any periodic image
    (as many cells away as the cutoff reaches, as the viewer's bond
    search).

    Returns a dictionary:

    - ``index``, ``symbol``: the centre;
    - ``cn``: the coordination number (number of ligands);
    - ``ligands``: ``[{"index", "symbol", "image", "length"}]``, shortest
      first (``image``: the ligand's cell offset, integers);
    - ``lengths`` (sorted) and ``mean``: bond lengths in Å;
    - ``volume``: of the ligands' convex hull, Å³ (None below 4 ligands);
    - ``distortion_index``, ``quadratic_elongation``,
      ``bond_angle_variance`` (deg²) and ``econ``: see the module
      docstring; None where not defined (no ligands; quadratic elongation
      and bond-angle variance need 4 or 6 ligands).
    """
    n_atoms = len(atoms)
    if not -n_atoms <= index < n_atoms:
        raise IndexError(f"atom index {index} out of range ({n_atoms} atoms)")
    index = index % n_atoms
    symbols = atoms.get_chemical_symbols()
    table = _cutoff_table(symbols, cutoffs)
    positions = atoms.get_positions()
    cell = np.asarray(atoms.cell[:], dtype=float)
    lattice = search_lattice(cell, atoms.pbc)
    centre = positions[index]
    ligands = []
    for j, symbol in enumerate(symbols):
        if symbol not in NONMETALS:
            continue
        low, cutoff = table[pair_key(symbols[index], symbol)]
        if cutoff <= 0:
            continue
        ranges = image_ranges(
            positions[j] - centre, cutoff, lattice, atoms.pbc
        )
        for i in ranges[0]:
            for jj in ranges[1]:
                for kk in ranges[2]:
                    if j == index and i == jj == kk == 0:
                        continue
                    to = (
                        positions[j]
                        + i * cell[0]
                        + jj * cell[1]
                        + kk * cell[2]
                    )
                    length = float(np.linalg.norm(to - centre))
                    if low <= length < cutoff:
                        ligands.append((length, j, (i, jj, kk), to))
    # Shortest first; lengths within 1e-9 Å count as equal (by atom, image),
    # as in viewer.js.
    ligands.sort(key=functools.cmp_to_key(_by_length))
    lengths = [item[0] for item in ligands]
    n = len(lengths)
    result: dict[str, Any] = {
        "index": index,
        "symbol": symbols[index],
        "cn": n,
        "ligands": [
            {
                "index": j,
                "symbol": symbols[j],
                "image": list(image),
                "length": length,
            }
            for length, j, image, _ in ligands
        ],
        "lengths": lengths,
        "mean": sum(lengths) / n if n else None,
        "volume": None,
        "distortion_index": None,
        "quadratic_elongation": None,
        "bond_angle_variance": None,
        "econ": None,
    }
    if not n:
        return result
    mean = result["mean"]
    result["distortion_index"] = sum(abs(x - mean) for x in lengths) / (
        n * mean
    )
    shortest = lengths[0]
    weights = [math.exp(1 - (x / shortest) ** 6) for x in lengths]
    weighted = sum(x * w for x, w in zip(lengths, weights, strict=True)) / sum(
        weights
    )
    result["econ"] = sum(math.exp(1 - (x / weighted) ** 6) for x in lengths)
    vertices = np.array([item[3] for item in ligands])
    volume = hull_volume(vertices)
    result["volume"] = volume
    if n in (4, 6) and volume:
        # Centre-to-vertex distance of the regular polyhedron of this volume:
        # V = 8 l0³ / (9√3) (tetrahedron), 4 l0³ / 3 (octahedron).
        if n == 4:
            l0 = (9 * math.sqrt(3) * volume / 8) ** (1 / 3)
        else:
            l0 = (3 * volume / 4) ** (1 / 3)
        result["quadratic_elongation"] = (
            sum((x / l0) ** 2 for x in lengths) / n
        )
        bonds = vertices - centre
        angles = []
        for a in range(n):
            for b in range(a + 1, n):
                cosine = np.dot(bonds[a], bonds[b]) / (
                    np.linalg.norm(bonds[a]) * np.linalg.norm(bonds[b])
                )
                angles.append(
                    math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
                )
        angles.sort()
        used = angles if n == 4 else angles[:12]
        ideal = math.degrees(math.acos(-1 / 3)) if n == 4 else 90.0
        result["bond_angle_variance"] = sum((a - ideal) ** 2 for a in used) / (
            len(used) - 1
        )
    return result
