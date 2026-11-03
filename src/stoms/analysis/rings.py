"""Rings of an atomic network, for any structure.

The network is a chosen set of atoms (by element, and optionally by a height
window per element along the surface normal ``a x b``) bonded when closer than
a cutoff per element pair, across periodic images. Two methods find rings:

``"planar"``
    For layers, surfaces, overlayers and 2D materials. Dangling atoms and
    chains are pruned (the network's 2-core); the rings are the faces of the
    network drawn in the a-b plane, traced by turning at every atom to the next
    bond clockwise from the one arrived by. A face whose walk ends displaced by
    a lattice vector wraps around the cell (an open face: a channel, not a
    ring); one that circles clockwise is the outline of an island of the
    network. Pruned and unbonded network atoms are enclosed by the smallest
    ring around them (labelled ``"6+1Cu"``). Network atoms on top of each
    other in the a-b plane (as the two S layers of MoS2) make the faces
    ambiguous; the result then carries a warning, and height windows that keep
    one layer help.

``"shortest-path"``
    For any network, also 3D (bulk crystals, zeolites, amorphous solids):
    Guttman's criterion. For every atom and every pair of its neighbours,
    each shortest path between the two neighbours that avoids the atom closes
    a ring; rings up to ``max_size`` atoms are searched.

A ring's size counts its atoms (``count="all"``), its atom pairs (``"pairs"``:
half the atoms, rounded up, so a ring of 5 A and 5 B atoms is a 5-ring), or the
atoms of
one element (an element symbol). ``"auto"`` counts pairs when every bond of the
network joins two different elements (as in Cu-O or Si-O networks) and atoms
otherwise.

The planar method follows ``ringnet.py`` (rings of Cu-O overlayers counted in
Cu atoms), generalised to any elements.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from ase import Atoms
from ase.data import atomic_numbers, covalent_radii
from ase.neighborlist import neighbor_list

Method = Literal["planar", "shortest-path"]
Image = tuple[int, int, int]


@dataclass(frozen=True)
class Ring:
    """One ring: its size and label, atoms in ring order with the periodic
    image of each, and its corner positions (Angstrom) moved so that the
    ring's centre lies in the cell."""

    size: int
    label: str
    atoms: tuple[int, ...]
    images: tuple[Image, ...]
    points: np.ndarray = field(repr=False, compare=False)
    # Area in the a-b plane (planar method only).
    area: float | None = None
    # Atoms enclosed by the ring (planar method only).
    inside: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "label": self.label,
            "atoms": list(self.atoms),
            "images": [list(image) for image in self.images],
            "points": np.round(self.points, 4).tolist(),
            "area": None if self.area is None else round(self.area, 4),
            "inside": list(self.inside),
        }


