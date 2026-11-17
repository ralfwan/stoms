"""What both notebook viewers share: settings, Python-side properties, HTML.

A viewer's state is three values, the same in the browser and in Python:

- ``frame``: the index of the shown frame;
- ``settings``: the viewer's settings, in the format of its settings files
  (``viewerPrefs`` in ``viewer.js``; the ledger viewer exports and imports the
  same files under View);
- ``camera``: ``{"R": 3×3 rotation, "scale": pixels per Å, "pan": [x, y]}``;
  empty for the default (top view, fitted).

The properties below (``show_cell``, ``atom_scale``, …) read and write
``settings``; they are not a second copy of it.
"""

from __future__ import annotations

import copy
import json
import math
import numbers
import os
import re
import tempfile
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms

from ..analysis.polyhedra import bond_range
from ..analysis.symmetry import (
    DEFAULT_TOLERANCE,
    INSTALL_HINT,
    check_tolerance,
    symmetry_available,
    symmetry_payload,
)
from .document import DEFAULT_HEIGHT, document, embed_data
from .frames import _copy, embed_symmetry

SETTINGS_VERSION = 1
# GUI profiles: which of the viewer's controls are shown (not a setting).
PROFILES = ("simple", "advanced")
DEFAULT_PROFILE = "simple"
# Defaults of the settings with properties here; they must match
# defaultPrefs() in viewer.js (checked by the browser tests).
DEFAULTS: dict[str, Any] = {
    "cell": True,
    "bonds": False,
    "wrap": False,
    "polyhedra": False,
    # Whether the centre atoms of drawn polyhedra are drawn.
    "polyhedraCentres": True,
    # Drawing style and radius type of the automatic radii (STYLES,
    # RADIUS_TYPES).
    "style": "ball-and-stick",
    "radiusType": "covalent",
    "labels": "off",
    "repeat": [1, 1, 1],
    # Transformation matrix of the shown cell instead of the repeat (None:
    # the repeat; see repeat), and the stored cell's outline beside it.
    "repeatMatrix": None,
    "storedCellOutline": False,
    # The stored cell's outline at every copy of the repeat.
    "repeatCellOutline": False,
    # Only the stored cell and its atoms, nothing from periodic images.
    "singleCell": False,
    "svgTransparent": True,
    "hiddenElements": [],
    "slice": [[None, None], [None, None], [None, None]],
    "cutoffs": {},
    # Shortest bond per element pair (bond_cutoffs as (min, max)).
    "bondMinimums": {},
    "bondedOutside": "hide",
    "polyCenters": None,
    "planes": [],
}
# Defaults of settings inside a group (viewerPrefs.appearance, .arrows).
NESTED_DEFAULTS: dict[tuple[str, str], Any] = {
    ("appearance", "atomScale"): 1.0,
    ("appearance", "polyAlpha"): 0.45,
    ("appearance", "planeAlpha"): 0.2,
    ("appearance", "bondRadius"): 0.08,
    ("appearance", "depthCue"): False,
    ("appearance", "depthStrength"): 0.6,
    ("appearance", "cellWidth"): 1.0,
    ("appearance", "cellColour"): None,
    ("appearance", "cellDash"): "solid",
    ("arrows", "show"): False,
    ("arrows", "scale"): 1.0,
    ("arrows", "source"): "vectors",
    # The reference of displacements (show_displacements): "compared",
    # "first", "previous" or "frame" (the frame index `frame`).
    ("displacement", "reference"): "first",
    ("displacement", "frame"): 0,
    # Distance tolerance (Å) of the symmetry search (symmetry_tolerance).
    ("symmetry", "tolerance"): DEFAULT_TOLERANCE,
    ("appearance", "colours"): {},
    ("appearance", "radii"): {},
    # Hydrogen bonds D–H···A (hydrogen_bonds and the hydrogen_bond_* settings).
    ("hbonds", "show"): False,
    ("hbonds", "acceptors"): ["O", "N", "F"],
    ("hbonds", "min"): 1.5,
    ("hbonds", "max"): 2.5,
    ("hbonds", "angle"): 120,
    ("hbonds", "colour"): "#2f7fd0",
    # Per-acceptor H···A ranges ({"O": [min, max]}), used when perAcceptor
    # is on (hydrogen_bond_distance as a dict); min/max stay the single
    # range for the acceptors without one.
    ("hbonds", "perAcceptor"): False,
    ("hbonds", "ranges"): {},
}
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
AXIS_NAMES = ("a", "b", "c")
LABELS = ("off", "index", "element", "element-index")
MAX_REPEAT = 12
# A transformation matrix makes at most as many cell copies as the largest
# repeat (MAX_REPEAT_COPIES in viewer.js).
MAX_REPEAT_COPIES = MAX_REPEAT**3
MAX_ATOM_SCALE = 3.0
# Cell outline: largest width in pixels, line styles (MAX_CELL_WIDTH and
# CELL_DASHES in viewer.js).
MAX_CELL_WIDTH = 6.0
CELL_STYLES = ("solid", "dashed", "dotted")
# Colour by property: values from the geometry (DERIVED_PROPERTIES in
# viewer.js; ring sizes need the ledger server), vector components, how to
# read values, and the palettes (PALETTES in viewer.js; checked by the
# browser tests).
DERIVED = (
    "coordination",
    "index",
    "x",
    "y",
    "z",
    "fa",
    "fb",
    "fc",
    "displacement",
    "equivalent",
)
COMPONENTS = ("norm", "x", "y", "z")
KINDS = ("auto", "continuous", "categories")
PALETTES = (
    "blue",
    "green",
    "orange",
    "purple",
    "grey",
    "viridis",
    "cividis",
    "plasma",
    "inferno",
    "magma",
    "turbo",
    "diverging",
    "custom",
)
# What arrows show (ARROW_SOURCES in viewer.js).
ARROW_SOURCES = ("vectors", "displacement")
# Atoms bonded to shown ones but outside the repeat or the slice
# (BONDED_OUTSIDE in viewer.js).
BONDED_OUTSIDE = ("hide", "partners", "ligands")
# Drawing styles and radius types (STYLES and RADIUS_TYPES in viewer.js).
STYLES = ("ball-and-stick", "space-filling", "stick", "wireframe")
RADIUS_TYPES = ("covalent", "vdw", "ionic")
# Looks for set_view: presets and the axes (prefix "-" for the other side).
VIEWS = ("top", "side-a", "side-b")
AXES = ("a", "b", "c", "x", "y", "z")


