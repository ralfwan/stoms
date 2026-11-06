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
import os
import re
import tempfile
import webbrowser
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ase import Atoms

from .document import DEFAULT_HEIGHT, document, embed_data
from .frames import _copy

SETTINGS_VERSION = 1
# Defaults of the settings with properties here; they must match
# defaultPrefs() in viewer.js (checked by the browser tests).
DEFAULTS: dict[str, Any] = {
    "cell": True,
    "bonds": False,
    "wrap": False,
    "polyhedra": False,
    "labels": "off",
    "repeat": [1, 1, 1],
    "svgTransparent": True,
    "hiddenElements": [],
    "slice": [[None, None], [None, None], [None, None]],
    "cutoffs": {},
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
    ("appearance", "colours"): {},
    ("appearance", "radii"): {},
}
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
AXIS_NAMES = ("a", "b", "c")
LABELS = ("off", "index", "element", "element-index")
MAX_REPEAT = 12
MAX_ATOM_SCALE = 3.0
# Cell outline: largest width in pixels, line styles (MAX_CELL_WIDTH and
# CELL_DASHES in viewer.js).
MAX_CELL_WIDTH = 6.0
CELL_STYLES = ("solid", "dashed", "dotted")
# Colour by property: values from the geometry (DERIVED_PROPERTIES in
# viewer.js; ring sizes need the ledger server), vector components, how to
# read values, and the palettes (PALETTES in viewer.js; checked by the
# browser tests).
DERIVED = ("coordination", "index", "x", "y", "z", "fa", "fb", "fc")
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
# Looks for set_view: presets and the axes (prefix "-" for the other side).
VIEWS = ("top", "side-a", "side-b")
AXES = ("a", "b", "c", "x", "y", "z")


# Atoms per measurement kind (MEASURE_ATOMS in viewer.js).
MEASURE_ATOMS = {"distance": 2, "angle": 3, "dihedral": 4}


def check_measurements(items: Any) -> list[dict[str, Any]]:
    """Measurements of a settings file, as the viewer keeps them.

    Each is ``{"kind": "distance" | "angle" | "dihedral", "atoms": [ref]}``,
    a ref ``{"index", "image": [i, j, k], "symbol", "count"}`` (the atom, its
    periodic image, its element and the number of atoms of the structure). A
    measurement is drawn on structures with the same atom count and elements
    at its indices. Values are not stored: the viewer computes them.
    """
    if not isinstance(items, list):
        raise ValueError("measurements are a list")
    checked = []
    for k, item in enumerate(items):
        kind = item.get("kind") if isinstance(item, Mapping) else None
        atoms = item.get("atoms") if isinstance(item, Mapping) else None
        if (
            kind not in MEASURE_ATOMS
            or not isinstance(atoms, list)
            or len(atoms) != MEASURE_ATOMS[kind]
        ):
            raise ValueError(
                f"measurement {k} is not a distance (2 atoms), angle (3) or "
                "dihedral (4)"
            )
        refs = []
        for ref in atoms:
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
                    f"measurement {k}: an atom is {{index, image, symbol, "
                    f"count}}, not {ref!r}"
                )
            refs.append(
                {
                    "index": ref["index"],
                    "image": list(ref["image"]),
                    "symbol": ref["symbol"],
                    "count": ref["count"],
                }
            )
        checked.append({"kind": kind, "atoms": refs})
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

    show_cell = _setting("cell", "Whether the unit cell outline is drawn.")
    show_bonds = _setting("bonds", "Whether bonds are drawn (ball and stick).")
    wrap = _setting("wrap", "Whether atoms are drawn wrapped into the cell.")
    polyhedra = _setting(
        "polyhedra", "Whether coordination polyhedra are drawn."
    )
    labels = _setting(
        "labels", 'Atom labels: "off", "index", "element" or "element-index".'
    )
    repeat = _setting(
        "repeat", "Copies of the cell along a, b and c (periodic axes only)."
    )
    transparent = _setting(
        "svgTransparent",
        "Whether saved SVG images have no background (in light colours).",
    )

    atom_scale = _nested(
        "appearance",
        "atomScale",
        "Factor on the automatic atom radii (not on radii set per element).",
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
        "Sphere radii per element in Å; others are automatic (atom_scale).",
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
    def bond_cutoffs(self) -> dict[str, float]:
        """Bond cutoffs in Å per element pair, as ``{"O-Si": 2.0}`` (symbols
        sorted). Pairs not given get the viewer's default."""
        return dict(self.settings.get("cutoffs") or {})

    @bond_cutoffs.setter
    def bond_cutoffs(self, value: Any) -> None:
        self._update_settings({"cutoffs": self._check("cutoffs", value)})

    @property
    def planes(self) -> list[dict[str, Any]]:
        """Miller planes: h·x + k·y + l·z = t in fractional coordinates,
        each ``{"h", "k", "l", "t", "show", "colour"}``."""
        return copy.deepcopy(self.settings.get("planes") or [])

    @planes.setter
    def planes(self, value: Any) -> None:
        self._update_settings({"planes": self._check("planes", value)})

    def add_plane(
        self,
        h: int,
        k: int,
        l: int,  # noqa: E741  (Miller index)
        t: float | None = None,
        *,
        distance: float | None = None,
        colour: str | None = None,
        show: bool = True,
    ) -> None:
        """Draw the Miller plane (h k l) at h·x + k·y + l·z = t.

        ``t`` is fractional (in units of the spacing d, default 0.5);
        ``distance`` instead gives the position in Å from the origin along
        the plane normal (t = distance / d, with d of the shown frame).
        """
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
        plane: dict[str, Any] = {
            "h": h,
            "k": k,
            "l": l,
            "t": 0.5 if t is None else t,
            "show": show,
        }
        if colour is not None:
            plane["colour"] = colour
        self.planes = [*self.planes, plane]

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
        ``"fb"``, ``"fc"``. ``source`` (``"arrays"``, ``"info"``,
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
            "svgTransparent",
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
            cutoffs = {}
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
                distance = float(cutoff)
                if not (distance >= 0 and math.isfinite(distance)):
                    raise ValueError("bond cutoffs are numbers ≥ 0 (Å)")
                cutoffs["-".join(sorted(symbols))] = distance
            return cutoffs
        if key == "planes":
            planes = []
            for plane in value:
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
                planes.append(entry)
            return planes
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
        """Distances, angles and dihedrals measured in the viewer (📏).

        Each is ``{"kind", "atoms", "images", "value", "unit"}``: atom indices,
        the periodic image of each atom (cell copies, as clicked) and the value
        on the shown frame (Å or degrees; None when the frame has other atoms).
        A distance also has ``"nearest"``: the distance to the nearest periodic
        image, when that is shorter. Empty when not linked to Python.
        """
        return []

    def _measurement_items(self) -> list[dict[str, Any]]:
        """Measurements as the page keeps them, stored in standalone HTML."""
        return []

    def _api_cache(self) -> dict[str, Any]:
        """Replies to the page's requests, stored in standalone HTML."""
        return {}

    def _data(self, *, bridge: bool) -> dict[str, Any]:
        return embed_data(
            self._frames,
            frame=self.frame,
            settings=self.settings,
            camera=self.camera,
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