@dataclass(frozen=True)
class RingResult:
    """Rings of a network, smallest first, and facts about the network."""

    rings: tuple[Ring, ...]
    method: Method
    # What a size counts, for example "atoms", "Cu-O pairs" or "Cu atoms".
    unit: str
    # Network atoms, bonds between them, and (planar) pruned atoms, how many
    # of those are enclosed by a ring, and faces that wrap around the cell.
    network: int
    bonds: int
    pruned: int = 0
    enclosed: int = 0
    open_faces: tuple[tuple[int, ...], ...] = ()
    # Why the rings may be wrong (planar: atoms on top of each other).
    warnings: tuple[str, ...] = ()

    @property
    def signature(self) -> str:
        """Ring labels by size, then "ch" per open face: "4,4,8+1Cu,ch"."""
        return ",".join(
            [ring.label for ring in self.rings] + ["ch"] * len(self.open_faces)
        )

    def counts(self) -> dict[int, int]:
        """Number of rings per size."""
        sizes: dict[int, int] = {}
        for ring in self.rings:
            sizes[ring.size] = sizes.get(ring.size, 0) + 1
        return dict(sorted(sizes.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "unit": self.unit,
            "network": self.network,
            "bonds": self.bonds,
            "pruned": self.pruned,
            "enclosed": self.enclosed,
            "open_faces": [list(face) for face in self.open_faces],
            "warnings": list(self.warnings),
            "signature": self.signature,
            "counts": {str(size): n for size, n in self.counts().items()},
            "rings": [ring.to_dict() for ring in self.rings],
        }


# Elements that bond by default; pairs of two other elements (metals) do not,
# as in the structure viewer.
NONMETALS = frozenset(
    [
        "H",
        "He",
        "B",
        "C",
        "N",
        "O",
        "F",
        "Ne",
        "Si",
        "P",
        "S",
        "Cl",
        "Ar",
        "Ge",
        "As",
        "Se",
        "Br",
        "Kr",
        "Sb",
        "Te",
        "I",
        "Xe",
    ]
)


def default_cutoff(a: str, b: str) -> float:
    """Bond cutoff for an element pair: 1.15 x the sum of covalent radii, or
    0 (no bond) between two metals, as in the structure viewer."""
    if a not in NONMETALS and b not in NONMETALS:
        return 0.0
    radii = (
        covalent_radii[atomic_numbers[a]] + covalent_radii[atomic_numbers[b]]
    )
    return round(float(1.15 * radii), 2)


def pair_key(a: str, b: str) -> str:
    """The cutoffs key of an element pair: "Cu-O" (symbols sorted)."""
    return "-".join(sorted((a, b)))


def surface_normal(cell: np.ndarray) -> np.ndarray:
    normal = np.cross(cell[0], cell[1])
    length = np.linalg.norm(normal)
    return normal / length if length else np.array([0.0, 0.0, 1.0])


def find_rings(
    atoms: Atoms,
    *,
    elements: Iterable[str] | None = None,
    heights: Mapping[str, tuple[float | None, float | None]] | None = None,
    cutoffs: Mapping[str, float] | None = None,
    alternating: bool = False,
    count: str = "auto",
    method: Method = "planar",
    enclosed: bool = True,
    max_size: int = 12,
) -> RingResult:
    """Find the rings of a network of ``atoms``.

    ``elements`` chooses the network's elements (all by default); ``heights``
    limits an element to a window (low, high; None = open) of heights along the
    surface normal, in Angstrom. ``cutoffs`` maps element pairs ("Cu-O", in
    either order) to bond cutoffs in Angstrom; other pairs use
    :func:`default_cutoff` (no bonds between two metals), and 0 means no bond.
    With ``alternating`` (and more than one element) only atoms of different
    elements bond.
    """
    if method not in ("planar", "shortest-path"):
        raise ValueError(f"unknown ring method {method!r}")
    symbols = atoms.get_chemical_symbols()
    positions = atoms.positions
    cell = np.asarray(atoms.cell.array, dtype=float)
    normal = surface_normal(cell)
    wanted = set(elements) if elements is not None else set(symbols)
    windows = dict(heights or {})
    nodes = []
    for index, symbol in enumerate(symbols):
        if symbol not in wanted:
            continue
        low, high = windows.get(symbol, (None, None))
        height = float(positions[index] @ normal)
        if (low is None or height >= low) and (high is None or height <= high):
            nodes.append(index)
    present = {symbols[i] for i in nodes}
    different_only = alternating and len(present) > 1
    lookup = {
        pair_key(*key.split("-")): float(value)
        for key, value in (cutoffs or {}).items()
    }
    periodic = [bool(p) for p in atoms.pbc]
    if method == "planar":
        periodic[2] = False  # the a-b plane only
    adjacency, bonds = _network(
        positions[nodes] if nodes else np.zeros((0, 3)),
        [symbols[i] for i in nodes],
        cell,
        periodic,
        lambda a, b: lookup.get(pair_key(a, b), default_cutoff(a, b)),
        different_only,
    )
    # "auto" counts pairs when every bond joins the two elements (as Cu-O).
    alternates = len(present) == 2 and all(
        symbols[nodes[u]] != symbols[nodes[v]]
        for u, edges in enumerate(adjacency)
        for v, _, _ in edges
    )
    pairs = count == "pairs" or (count == "auto" and alternates and bonds > 0)
    if pairs:
        unit = f"{'-'.join(sorted(present))} pairs"
    elif count in ("all", "auto"):
        unit = "atoms"
    else:
        unit = f"{count} atoms"

    def size_of(walk: list[int]) -> int:
        if pairs:
            return (len(walk) + 1) // 2
        if count in ("all", "auto"):
            return len(walk)
        return sum(symbols[i] == count for i in walk)

    if method == "planar":
        return _planar(
            atoms, nodes, adjacency, bonds, size_of, unit, enclosed, cell
        )
    return _shortest_paths(
        atoms, nodes, adjacency, bonds, size_of, unit, max_size, cell, periodic
    )


# Half-edges per network node: (neighbour node, image shift, bond vector).
Adjacency = list[list[tuple[int, Image, np.ndarray]]]


def _network(
    positions: np.ndarray,
    symbols: list[str],
    cell: np.ndarray,
    periodic: list[bool],
    cutoff: Any,
    different_only: bool,
) -> tuple[Adjacency, int]:
    """Bonds of the network nodes, across periodic images."""
    count = len(symbols)
    adjacency: Adjacency = [[] for _ in range(count)]
    if count < 2:
        return adjacency, 0
    species = sorted(set(symbols))
    radii = {
        (a, b): cutoff(a, b)
        for a in species
        for b in species
        if not (different_only and a == b)
    }
    radii = {key: value for key, value in radii.items() if value > 0}
    if not radii:
        return adjacency, 0
    network = Atoms(symbols, positions=positions, cell=cell, pbc=periodic)
    first, second, shifts, vectors = neighbor_list(
        "ijSD", network, radii, self_interaction=False
    )
    bonds = 0
    for i, j, shift, vector in zip(
        first, second, shifts, vectors, strict=True
    ):
        if i == j:
            continue  # bonded to its own image: too small a cell
        adjacency[i].append((int(j), tuple(int(s) for s in shift), vector))  # type: ignore[arg-type]
        bonds += 1
    return adjacency, bonds // 2


def _into_cell(
    points: np.ndarray, cell: np.ndarray, periodic: list[bool]
) -> np.ndarray:
    """Points moved by a lattice vector so their centre lies in the cell
    (tolerant of rounding: a centre on a cell edge goes to fraction 0). Only
    periodic directions count, so a 2D cell may have a zero c vector."""
    if not any(periodic):
        return points
    centre = points.mean(axis=0) @ np.linalg.pinv(cell)
    shift = np.array(
        [
            -np.floor(c + 1e-4) if p else 0.0
            for c, p in zip(centre, periodic, strict=True)
        ]
    )
    return points + shift @ cell


def _label(size: int, inside: list[str]) -> str:
    counts: dict[str, int] = {}
    for symbol in inside:
        counts[symbol] = counts.get(symbol, 0) + 1
    return f"{size}" + "".join(f"+{n}{s}" for s, n in counts.items())


def _signed_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * (x @ np.roll(y, -1) - y @ np.roll(x, -1)))