def check_repeat_matrix(value: Any) -> list[list[int]] | None:
    """A transformation matrix of the shown cell, as the viewer keeps it
    (``repeatMatrix``; checkRepeatMatrix in viewer.js): 3 rows of 3 whole
    numbers from -MAX_REPEAT to MAX_REPEAT with a determinant from 1 to
    MAX_REPEAT³ (the number of cell copies). None stands for the repeat."""
    if value is None:
        return None
    try:
        rows = [list(row) for row in value]
    except TypeError:
        raise ValueError("the matrix has 3 rows of 3 whole numbers") from None
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        raise ValueError("the matrix has 3 rows of 3 whole numbers")
    entries = [v for row in rows for v in row]
    if not all(
        isinstance(v, numbers.Integral) and not isinstance(v, bool)
        for v in entries
    ):
        raise ValueError(f"the matrix entries are whole numbers, not {rows!r}")
    matrix = [[int(v) for v in row] for row in rows]
    if any(abs(v) > MAX_REPEAT for row in matrix for v in row):
        raise ValueError(
            f"the matrix entries are from -{MAX_REPEAT} to {MAX_REPEAT}"
        )
    (a, b, c), (d, e, f), (g, h, i) = matrix
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if det == 0:
        raise ValueError("the matrix rows are not independent (determinant 0)")
    if det < 0:
        raise ValueError(
            f"the matrix determinant is {det}: the new cell is left-handed "
            "(swap two rows)"
        )
    if det > MAX_REPEAT_COPIES:
        raise ValueError(
            f"the matrix determinant is {det}: at most {MAX_REPEAT_COPIES} "
            "cell copies"
        )
    return matrix


# Atoms per measurement kind (MEASURE_ATOMS in viewer.js) and planes of the
# plane measurements (MEASURE_PLANES).
MEASURE_ATOMS = {
    "position": 1,
    "distance": 2,
    "angle": 3,
    "dihedral": 4,
    "plane-angle": 0,
    "plane-distance": 1,
}
MEASURE_PLANES = {"plane-angle": 2, "plane-distance": 1}
# Atoms of a plane through atoms (MIN_PLANE_ATOMS in viewer.js).
MIN_PLANE_ATOMS = 3
# Extend factor ``scale`` of a plane (MIN/MAX_PLANE_SCALE in viewer.js).
MIN_PLANE_SCALE = 1.0
MAX_PLANE_SCALE = 10.0


def check_plane_scale(value: Any) -> float:
    """A plane's extend factor ``scale``: a number from 1 to 10 (the drawn
    plane, extended in all in-plane directions about its centre)."""
    if (
        isinstance(value, bool)
        or not isinstance(value, numbers.Real)
        or not MIN_PLANE_SCALE <= float(value) <= MAX_PLANE_SCALE
    ):
        raise ValueError(
            f"a plane's scale is a number from {MIN_PLANE_SCALE:g} to "
            f"{MAX_PLANE_SCALE:g}, not {value!r}"
        )
    return float(value)


def check_atom_ref(ref: Any, where: str) -> dict[str, Any]:
    """An atom ref ``{"index", "image": [i, j, k], "symbol", "count"}`` as
    measurements and planes through atoms keep it."""
    ok = (
        isinstance(ref, Mapping)
        and _whole(ref.get("index"))
        and ref["index"] >= 0
        and _whole(ref.get("count"))
        and ref["index"] < ref["count"]
        and isinstance(ref.get("symbol"), str)
        and isinstance(ref.get("image"), list | tuple)
        and len(ref["image"]) == 3
        and all(_whole(n) for n in ref["image"])
    )
    if not ok:
        raise ValueError(
            f"{where}: an atom is {{index, image, symbol, count}}, not {ref!r}"
        )
    return {
        "index": ref["index"],
        "image": list(ref["image"]),
        "symbol": ref["symbol"],
        "count": ref["count"],
    }


def check_plane_definition(plane: Any, where: str) -> dict[str, Any]:
    """A plane as plane measurements keep it: ``{"h", "k", "l", "t"}`` (a
    Miller plane) or ``{"atoms": [ref, ...]}`` (through 3 or more atoms)."""
    if isinstance(plane, Mapping) and "atoms" in plane:
        atoms = plane["atoms"]
        if not isinstance(atoms, list) or len(atoms) < MIN_PLANE_ATOMS:
            raise ValueError(f"{where}: a plane through atoms has 3 or more")
        return {"atoms": [check_atom_ref(ref, where) for ref in atoms]}
    if isinstance(plane, Mapping):
        h, k, l = (plane.get(n, 0) for n in "hkl")  # noqa: E741
        t = plane.get("t", 0)
        if (
            all(_whole(n) for n in (h, k, l))
            and (h or k or l)
            and isinstance(t, numbers.Real)
            and math.isfinite(t)
        ):
            return {"h": h, "k": k, "l": l, "t": float(t)}
    raise ValueError(
        f"{where}: a plane is {{h, k, l, t}} (whole h, k, l, not all 0) or "
        f"{{atoms: [...]}}, not {plane!r}"
    )


def check_atom_plane(plane: Mapping[str, Any]) -> dict[str, Any]:
    """A plane through atoms of ``viewer.planes``: ``{"atoms": [ref, ...],
    "show", "patch", "colour", "scale"}`` (colour and scale optional)."""
    atoms = plane.get("atoms")
    if not isinstance(atoms, list) or len(atoms) < MIN_PLANE_ATOMS:
        raise ValueError("a plane through atoms has 3 or more atoms")
    entry: dict[str, Any] = {
        "atoms": [check_atom_ref(ref, "a plane") for ref in atoms],
        "show": bool(plane.get("show", True)),
        "patch": bool(plane.get("patch", False)),
    }
    colour = plane.get("colour")
    if colour is not None:
        if not (isinstance(colour, str) and COLOUR.match(colour)):
            raise ValueError(f"a plane colour is #rrggbb, not {colour!r}")
        entry["colour"] = colour
    if "scale" in plane:
        entry["scale"] = check_plane_scale(plane["scale"])
    return entry


def check_profile(value: Any) -> str:
    """``value`` if it names a profile, else ValueError."""
    if not isinstance(value, str) or value not in PROFILES:
        raise ValueError(f'profile is "simple" or "advanced", not {value!r}')
    return value