def _inside(point: np.ndarray, polygon: np.ndarray) -> bool:
    x, y = point
    inside = False
    for k in range(len(polygon)):
        x1, y1 = polygon[k]
        x2, y2 = polygon[(k + 1) % len(polygon)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _planar(
    atoms: Atoms,
    nodes: list[int],
    adjacency: Adjacency,
    bonds: int,
    size_of: Any,
    unit: str,
    enclosed: bool,
    cell: np.ndarray,
) -> RingResult:
    symbols = atoms.get_chemical_symbols()
    positions = atoms.positions
    # In-plane coordinates: e1 along a, e2 = n x e1.
    # (Without a cell, as for a molecule: the xy plane.)
    length = np.linalg.norm(cell[0])
    e1 = cell[0] / length if length else np.array([1.0, 0.0, 0.0])
    e2 = np.cross(surface_normal(cell), e1)

    def flat(v: np.ndarray) -> np.ndarray:
        return np.array([v @ e1, v @ e2])

    alive = [True] * len(nodes)
    changed = True
    while changed:  # 2-core: drop atoms with at most one remaining bond
        changed = False
        for u, edges in enumerate(adjacency):
            if alive[u] and sum(alive[v] for v, _, _ in edges) <= 1:
                alive[u] = False
                changed = True
    core = [
        sorted(
            (e for e in edges if alive[e[0]]),
            key=lambda e: float(np.arctan2(*flat(e[2])[::-1])),
        )
        if alive[u]
        else []
        for u, edges in enumerate(adjacency)
    ]
    half_edges = sum(len(edges) for edges in core)
    used = [[False] * len(edges) for edges in core]
    found: list[tuple[list[int], list[Image], np.ndarray, float]] = []
    open_faces: list[tuple[int, ...]] = []
    for u in range(len(nodes)):
        for k in range(len(core[u])):
            if used[u][k]:
                continue
            walk, images, points = [], [], []
            image = np.zeros(3, dtype=int)
            position = positions[nodes[u]].copy()
            cu, ck = u, k
            for _ in range(half_edges + 1):
                used[cu][ck] = True
                v, shift, vector = core[cu][ck]
                walk.append(nodes[cu])
                images.append(tuple(int(i) for i in image))
                points.append(position.copy())
                position = position + vector
                image = image + np.array(shift)
                back = core[v]
                j = next(
                    (
                        n
                        for n, (w, s, _) in enumerate(back)
                        if w == cu and s == tuple(-np.array(shift))
                    ),
                    0,
                )
                cu, ck = v, (j - 1) % len(back)
                if (cu, ck) == (u, k):
                    break
            if image.any():
                open_faces.append(tuple(walk))
                continue
            outline = np.array([flat(p) for p in points])
            area = _signed_area(outline)
            if area <= 1e-6:
                continue  # the clockwise outline of an island
            found.append((walk, images, np.array(points), area))  # type: ignore[arg-type]

    moved = [
        _into_cell(points, cell, [*map(bool, atoms.pbc[:2]), False])
        for _, _, points, _ in found
    ]
    inside: list[list[int]] = [[] for _ in found]
    enclosed_count = 0
    if enclosed:
        shifts = [
            i * cell[0] + j * cell[1]
            for i in ((-1, 0, 1) if atoms.pbc[0] else (0,))
            for j in ((-1, 0, 1) if atoms.pbc[1] else (0,))
        ]
        outlines = [np.array([flat(p) for p in points]) for points in moved]
        for u, node in enumerate(nodes):
            if alive[u]:
                continue
            best = None
            for r, (_, _, _, area) in enumerate(found):
                if best is not None and area >= found[best][3]:
                    continue
                if any(
                    _inside(flat(positions[node] + s), outlines[r])
                    for s in shifts
                ):
                    best = r
            if best is not None:
                inside[best].append(node)
                enclosed_count += 1
    rings = [
        Ring(
            size=size_of(walk),
            label=_label(size_of(walk), [symbols[i] for i in inside[r]]),
            atoms=tuple(walk),
            images=tuple(images),
            points=moved[r],
            area=area,
            inside=tuple(inside[r]),
        )
        for r, (walk, images, _, area) in enumerate(found)
    ]
    rings.sort(key=lambda ring: (ring.size, ring.label))
    overlaps = _overlapping(
        [nodes[u] for u in range(len(nodes)) if alive[u]], atoms, flat, cell
    )
    warnings: tuple[str, ...] = ()
    if overlaps:
        named = ", ".join(
            f"{symbols[i]}{i} and {symbols[j]}{j}" for i, j in overlaps[:3]
        )
        warnings = (
            f"{len(overlaps)} pair{'s' if len(overlaps) > 1 else ''} of network "
            f"atoms lie on top of each other in the a-b plane ({named}"
            f"{', ...' if len(overlaps) > 3 else ''}), so the rings of a flat "
            "network may be wrong: keep one layer with height windows, or "
            "choose a 3D network (shortest-path rings).",
        )
    return RingResult(
        rings=tuple(rings),
        method="planar",
        unit=unit,
        network=len(nodes),
        bonds=bonds,
        pruned=alive.count(False),
        enclosed=enclosed_count,
        open_faces=tuple(open_faces),
        warnings=warnings,
    )


# Atoms closer than this in the a-b plane count as on top of each other.
OVERLAP_DISTANCE = 0.2


def _overlapping(
    indices: list[int], atoms: Atoms, flat: Any, cell: np.ndarray
) -> list[tuple[int, int]]:
    """Pairs of atoms (indices into ``atoms``) on top of each other in the
    a-b plane, also across in-plane periodic images."""
    if len(indices) < 2:
        return []
    points = np.array([flat(atoms.positions[i]) for i in indices])
    shifts = [
        flat(i * cell[0] + j * cell[1])
        for i in ((-1, 0, 1) if atoms.pbc[0] else (0,))
        for j in ((-1, 0, 1) if atoms.pbc[1] else (0,))
    ]
    close = np.zeros((len(indices), len(indices)), dtype=bool)
    for shift in shifts:
        gaps = points[:, None, :] + shift - points[None, :, :]
        close |= np.linalg.norm(gaps, axis=2) < OVERLAP_DISTANCE
    first, second = np.nonzero(np.triu(close, k=1))
    return [
        (indices[a], indices[b])
        for a, b in zip(first.tolist(), second.tolist(), strict=True)
    ]


def _shortest_paths(
    atoms: Atoms,
    nodes: list[int],
    adjacency: Adjacency,
    bonds: int,
    size_of: Any,
    unit: str,
    max_size: int,
    cell: np.ndarray,
    periodic: list[bool],
) -> RingResult:
    """Guttman rings: shortest paths between two neighbours of an atom that
    avoid the atom, each closed by the atom. Nodes are (atom, image)."""
    Node = tuple[int, Image]

    def neighbours(node: Node) -> list[Node]:
        u, image = node
        return [
            (v, (image[0] + s[0], image[1] + s[1], image[2] + s[2]))
            for v, s, _ in adjacency[u]
        ]

    def shortest_paths(
        start: Node, goal: Node, avoid: Node, limit: int
    ) -> list[list[Node]]:
        """Every shortest path start..goal (at most ``limit`` bonds) that
        avoids ``avoid``."""
        parents: dict[Node, list[Node]] = {start: []}
        depth = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node == goal or depth[node] >= limit:
                continue
            if goal in depth and depth[node] >= depth[goal]:
                continue
            for nxt in neighbours(node):
                if nxt == avoid:
                    continue
                if nxt not in depth:
                    depth[nxt] = depth[node] + 1
                    parents[nxt] = [node]
                    queue.append(nxt)
                elif depth[nxt] == depth[node] + 1:
                    parents[nxt].append(node)
        if goal not in depth:
            return []
        paths: list[list[Node]] = []

        def back(node: Node, tail: list[Node]) -> None:
            if node == start:
                paths.append([start, *tail])
                return
            for parent in parents[node]:
                back(parent, [node, *tail])

        back(goal, [])
        return paths

    def canonical(ring: list[Node]) -> tuple[Node, ...]:
        """The same key for a ring and its periodic copies."""
        keys = []
        for _, origin in ring:
            keys.append(
                tuple(
                    sorted(
                        (
                            u,
                            (
                                i[0] - origin[0],
                                i[1] - origin[1],
                                i[2] - origin[2],
                            ),
                        )
                        for u, i in ring
                    )
                )
            )
        return min(keys)

    seen: set[tuple[Node, ...]] = set()
    found: list[list[Node]] = []
    for u in range(len(nodes)):
        centre: Node = (u, (0, 0, 0))
        around = neighbours(centre)
        for a in range(len(around)):
            for b in range(a + 1, len(around)):
                if around[a] == around[b]:
                    continue
                for path in shortest_paths(
                    around[a], around[b], centre, max_size - 2
                ):
                    ring = [centre, *path]
                    if len({node for node in ring}) != len(ring):
                        continue
                    key = canonical(ring)
                    if key not in seen:
                        seen.add(key)
                        found.append(ring)
    positions = atoms.positions
    rings = []
    for ring in found:
        walk = [nodes[u] for u, _ in ring]
        points = np.array(
            [positions[nodes[u]] + np.array(image) @ cell for u, image in ring]
        )
        size = size_of(walk)
        rings.append(
            Ring(
                size=size,
                label=str(size),
                atoms=tuple(walk),
                images=tuple(image for _, image in ring),
                points=_into_cell(points, cell, periodic),
            )
        )
    rings.sort(key=lambda ring: (ring.size, ring.atoms))
    return RingResult(
        rings=tuple(rings),
        method="shortest-path",
        unit=unit,
        network=len(nodes),
        bonds=bonds,
    )