def check_measurements(items: Any) -> list[dict[str, Any]]:
    """Measurements of a settings file, as the viewer keeps them.

    Each is ``{"kind": "position" | "distance" | "angle" | "dihedral",
    "atoms": [ref]}``,
    a ref ``{"index", "image": [i, j, k], "symbol", "count"}`` (the atom, its
    periodic image, its element and the number of atoms of the structure),
    or a plane measurement with ``"planes"`` (see check_plane_definition):
    ``{"kind": "plane-angle", "atoms": [], "planes": [plane, plane]}`` (the
    angle between two planes) or ``{"kind": "plane-distance", "atoms":
    [ref], "planes": [plane]}`` (the atom's signed distance from the plane).
    A measurement is drawn on structures with the same atom count and
    elements at its indices (also those of its planes). Values are not
    stored: the viewer computes them.
    """
    if not isinstance(items, list):
        raise ValueError("measurements are a list")
    checked = []
    for k, item in enumerate(items):
        kind = item.get("kind") if isinstance(item, Mapping) else None
        atoms = item.get("atoms", []) if isinstance(item, Mapping) else None
        if (
            kind not in MEASURE_ATOMS
            or not isinstance(atoms, list)
            or len(atoms) != MEASURE_ATOMS[kind]
        ):
            raise ValueError(
                f"measurement {k} is not a distance (2 atoms), angle (3), "
                "dihedral (4), position (1), plane-angle (no atoms, 2 planes) "
                "or plane-distance (1 atom, 1 plane)"
            )
        where = f"measurement {k}"
        entry: dict[str, Any] = {
            "kind": kind,
            "atoms": [check_atom_ref(ref, where) for ref in atoms],
        }
        if kind in MEASURE_PLANES:
            planes = item.get("planes")
            if (
                not isinstance(planes, list)
                or len(planes) != MEASURE_PLANES[kind]
            ):
                raise ValueError(
                    f"{where}: a {kind} has {MEASURE_PLANES[kind]} plane"
                    f"{'s' if MEASURE_PLANES[kind] > 1 else ''}"
                )
            entry["planes"] = [
                check_plane_definition(plane, where) for plane in planes
            ]
        checked.append(entry)
    return checked


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read_settings(
    settings: Any,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """``(settings, camera, measurements)`` from what ``view(settings=...)``
    accepts.

    That is a viewer's ``get_settings()``, the content of a settings file
    (``{"stoms_viewer_settings": 1, "settings": {...}, "view": {...},
    "measurements": [...]}``), the path of such a file, or a plain settings
    dictionary.
    """
    if settings is None:
        return {}, {}, []
    if isinstance(settings, str | os.PathLike):
        settings = json.loads(Path(settings).read_text(encoding="utf-8"))
    if not isinstance(settings, Mapping):
        raise TypeError(
            "settings must be a dictionary (viewer.get_settings()) or the path "
            f"of a settings file, not a {type(settings).__name__}"
        )
    camera: Any = {}
    measurements: list[dict[str, Any]] = []
    if "stoms_viewer_settings" in settings:
        if settings["stoms_viewer_settings"] != SETTINGS_VERSION:
            raise ValueError(
                "unknown settings file version "
                f"{settings['stoms_viewer_settings']!r}"
            )
        camera = settings.get("view") or {}
        measurements = check_measurements(settings.get("measurements") or [])
        settings = settings.get("settings") or {}
        if not isinstance(settings, Mapping) or not isinstance(
            camera, Mapping
        ):
            raise ValueError("a settings file holds dictionaries")
    try:
        json.dumps(settings, allow_nan=False)
        json.dumps(camera, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"settings must be plain JSON: {error}") from None
    return (
        copy.deepcopy(dict(settings)),
        copy.deepcopy(dict(camera)),
        measurements,
    )


def _setting(key: str, doc: str) -> property:
    def get(self: ViewerBase) -> Any:
        return copy.deepcopy(self.settings.get(key, DEFAULTS[key]))

    def set_(self: ViewerBase, value: Any) -> None:
        self._update_settings({key: self._check(key, value)})

    return property(get, set_, doc=doc)


def _nested(group: str, key: str, doc: str) -> property:
    """A setting inside a group of the settings (``settings[group][key]``)."""

    def get(self: ViewerBase) -> Any:
        values = self.settings.get(group) or {}
        return copy.deepcopy(values.get(key, NESTED_DEFAULTS[group, key]))

    def set_(self: ViewerBase, value: Any) -> None:
        values = dict(self.settings.get(group) or {})
        values[key] = self._check(f"{group}.{key}", value)
        self._update_settings({group: values})

    return property(get, set_, doc=doc)


class ViewerBase:
    """Shared by Viewer (the widget) and StaticView.

    Subclasses provide ``frame``, ``settings``, ``camera``, ``_images`` and
    ``_frames`` (the frames' JSON).
    """

    frame: int
    settings: dict[str, Any]
    camera: dict[str, Any]
    _images: list[Atoms]
    _frames: list[dict[str, Any]]
    _height: int = DEFAULT_HEIGHT
    _title: str = "STOMS viewer"
    _profile: str = DEFAULT_PROFILE

    @property
    def profile(self) -> str:
        """Which controls the viewer shows: ``"simple"`` (the default: the
        controls most pictures need, plus every control whose setting is in
        use) or ``"advanced"`` (all of them). Only the controls change, never
        a setting or the picture; it is not part of ``get_settings()`` or
        settings files, but saved HTML files keep it. Switched in the viewer
        too (⚙ › Controls)."""
        return self._profile

    @profile.setter
    def profile(self, value: str) -> None:
        self._profile = check_profile(value)

    show_cell = _setting("cell", "Whether the unit cell outline is drawn.")
    show_bonds = _setting("bonds", "Whether bonds are drawn (ball and stick).")
    wrap = _setting("wrap", "Whether atoms are drawn wrapped into the cell.")
    polyhedra = _setting(
        "polyhedra", "Whether coordination polyhedra are drawn."
    )
    show_polyhedron_centres = _setting(
        "polyhedraCentres",
        "Whether the centre atoms of drawn polyhedra are drawn (default True). "
        "When False, only atoms that are the centre of a drawn polyhedron are "
        "left out (sphere, label and bonds); they still count as shown atoms.",
    )
    labels = _setting(
        "labels", 'Atom labels: "off", "index", "element" or "element-index".'
    )
    style = _setting(
        "style",
        'Drawing style: "ball-and-stick" (the default), "space-filling" '
        "(spheres at the radius type's table radii, no bonds or polyhedra), "
        '"stick" (bonds as cylinders, atoms of the bond radius) or "wireframe" '
        "(bonds as thin "
        "lines, atoms without bonds as dots). Stick and wireframe always draw "
        "bonds; element_radii win in every style but space-filling.",
    )
    radius_type = _setting(
        "radiusType",
        'Radius type of the automatic atom radii: "covalent" (Cordero 2008, '
        'the default), "vdw" (van der Waals, Alvarez 2013) or "ionic" '
        "(Shannon 1976, one ion per element at coordination 6). Elements "
        "without such a radius keep the covalent one.",
    )

    @property
    def repeat(self) -> list[int] | list[list[int]]:
        """The shown cell: copies along a, b and c (periodic axes only), as
        ``[na, nb, nc]``; or a 3×3 integer transformation matrix whose rows
        are the shown cell's vectors in units of the stored a, b and c, such
        as ``[[2, 1, 0], [-1, 1, 0], [0, 0, 1]]`` for (√3×√3)R30° of a
        hexagonal a-b lattice. Display only: the frames, saved structures and
        the cell numbers keep the stored cell. A 3-list sets the repeat and
        drops the matrix; reading gives the matrix while one is set."""
        matrix = self.settings.get("repeatMatrix")
        if matrix is not None:
            return copy.deepcopy(matrix)
        return copy.deepcopy(self.settings.get("repeat", DEFAULTS["repeat"]))

    @repeat.setter
    def repeat(self, value: Any) -> None:
        items = list(value)
        if any(hasattr(row, "__len__") for row in items):
            self._update_settings(
                {"repeatMatrix": self._check("repeatMatrix", items)}
            )
        else:
            changes: dict[str, Any] = {"repeat": self._check("repeat", items)}
            # The repeat replaces a matrix (settings without one stay so).
            if self.settings.get("repeatMatrix") is not None:
                changes["repeatMatrix"] = None
            self._update_settings(changes)

    show_stored_cell = _setting(
        "storedCellOutline",
        "Whether the stored cell's outline is drawn (dotted) beside the cell "
        "of a transformation matrix (see repeat).",
    )
    repeat_cell_outline = _setting(
        "repeatCellOutline",
        "Whether the cell outline is drawn at every repeated copy (default "
        "False; with show_cell). With a transformation matrix: the "
        "stored-cell grid inside the shown cell, dotted (it includes "
        "show_stored_cell).",
    )
    single_cell = _setting(
        "singleCell",
        "Whether only the stored cell is shown (default False): each atom "
        "once, wrapped into the cell, and nothing from periodic images. While "
        "it is on, repeat (also a transformation matrix), wrap, "
        "repeat_cell_outline, show_stored_cell and bonded_outside are ignored "
        "but kept, so switching it off shows the previous view again; only "
        "polyhedra and rings complete inside the cell are drawn, and planes "
        "are clipped to the cell. Labels, arrows and measurements are "
        "unchanged.",
    )
    transparent = _setting(
        "svgTransparent",
        "Whether saved SVG images have no background (in light colours).",
    )

    atom_scale = _nested(
        "appearance",
        "atomScale",
        "Factor on the automatic atom radii in ball-and-stick (not on radii "
        "set per element); space-filling, stick and wireframe ignore it.",
    )
    polyhedra_opacity = _nested(
        "appearance", "polyAlpha", "Opacity of the polyhedra, 0 to 1."
    )
    plane_opacity = _nested(
        "appearance", "planeAlpha", "Opacity of the Miller planes, 0 to 1."
    )
    bond_radius = _nested(
        "appearance", "bondRadius", "Bond radius in Å, 0.02 to 0.4."
    )
    depth_cue = _nested(
        "appearance", "depthCue", "Whether atoms fade towards the back."
    )
    depth_strength = _nested(
        "appearance",
        "depthStrength",
        "How far the back-most atoms fade (depth_cue), 0.1 to 0.9.",
    )
    cell_width = _nested(
        "appearance",
        "cellWidth",
        f"Line width of the cell outline in pixels, up to {MAX_CELL_WIDTH:g}.",
    )
    cell_colour = _nested(
        "appearance",
        "cellColour",
        'Colour of the cell outline, such as "#000000"; None: the theme\'s.',
    )
    cell_style = _nested(
        "appearance",
        "cellDash",
        'Line style of the cell outline: "solid", "dashed" or "dotted".',
    )
    show_forces = _nested(
        "arrows",
        "show",
        "Whether force arrows are drawn: calculator forces, or the per-atom "
        "vectors chosen under ⚙ › Arrows.",
    )
    force_scale = _nested(
        "arrows", "scale", "Arrow length in Å per unit of the vectors."
    )
    arrow_source = _nested(
        "arrows",
        "source",
        'What arrows show: "vectors" (forces or the per-atom vectors chosen '
        'under ⚙ › Arrows) or "displacement" (see show_displacements).',
    )
    symmetry_tolerance = _nested(
        "symmetry",
        "tolerance",
        "Distance tolerance in Å of the symmetry search (space group, "
        "Wyckoff letters, equivalent sites; spglib's symprec), 1e-5 to 1.",
    )
    hidden_elements = _setting(
        "hiddenElements", "Elements not drawn (nor their bonds), as symbols."
    )
    element_colours = _nested(
        "appearance",
        "colours",
        'Colours per element, such as {"O": "#d62728"}; others keep theirs.',
    )
    element_radii = _nested(
        "appearance",
        "radii",
        "Sphere radii per element in Å, in every style but space-filling "
        "(which draws the radius type's table radii); others are automatic "
        "(atom_scale).",
    )
    hydrogen_bonds = _nested(
        "hbonds",
        "show",
        "Whether hydrogen bonds D–H···A are drawn (dashed): see "
        "hydrogen_bond_acceptors, hydrogen_bond_distance, hydrogen_bond_angle.",
    )
    hydrogen_bond_acceptors = _nested(
        "hbonds",
        "acceptors",
        "Elements of hydrogen bond acceptors A and donors D (the atom bonded "
        'to the H), as symbols; default ["O", "N", "F"].',
    )
    hydrogen_bond_angle = _nested(
        "hbonds",
        "angle",
        "Smallest D–H···A angle at the H in degrees (0 to 180), default 120.",
    )
    hydrogen_bond_colour = _nested(
        "hbonds", "colour", 'Colour of the hydrogen bonds, such as "#2f7fd0".'
    )
    bonded_outside = _setting(
        "bondedOutside",
        'Atoms outside the repeat or the slice bonded to shown atoms: "hide", '
        '"partners" (drawn with their bonds, one step) or "ligands" (only the '
        "ligands of shown polyhedra). They are not counted as shown atoms.",
    )
    polyhedron_centres = _setting(
        "polyCenters",
        "Elements at the centre of coordination polyhedra (None: the "
        "transition metals).",
    )

    @property
    def slice(self) -> dict[str, tuple[float | None, float | None]]:
        """Fractional-coordinate window of the drawn atoms per axis:
        ``{"a": (min, max), "b": ..., "c": ...}``; None is no limit."""
        bounds = self.settings.get("slice") or DEFAULTS["slice"]
        return {
            axis: (bounds[k][0], bounds[k][1])
            for k, axis in enumerate(AXIS_NAMES)
        }

    @slice.setter
    def slice(self, value: Any) -> None:
        self._update_settings({"slice": self._check("slice", value)})

    @property
    def bond_cutoffs(self) -> dict[str, float | tuple[float, float]]:
        """Bond cutoffs in Å per element pair, as ``{"O-Si": 2.0}`` (symbols
        sorted): the longest bond drawn, or ``(min, max)`` where bonds
        shorter than ``min`` are not drawn either (``{"H-O": (0.5, 1.2)}``).
        Pairs not given get the viewer's default (minimum 0)."""
        cutoffs = self.settings.get("cutoffs") or {}
        minimums = self.settings.get("bondMinimums") or {}
        return {
            pair: (minimums[pair], cutoff) if minimums.get(pair) else cutoff
            for pair, cutoff in cutoffs.items()
        }

    @bond_cutoffs.setter
    def bond_cutoffs(self, value: Any) -> None:
        cutoffs, minimums = self._check("cutoffs", value)
        self._update_settings({"cutoffs": cutoffs, "bondMinimums": minimums})

    @property
    def hydrogen_bond_distance(
        self,
    ) -> tuple[float, float] | dict[str, tuple[float, float]]:
        """Range of H···A distances of hydrogen bonds in Å, ``(min, max)``;
        default (1.5, 2.5). Set a dict such as ``{"O": (1.5, 2.5),
        "N": (1.6, 2.6)}`` for a range per acceptor element (⚙ › Bond
        search › Per acceptor); it replaces the stored ranges. Acceptors
        without an entry keep the single range; entries for elements not in
        hydrogen_bond_acceptors are stored but have no effect.

        With per-acceptor ranges on, this reads as a dict of every acceptor
        element (hydrogen_bond_acceptors) and the range in effect. Writing
        that value back stores a range for every acceptor, which then no
        longer follows the single range (the viewer's ↺ beside a row undoes
        that per element). Setting ``(min, max)`` sets the single range and
        switches per-acceptor ranges off (the stored ones are kept for the
        viewer's Per acceptor box)."""
        values = self.settings.get("hbonds") or {}
        single = (
            values.get("min", NESTED_DEFAULTS["hbonds", "min"]),
            values.get("max", NESTED_DEFAULTS["hbonds", "max"]),
        )
        if not values.get("perAcceptor"):
            return single
        ranges = values.get("ranges") or {}
        acceptors = values.get(
            "acceptors", NESTED_DEFAULTS["hbonds", "acceptors"]
        )
        return {
            symbol: tuple(ranges[symbol]) if symbol in ranges else single
            for symbol in acceptors
        }

    @hydrogen_bond_distance.setter
    def hydrogen_bond_distance(self, value: Any) -> None:
        values = dict(self.settings.get("hbonds") or {})
        if isinstance(value, Mapping):
            ranges = self._check("hbonds.ranges", value)
            values.update(perAcceptor=True, ranges=ranges)
        else:
            low, high = self._check("hbonds.distance", value)
            values.update(min=low, max=high)
            if "perAcceptor" in values:
                values["perAcceptor"] = False
        self._update_settings({"hbonds": values})

    @property
    def planes(self) -> list[dict[str, Any]]:
        """Miller planes: h·x + k·y + l·z = t in fractional coordinates,
        each ``{"h", "k", "l", "t", "show", "colour"}``; and planes through
        atoms, ``{"atoms": [ref, ...], "show", "patch", "colour"}`` (refs as
        in measurements; see add_plane). Either kind may have ``"scale"``
        (1 to 10, absent = 1): the drawn plane extended in all in-plane
        directions about its centre."""
        return copy.deepcopy(self.settings.get("planes") or [])

    @planes.setter
    def planes(self, value: Any) -> None:
        self._update_settings({"planes": self._check("planes", value)})

    def add_plane(
        self,
        h: int | None = None,
        k: int | None = None,
        l: int | None = None,  # noqa: E741  (Miller index)
        t: float | None = None,
        *,
        atoms: Any = None,
        patch: bool = False,
        distance: float | None = None,
        colour: str | None = None,
        show: bool = True,
        scale: float = 1,
    ) -> None:
        """Draw the Miller plane (h k l) at h·x + k·y + l·z = t, or the plane
        through ``atoms``.

        ``t`` is fractional (in units of the spacing d, default 0.5);
        ``distance`` instead gives the position in Å from the origin along
        the plane normal (t = distance / d, with d of the shown frame).

        ``atoms`` are 3 or more atom indices of the shown frame (or atom refs
        ``{"index", "image", "symbol", "count"}`` as in measurements, for
        periodic images): the plane through 3 atoms, the least-squares plane
        through more. It follows the atoms through the frames (those with
        the same atoms). It is drawn where it cuts the shown cell like a
        Miller plane, or with ``patch=True`` as a patch around the atoms.

        ``scale`` (1 to 10) extends the drawn plane of either kind in all
        in-plane directions about its centre, beyond the shown cell or the
        patch ("Extend ×" in the Planes tab).
        """
        scale = check_plane_scale(scale)
        if atoms is not None:
            if not (h is None and k is None and l is None and t is None) or (
                distance is not None
            ):
                raise ValueError(
                    "a plane is given by Miller indices or by atoms, not both"
                )
            plane: dict[str, Any] = {
                "atoms": self._atom_refs(atoms),
                "show": show,
                "patch": bool(patch),
            }
        else:
            if h is None or k is None or l is None:
                raise ValueError(
                    "add_plane needs Miller indices h, k, l or atoms=[...]"
                )
            if distance is not None:
                if t is not None:
                    raise ValueError(
                        "give the plane's position as t or distance, not both"
                    )
                g = math.hypot(
                    *([h, k, l] @ self._images[self.frame].cell.reciprocal())
                )
                if not g:
                    raise ValueError(
                        "a plane has whole Miller indices h, k, l, not all 0, "
                        "and its distance needs a cell"
                    )
                t = float(distance) * float(g)
            plane = {
                "h": h,
                "k": k,
                "l": l,
                "t": 0.5 if t is None else t,
                "show": show,
            }
        if colour is not None:
            plane["colour"] = colour
        if scale != 1:
            plane["scale"] = scale
        self.planes = [*self.planes, plane]

    def _atom_refs(self, atoms: Any) -> list[dict[str, Any]]:
        """Atom refs of a plane through ``atoms`` (indices of the shown
        frame, or refs), checked to span a plane on the shown frame."""
        shown = self._images[self.frame]
        symbols = shown.get_chemical_symbols()
        if isinstance(atoms, str) or not hasattr(atoms, "__iter__"):
            raise ValueError("atoms is a list of 3 or more atom indices")
        refs = []
        for atom in atoms:
            if isinstance(atom, Mapping):
                refs.append(check_atom_ref(atom, "add_plane"))
                continue
            if not isinstance(atom, numbers.Integral) or isinstance(
                atom, bool
            ):
                raise ValueError(
                    f"an atom of a plane is an index, not {atom!r}"
                )
            index = int(atom)
            if not 0 <= index < len(symbols):
                raise ValueError(
                    f"atom {index} is not in the shown frame "
                    f"({len(symbols)} atoms)"
                )
            refs.append(
                {
                    "index": index,
                    "image": [0, 0, 0],
                    "symbol": symbols[index],
                    "count": len(symbols),
                }
            )
        keys = {(r["index"], tuple(r["image"])) for r in refs}
        if len(refs) < MIN_PLANE_ATOMS or len(keys) < len(refs):
            raise ValueError("a plane goes through 3 or more different atoms")
        fits = all(
            r["count"] == len(symbols) and symbols[r["index"]] == r["symbol"]
            for r in refs
        )
        if fits:
            positions = np.array(
                [
                    shown.positions[r["index"]]
                    + np.array(r["image"]) @ shown.cell[:]
                    for r in refs
                ]
            )
            spread = np.linalg.svd(positions - positions.mean(axis=0))[1]
            if spread[1] < 1e-4:
                raise ValueError(
                    "these atoms lie on a line: they span no plane"
                )
        return refs

    def clear_planes(self) -> None:
        """Remove every plane."""
        self.planes = []

    def colour_by(
        self,
        name: str | None,
        *,
        source: str | None = None,
        component: str = "norm",
        kind: str = "auto",
        range: tuple[float | None, float | None] | None = None,
        symmetric: bool = False,
        palette: str | None = None,
    ) -> None:
        """Colour atoms by a per-atom property, or by element (``None``).

        ``name`` is a per-atom array of the frames (``atoms.arrays`` such as
        ``"tags"``, per-atom lists in ``atoms.info``, calculator results such
        as ``"charges"`` or ``"forces"``), or a value from the geometry:
        ``"coordination"``, ``"index"``, ``"x"``, ``"y"``, ``"z"``, ``"fa"``,
        ``"fb"``, ``"fc"``, ``"displacement"`` (a vector, from the
        reference of show_displacements), or ``"equivalent"`` (the
        symmetry-equivalent site, as categories; needs spglib, the
        ``stoms[symmetry]`` extra). ``source`` (``"arrays"``, ``"info"``,
        ``"calculator"``) picks among arrays of the same name. Vectors are
        coloured by ``component`` (``"norm"``, ``"x"``, ``"y"``, ``"z"``).
        ``kind`` reads values as ``"auto"``, ``"continuous"`` or
        ``"categories"``; ``range`` fixes the ends of a colour scale (None:
        automatic, over all frames); ``symmetric`` centres it on 0. ``palette``
        is one of PALETTES (``"diverging"`` suits signed values).
        """
        if name is None:
            self._update_settings({"colour": "element"})
            return
        if component not in COMPONENTS:
            raise ValueError(f"component is one of {', '.join(COMPONENTS)}")
        if kind not in KINDS:
            raise ValueError(f"kind is one of {', '.join(KINDS)}")
        if palette is not None and palette not in PALETTES:
            raise ValueError(f"palette is one of {', '.join(PALETTES)}")
        low, high = range if range is not None else (None, None)
        for end in (low, high):
            if end is not None and not (
                isinstance(end, int | float) and math.isfinite(end)
            ):
                raise ValueError("range ends are numbers or None")
        choice = self._colour_choice(name, source)
        if choice == {"source": "derived", "name": "equivalent"}:
            if not symmetry_available():
                raise ImportError(INSTALL_HINT)
            kind = "categories"
        changes: dict[str, Any] = {
            "colour": "property",
            "property": {
                **(self.settings.get("property") or {}),
                "choice": choice,
                "component": component,
                "kind": kind,
                "min": low,
                "max": high,
                "symmetric": bool(symmetric),
            },
        }
        if palette is not None:
            changes["palettes"] = {
                **(self.settings.get("palettes") or {}),
                "property": palette,
            }
        self._update_settings(changes)

    color_by = colour_by

    def show_displacements(
        self, reference: str | int = "first", *, show: bool = True
    ) -> None:
        """Draw each atom's displacement from a reference frame as arrows.

        ``reference`` is ``"first"`` (frame 0), ``"previous"`` (the frame
        before the shown one) or a frame index (negative counts from the
        end). Along periodic axes the displacement is the shortest over
        periodic images, so an atom that crossed a cell face gets a short
        arrow. ``show=False`` hides the arrows but keeps the reference, which
        also serves ``colour_by("displacement")``. Arrows keep their style
        (force_scale, ⚙ › Arrows); ``arrow_source = "vectors"`` goes back to
        forces.
        """
        count = len(self._images)
        if count < 2:
            raise ValueError("displacements need two frames or more")
        if not isinstance(show, bool):
            raise TypeError(f"show is True or False, not {show!r}")
        settings = {
            "reference": NESTED_DEFAULTS["displacement", "reference"],
            "frame": NESTED_DEFAULTS["displacement", "frame"],
            **(self.settings.get("displacement") or {}),
        }
        if reference == "compared":
            raise ValueError(
                "a notebook viewer has no compared structure: the reference "
                'is "first", "previous" or a frame index'
            )
        if reference in ("first", "previous"):
            settings["reference"] = reference
        elif isinstance(reference, numbers.Integral) and not isinstance(
            reference, bool
        ):
            index = int(reference)
            if not -count <= index < count:
                raise ValueError(
                    f"frame {index} is out of range: there are {count} frames"
                )
            settings = {"reference": "frame", "frame": index % count}
        else:
            raise ValueError(
                'the reference is "first", "previous" or a frame index, '
                f"not {reference!r}"
            )
        self._update_settings(
            {
                "arrows": {
                    **(self.settings.get("arrows") or {}),
                    "show": show,
                    "source": "displacement",
                },
                "displacement": settings,
            }
        )

    def polyhedron(
        self, index: int, *, frame: int | None = None
    ) -> dict[str, Any]:
        """The coordination polyhedron of atom ``index`` on the shown frame
        (or ``frame``), with the viewer's bond cutoffs (``bond_cutoffs``,
        with their minimums; else the defaults).

        The same numbers as the Measure tab's polyhedra (📏 › Polyhedron):
        bond lengths, volume, distortion index, quadratic elongation,
        bond-angle variance and effective coordination number; see
        :func:`stoms.analysis.polyhedron` for the dictionary.
        """
        from ..analysis import polyhedron

        count = len(self._images)
        shown = self.frame if frame is None else frame
        if (
            not isinstance(shown, numbers.Integral)
            or isinstance(shown, bool)
            or not -count <= shown < count
        ):
            raise ValueError(
                f"frame {shown!r} is out of range: there are {count} frames"
            )
        atoms = self._images[shown]
        if self.settings.get("wrap") or self.settings.get("singleCell"):
            # The viewer draws (and searches bonds from) wrapped positions
            # (single cell only wraps as well).
            atoms = atoms.copy()
            atoms.wrap()
        return polyhedron(atoms, index, cutoffs=self.bond_cutoffs)

    def _colour_choice(self, name: str, source: str | None) -> dict[str, Any]:
        """The viewer's choice of a property (see propertyOptions)."""
        found = {
            (array["source"], array["name"])
            for frame in self._frames
            for array in frame["arrays"]
        }
        sources = [
            s for s in ("calculator", "arrays", "info") if (s, name) in found
        ]
        if source is not None:
            sources = [s for s in sources if s == source]
        if sources:
            return {"source": "array", "origin": sources[0], "name": name}
        if name in DERIVED and source is None:
            return {"source": "derived", "name": name}
        names = sorted({n for _, n in found} | set(DERIVED))
        raise ValueError(
            f"no per-atom property {name!r}"
            + (f" from {source}" if source else "")
            + f"; the frames have: {', '.join(names)}"
        )

    @property
    def panel_size(self) -> tuple[int | None, int | None]:
        """Panel ``(width, height)`` in pixels, also the size of saved
        images; None is automatic."""
        size = self.settings.get("panelSize") or {}
        return size.get("width"), size.get("height")

    @panel_size.setter
    def panel_size(self, value: tuple[int | None, int | None]) -> None:
        width, height = value
        self._update_settings(
            {"panelSize": {"width": _pixels(width), "height": _pixels(height)}}
        )

    def _update_settings(self, changes: dict[str, Any]) -> None:
        # A new dictionary, so that the widget sends it.
        self.settings = {**copy.deepcopy(self.settings), **changes}

    @staticmethod
    def _check(key: str, value: Any) -> Any:
        if key in (
            "cell",
            "bonds",
            "wrap",
            "polyhedra",
            "polyhedraCentres",
            "svgTransparent",
            "storedCellOutline",
            "repeatCellOutline",
            "singleCell",
            "arrows.show",
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{key} is True or False, not {value!r}")
            return value
        if key == "labels":
            if value not in LABELS:
                raise ValueError(f"labels is one of {', '.join(LABELS)}")
            return value
        if key == "repeat":
            counts = list(value)
            if len(counts) != 3 or not all(
                isinstance(n, int) and 1 <= n <= MAX_REPEAT for n in counts
            ):
                raise ValueError(
                    f"repeat is three whole numbers from 1 to {MAX_REPEAT}"
                )
            return counts
        if key == "repeatMatrix":
            return check_repeat_matrix(value)
        if key in ("hiddenElements", "polyCenters"):
            if value is None and key == "polyCenters":
                return None
            if isinstance(value, str) or not all(
                isinstance(sym, str) for sym in value
            ):
                raise TypeError(f"{key} is a list of element symbols")
            return sorted(set(value))
        if key == "appearance.colours":
            colours = dict(value)
            for sym, colour in colours.items():
                if not (isinstance(colour, str) and COLOUR.match(colour)):
                    raise ValueError(
                        f"the colour of {sym} is #rrggbb, not {colour!r}"
                    )
            return colours
        if key == "appearance.radii":
            radii = {sym: float(r) for sym, r in dict(value).items()}
            if not all(r > 0 and math.isfinite(r) for r in radii.values()):
                raise ValueError("element radii are positive numbers (Å)")
            return radii
        if key == "slice":
            items = (
                [value.get(axis) for axis in AXIS_NAMES]
                if isinstance(value, Mapping)
                else list(value)
            )
            if len(items) != 3:
                raise ValueError("slice has bounds for a, b and c")
            bounds = []
            for item in items:
                low, high = item if item is not None else (None, None)
                for end in (low, high):
                    if end is not None and not (
                        isinstance(end, int | float) and math.isfinite(end)
                    ):
                        raise ValueError("slice bounds are numbers or None")
                bounds.append([low, high])
            return bounds
        if key == "cutoffs":
            # (cutoffs, minimums): a cutoff is the longest bond, or
            # (min, max); minimums of 0 are left out.
            cutoffs, minimums = {}, {}
            for pair, cutoff in dict(value).items():
                symbols = (
                    pair.split("-") if isinstance(pair, str) else list(pair)
                )
                if len(symbols) != 2 or not all(
                    isinstance(x, str) for x in symbols
                ):
                    raise ValueError(
                        f"bond cutoffs are per pair, as 'O-Si' or ('O', 'Si'), not {pair!r}"
                    )
                key_ = "-".join(sorted(symbols))
                low, high = bond_range(cutoff)
                cutoffs[key_] = high
                if low:
                    minimums[key_] = low
            return cutoffs, minimums
        if key == "style":
            if value not in STYLES:
                raise ValueError(
                    f"style is one of {', '.join(STYLES)}, not {value!r}"
                )
            return value
        if key == "radiusType":
            if value not in RADIUS_TYPES:
                raise ValueError(
                    f"radius_type is one of {', '.join(RADIUS_TYPES)}, "
                    f"not {value!r}"
                )
            return value
        if key == "bondedOutside":
            if value not in BONDED_OUTSIDE:
                raise ValueError(
                    f"bonded_outside is one of {', '.join(BONDED_OUTSIDE)}, "
                    f"not {value!r}"
                )
            return value
        if key == "hbonds.show":
            if not isinstance(value, bool):
                raise TypeError(
                    f"hydrogen_bonds is True or False, not {value!r}"
                )
            return value
        if key == "hbonds.acceptors":
            if isinstance(value, str) or not all(
                isinstance(sym, str) for sym in value
            ):
                raise TypeError(
                    "hydrogen_bond_acceptors is a list of element symbols"
                )
            return list(dict.fromkeys(value))
        if key == "hbonds.distance":
            low, high = bond_range(value)
            if isinstance(value, numbers.Real) or low > high:
                raise ValueError(
                    "hydrogen_bond_distance is (min, max) in Å, min ≤ max"
                )
            return low, high
        if key == "hbonds.ranges":
            ranges = {}
            for symbol, pair in value.items():
                if not isinstance(symbol, str):
                    raise TypeError(
                        "hydrogen_bond_distance per acceptor has element "
                        f"symbols as keys, not {symbol!r}"
                    )
                try:
                    low, high = ViewerBase._check("hbonds.distance", pair)
                except ValueError:
                    raise ValueError(
                        f"hydrogen_bond_distance of {symbol} is (min, max) "
                        "in Å, min ≤ max"
                    ) from None
                ranges[symbol] = [low, high]
            return ranges
        if key == "hbonds.angle":
            angle = float(value)
            if not 0 <= angle <= 180:
                raise ValueError("hydrogen_bond_angle is 0 to 180 (degrees)")
            return angle
        if key == "hbonds.colour":
            if not (isinstance(value, str) and COLOUR.match(value)):
                raise ValueError(
                    f"hydrogen_bond_colour is #rrggbb, not {value!r}"
                )
            return value
        if key == "planes":
            planes = []
            for plane in value:
                if isinstance(plane, Mapping) and "atoms" in plane:
                    planes.append(check_atom_plane(plane))
                    continue
                h, k, l = (plane.get(n, 0) for n in "hkl")  # noqa: E741
                if not all(isinstance(n, int) for n in (h, k, l)) or not (
                    h or k or l
                ):
                    raise ValueError(
                        "a plane has whole Miller indices h, k, l, not all 0"
                    )
                t = float(plane.get("t", 0.5))
                if not math.isfinite(t):
                    raise ValueError("a plane's position t is a number")
                entry: dict[str, Any] = {
                    "h": h,
                    "k": k,
                    "l": l,
                    "t": t,
                    "show": bool(plane.get("show", True)),
                }
                colour = plane.get("colour")
                if colour is not None:
                    if not (isinstance(colour, str) and COLOUR.match(colour)):
                        raise ValueError(
                            f"a plane colour is #rrggbb, not {colour!r}"
                        )
                    entry["colour"] = colour
                if "scale" in plane:
                    entry["scale"] = check_plane_scale(plane["scale"])
                planes.append(entry)
            return planes
        if key == "arrows.source":
            if value not in ARROW_SOURCES:
                raise ValueError(
                    f"arrow_source is one of {', '.join(ARROW_SOURCES)}, "
                    f"not {value!r}"
                )
            return value
        if key == "symmetry.tolerance":
            return check_tolerance(value)
        if key == "arrows.scale":
            scale = float(value)
            if not (scale > 0 and math.isfinite(scale)):
                raise ValueError("force_scale is a positive number")
            return scale
        if key in ("appearance.polyAlpha", "appearance.planeAlpha"):
            alpha = float(value)
            if not 0 <= alpha <= 1:
                raise ValueError("an opacity is between 0 and 1")
            return alpha
        if key == "appearance.bondRadius":
            radius = float(value)
            if not 0.02 <= radius <= 0.4:
                raise ValueError("bond_radius is between 0.02 and 0.4 (Å)")
            return radius
        if key == "appearance.depthStrength":
            strength = float(value)
            if not 0.1 <= strength <= 0.9:
                raise ValueError("depth_strength is between 0.1 and 0.9")
            return strength
        if key == "appearance.depthCue":
            if not isinstance(value, bool):
                raise TypeError("depth_cue is True or False")
            return value
        if key == "appearance.cellWidth":
            width = float(value)
            if not 0 < width <= MAX_CELL_WIDTH:
                raise ValueError(
                    f"cell_width is above 0 and at most {MAX_CELL_WIDTH:g} (px)"
                )
            return width
        if key == "appearance.cellColour":
            if value is not None and not (
                isinstance(value, str) and COLOUR.match(value)
            ):
                raise ValueError(
                    f"cell_colour is #rrggbb or None, not {value!r}"
                )
            return value
        if key == "appearance.cellDash":
            if value not in CELL_STYLES:
                raise ValueError(
                    f"cell_style is one of {', '.join(CELL_STYLES)}, "
                    f"not {value!r}"
                )
            return value
        if key == "appearance.atomScale":
            scale = float(value)
            if not 0 < scale <= MAX_ATOM_SCALE:
                raise ValueError(
                    f"atom_scale is above 0 and at most {MAX_ATOM_SCALE}"
                )
            return scale
        raise KeyError(key)

    # ------------------------------------------------------------ state

    def get_settings(self) -> dict[str, Any]:
        """The settings, the view and the measurements, as in a settings file.

        Pass it to ``view(..., settings=...)`` to show other structures the
        same way, or save it with ``json.dump``. Measurements name atoms by
        index, so they are drawn on structures with the same atoms (count and
        elements) at those indices, such as the frames of a trajectory or
        relaxations of one structure. The ledger viewer imports the file under
        View › Viewer settings; it ignores the view and the measurements.
        """
        return {
            "stoms_viewer_settings": SETTINGS_VERSION,
            "settings": copy.deepcopy(self.settings),
            "view": copy.deepcopy(self.camera),
            "measurements": copy.deepcopy(self._measurement_items()),
        }

    @property
    def images(self) -> list[Atoms]:
        """Copies of the shown frames."""
        return [_copy(atoms) for atoms in self._images]

    @property
    def selected_atoms(self) -> Atoms:
        """A copy of the shown frame, with its calculator results."""
        return _copy(self._images[self.frame])

    @property
    def measurements(self) -> list[dict[str, Any]]:
        """Positions, distances, angles and dihedrals measured in the viewer
        (📏), and plane angles and distances to a plane.

        Each is ``{"kind", "atoms", "images", "value", "unit"}``: atom indices,
        the periodic image of each atom (cell copies, as clicked) and the value
        on the shown frame (Å or degrees; None when the frame has other atoms).
        A ``"position"`` has one atom; its value is the Cartesian ``(x, y, z)``
        of the clicked copy, in Å.
        A distance also has ``"nearest"``: the distance to the nearest periodic
        image, when that is shorter. A ``"plane-angle"`` (0 to 90°, no atoms)
        and a ``"plane-distance"`` (the atom's signed distance along the
        plane normal, Å) also have ``"planes"``: ``{"h", "k", "l", "t"}`` or
        ``{"atoms", "images"}`` each. Empty when not linked to Python.
        """
        return []

    def _measurement_items(self) -> list[dict[str, Any]]:
        """Measurements as the page keeps them, stored in standalone HTML."""
        return []

    def _api_cache(self) -> dict[str, Any]:
        """Replies to the page's requests, stored in standalone HTML."""
        return {}

    def _page_frames(self) -> list[dict[str, Any]]:
        """The frames' JSON with their symmetry at the current tolerance
        (computed again only when the frames or the tolerance changed)."""
        tolerance = self.symmetry_tolerance
        state = (id(self._frames), tolerance)
        if getattr(self, "_symmetry_state", None) != state:
            embed_symmetry(self._frames, self._images, tolerance)
            self._symmetry_state = state
        return self._frames

    def _answer_symmetry(self, path: str) -> dict[str, Any] | None:
        """The page's request ``structures/frame-<i>/symmetry?tolerance=t``
        (as the ledger server answers it), or None for other paths."""
        match = re.fullmatch(
            r"structures/frame-(\d+)/symmetry(?:\?tolerance=([^&]*))?", path
        )
        if match is None:
            return None
        index = int(match.group(1))
        if index >= len(self._images):
            raise LookupError(f"there is no frame {index}")
        tolerance = check_tolerance(match.group(2) or DEFAULT_TOLERANCE)
        return symmetry_payload(self._images[index], tolerance)

    def _data(self, *, bridge: bool) -> dict[str, Any]:
        return embed_data(
            self._page_frames(),
            frame=self.frame,
            settings=self.settings,
            camera=self.camera,
            profile=self.profile,
            title=self._title,
            bridge=bridge,
            height=self._height,
            # Live viewers ask Python; HTML files have no kernel to ask.
            api=None if bridge else self._api_cache(),
            measurements=self._measurement_items(),
        )

    def to_html(self) -> str:
        """The viewer as a standalone HTML file, in its current state.

        It needs no Python or server: open it in any browser.
        """
        return document(self._data(bridge=False))

    def open_in_browser(
        self, path: str | os.PathLike[str] | None = None
    ) -> Path:
        """Open the viewer in a browser tab of this computer; return the
        HTML file (written to ``path``, else a temporary directory).

        On a remote Jupyter server this opens nothing on your screen: use
        the ⧉ button in the viewer instead.
        """
        if path is None:
            directory = Path(tempfile.mkdtemp(prefix="stoms-view-"))
            path = directory / f"{self._frames[self.frame]['formula']}.html"
        target = Path(path)
        target.write_text(self.to_html(), encoding="utf-8")
        webbrowser.open(target.resolve().as_uri())
        return target

    def _save_html(self, path: Path) -> Path:
        path.write_text(self.to_html(), encoding="utf-8")
        return path

    def __repr__(self) -> str:
        formulas = sorted({f["formula"] for f in self._frames})
        shown = ", ".join(formulas[:3]) + (", …" if len(formulas) > 3 else "")
        count = len(self._frames)
        return (
            f"{type(self).__name__}({count} frame{'s' if count != 1 else ''}: "
            f"{shown}; frame {self.frame})"
        )


def _pixels(value: int | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or not 160 <= value <= 4000:
        raise ValueError("panel sizes are whole pixels from 160 to 4000")
    return value


def check_view(name: str) -> str:
    axis = name[1:] if name.startswith("-") else name
    if axis not in AXES and (name.startswith("-") or name not in VIEWS):
        raise ValueError(
            f"views are {', '.join(VIEWS)} or an axis ({', '.join(AXES)}, "
            "with '-' for the other side)"
        )
    return name
