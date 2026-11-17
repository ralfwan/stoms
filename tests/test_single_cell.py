"""Single cell only (viewerPrefs.singleCell; viewer.js run in Node, and its
Python setting): nothing drawn outside the stored cell, the overridden
settings kept, and no change while it is off."""

import json
from typing import Any

import numpy as np
import pytest
from ase import Atoms
from test_bond_search import _payload
from test_polyhedra import rutile
from test_repeat_matrix import OVERLAY
from test_web_viewer import _evaluate

TOLERANCE = 1e-6
MATRIX = [[2, 1, 0], [-1, 1, 0], [0, 0, 1]]


def _rutile_with_edges() -> dict[str, Any]:
    """Rutile doubled along c, slightly sheared, with atoms stored outside
    the cell: the Ti at (½, ½, ¼) has its octahedron inside the cell, the
    other three Ti reach into neighbouring copies."""
    atoms = rutile().repeat((1, 1, 2))
    atoms.set_cell(
        atoms.cell[:] + [[0, 0, 0], [0.3, 0, 0], [0.1, 0.2, 0]],
        scale_atoms=True,
    )
    atoms.positions[2] -= atoms.cell[0]
    atoms.positions[3] += atoms.cell[1] + atoms.cell[2]
    atoms.positions[7] -= atoms.cell[2]
    return _payload(atoms, "rutile-edges")


def _water_at_edge() -> dict[str, Any]:
    """A surface-like O near the a face and a water whose H bonds to it
    across that face (the H and the water stored at negative x)."""
    acceptor = np.array([0.4, 5.0, 10.0])
    h1 = np.array([-0.4, 5.0, 11.6])
    o_water = h1 + 0.97 * (h1 - acceptor) / np.linalg.norm(h1 - acceptor)
    h2 = o_water + np.array([-0.3, 0.9, 0.2])
    return _payload(
        Atoms(
            "OOHH",
            positions=[acceptor, o_water, h1, h2],
            cell=[10.0, 10.0, 25.0],
            pbc=True,
        ),
        "water-edge",
    )


# Everything that could reach outside the cell, switched on: bonds and
# polyhedra with partners outside, hydrogen bonds, a transformation matrix
# (and a repeat), outlines of every copy, a Miller plane and planes through
# atoms (one a patch, both extended), rings, labels and force arrows.
_SETTINGS = f"""
  viewerPrefs.cutoffs = bondCutoffs(structure); viewerPrefs.bonds = true; viewerPrefs.polyhedra = true;
  viewerPrefs.bondedOutside = 'partners'; viewerPrefs.hbonds.show = true;
  viewerPrefs.repeat = [2, 2, 2]; viewerPrefs.repeatMatrix = {json.dumps(MATRIX)};
  viewerPrefs.wrap = false; viewerPrefs.cell = true; viewerPrefs.repeatCellOutline = true; viewerPrefs.storedCellOutline = true;
  viewerPrefs.labels = 'element-index'; viewerPrefs.arrows.show = true;
  const ref = (index, image) => ({{ index, image, symbol: structure.symbols[index], count: structure.symbols.length }});
  viewerPrefs.planes = [{{ h: 1, k: 1, l: 0, t: 1, show: true, scale: 3 }},
    {{ atoms: [ref(0, [0, 0, 0]), ref(1, [1, 0, 0]), ref(2, [0, 1, 0])], show: true, patch: true, scale: 4 }},
    {{ atoms: [ref(0, [0, 0, 0]), ref(1, [0, 0, 0]), ref(3, [0, 0, 0])], show: true, patch: false, scale: 2 }}];
  measureState.items = [{{ kind: 'distance', atoms: [ref(0, [0, 0, 0]), ref(1, [1, 0, 0])] }}];
"""
_ARGS = (
    "{ vectors: structure.positions.map((p, i) => [0.1 * i, -0.05, 0.02 * i]),"
    " magnitudes: structure.positions.map((p, i) => Math.hypot(0.1 * i, 0.05, 0.02 * i)),"
    " included: structure.positions.map(() => true) },"
    " { rings: [{ size: 3, points: [structure.positions[0], structure.positions[1], structure.positions[3]] },"
    "   { size: 3, points: [positionsOf(structure)[0], positionsOf(structure)[1], positionsOf(structure)[3]] }]"
    "   .map((r) => ({ ...r, centre: r.points.reduce((a, p) => a.map((v, k) => v + p[k] / 3), [0, 0, 0]) })) }"
)


def _scene(single: str, *, args: str = _ARGS, wrap: bool = False) -> str:
    """JS: the scene with _SETTINGS (Wrap as `wrap`) and singleCell =
    `single` (a JS value), as JSON-able parts."""
    return (
        "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]; sharedView.scale = 20;"
        f" {_SETTINGS}; viewerPrefs.singleCell = {single}; viewerPrefs.wrap = {json.dumps(wrap)};"
        f" const sc = buildScene(structure, {OVERLAY}, {args});"
        " const { structure: _s, overlay: _o, ...rest } = sc;"
        " return { scene: rest, json: JSON.stringify(rest) }; })()"
    )


def _outside(cell: Any, points: Any) -> list[Any]:
    """The points (Å) whose fractional coordinates leave [0, 1]."""
    if not len(points):
        return []
    fractional = np.asarray(points) @ np.linalg.inv(np.asarray(cell))
    bad = np.any(
        (fractional < -TOLERANCE) | (fractional > 1 + TOLERANCE), axis=1
    )
    return fractional[bad].tolist()


def _drawn_points(scene: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        "atoms": [a["position"] for a in scene["atoms"]],
        "bonds": [p for b in scene["halfBonds"] for p in (b["from"], b["to"])],
        "hbonds": [p for b in scene["hbonds"] for p in (b["from"], b["to"])],
        "polyhedra": [
            p
            for poly in scene["polyhedra"]
            for f in poly["faces"]
            for p in f["points"]
        ],
        "planes": [
            p for plane in scene["planes"] for p in plane["polygon"]["points"]
        ],
        "rings": [p for ring in scene["rings"] for p in ring["points"]],
        "labels": [label["position"] for label in scene["labels"]],
        "outline": [
            p
            for edge in scene["cellEdges"] + scene["storedEdges"]
            for p in edge
        ],
    }


@pytest.mark.parametrize("structure", [_rutile_with_edges(), _water_at_edge()])
def test_nothing_is_drawn_outside_the_cell(structure: dict[str, Any]) -> None:
    off, on = _evaluate(
        (_scene("false"), structure), (_scene("true"), structure)
    )
    cell = structure["cell"]
    count = len(structure["symbols"])
    # Off: the setup does reach outside the stored cell.
    assert any(
        _outside(cell, points)
        for points in _drawn_points(off["scene"]).values()
    )
    # On: nothing drawn leaves the cell.
    for kind, points in _drawn_points(on["scene"]).items():
        assert _outside(cell, points) == [], kind
    scene = on["scene"]
    # Each stored atom exactly once, in the cell itself, none bonded outside.
    assert sorted(a["index"] for a in scene["atoms"]) == list(range(count))
    assert all(a["image"] == [0, 0, 0] for a in scene["atoms"])
    assert scene["extraAtoms"] == 0
    assert scene["visibleAtoms"] == scene["totalAtoms"] == count
    # The stored cell's outline only, and no transformation.
    assert len(scene["cellEdges"]) == 12 and scene["storedEdges"] == []
    assert scene["transform"] is None
    assert scene["cellNote"] == "single cell only is on"
    # Measurements and arrows are unchanged: the distance to an image keeps
    # its value as with Wrap (atoms are wrapped, as Wrap wraps them).
    [wrapped] = _evaluate((_scene("false", wrap=True), structure))
    assert scene["marks"] == wrapped["scene"]["marks"]
    assert len(scene["arrows"]) == count


def test_edge_polyhedra_are_left_out() -> None:
    structure = _rutile_with_edges()
    off, on = _evaluate(
        (_scene("false"), structure), (_scene("true"), structure)
    )
    # Off: all four TiO6 octahedra, in every copy of the matrix's cell.
    assert len(off["scene"]["polyhedra"]) > 4
    # On: only the octahedron of the Ti at (½, ½, ¼), complete in the cell.
    [polyhedron] = on["scene"]["polyhedra"]
    points = {
        tuple(np.round(p, 6)) for f in polyhedron["faces"] for p in f["points"]
    }
    assert len(points) == 6
    # The other Ti are drawn as atoms; bonds stay inside.
    assert len(on["scene"]["halfBonds"]) > 0


def test_hydrogen_bond_across_the_face_is_left_out() -> None:
    structure = _water_at_edge()
    off, on = _evaluate(
        (_scene("false"), structure), (_scene("true"), structure)
    )
    assert len(off["scene"]["hbonds"]) >= 1
    assert on["scene"]["hbonds"] == []


def test_planes_are_clipped_to_the_cell() -> None:
    structure = _rutile_with_edges()
    off, on = _evaluate(
        (_scene("false"), structure), (_scene("true"), structure)
    )
    # The Miller plane fills its cut of the cell; the patch is cut at the
    # cell's faces (or left out where nothing of it is inside).
    assert len(off["scene"]["planes"]) == len(on["scene"]["planes"]) == 3
    miller, patch, _ = on["scene"]["planes"]
    # The extended Miller plane is its cut of the cell (a rectangle); the
    # extended triangular patch around its atoms gains corners at the faces.
    assert len(miller["polygon"]["points"]) == 4
    assert patch["polygon"]["patch"] is True
    assert len(patch["polygon"]["points"]) > 3


def test_clip_to_cell() -> None:
    cell = [[2.0, 0, 0], [0, 2.0, 0], [0, 0, 2.0]]
    square = (
        "({ points: [[-1, -1, 1], [3, -1, 1], [3, 3, 1], [-1, 3, 1]],"
        " normal: [0, 0, 1], centre: [1, 1, 1] })"
    )
    clipped, inside, outside, flat = _evaluate(
        (f"clipToCell({square}, structure.cell)", {"cell": cell}),
        (
            "clipToCell({ points: [[0.5, 0.5, 1], [1.5, 0.5, 1], [1, 1.5, 1]],"
            " normal: [0, 0, 1], centre: [1, 0.8, 1] }, structure.cell).points",
            {"cell": cell},
        ),
        (
            "clipToCell({ points: [[3, 3, 1], [4, 3, 1], [4, 4, 1]],"
            " normal: [0, 0, 1], centre: [3.5, 3.5, 1] }, structure.cell)",
            {"cell": cell},
        ),
        (
            f"clipToCell({square}, structure.cell).points.length",
            {"cell": [[2.0, 0, 0], [0, 2.0, 0], [0, 0, 0]]},
        ),
    )
    assert sorted(map(tuple, clipped["points"])) == [
        (0, 0, 1),
        (0, 2, 1),
        (2, 0, 1),
        (2, 2, 1),
    ]
    assert clipped["centre"] == [1, 1, 1]
    assert inside == [[0.5, 0.5, 1], [1.5, 0.5, 1], [1, 1.5, 1]]
    assert outside is None
    # Without a cell volume nothing is clipped.
    assert flat == 4


def test_switching_off_restores_the_previous_scene() -> None:
    structure = _rutile_with_edges()

    def toggled(final: str) -> str:
        return (
            "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]; sharedView.scale = 20;"
            f" {_SETTINGS};"
            " const settings = () => JSON.stringify(viewerPrefs);"
            " const build = () => { const { structure: _s, overlay: _o, ...rest } ="
            f" buildScene(structure, {OVERLAY}, {_ARGS}); return JSON.stringify(rest); }};"
            " viewerPrefs.singleCell = false; const before = build(), stored = settings();"
            " viewerPrefs.singleCell = true; const during = build(); const kept = settings();"
            f" viewerPrefs.singleCell = {final}; const after = build();"
            " return { before, during, after, same: stored === kept.replace('\"singleCell\":true', '\"singleCell\":false') }; })()"
        )

    [result] = _evaluate((toggled("false"), structure))
    assert result["during"] != result["before"]
    assert result["after"] == result["before"]
    # The settings it overrides are untouched while it is on.
    assert result["same"] is True


def test_off_by_default_and_unchanged_scenes() -> None:
    structure = _rutile_with_edges()
    default, normalised, kept, junk = _evaluate(
        ("defaultPrefs().singleCell", {}),
        ("normalizePrefs({}).singleCell", {}),
        ("normalizePrefs({ singleCell: true }).singleCell", {}),
        ("normalizePrefs({ singleCell: 'yes' }).singleCell", {}),
    )
    assert (default, normalised, kept, junk) == (False, False, True, False)
    # A scene without the key (older settings) is the scene with it off.
    without = (
        "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]; sharedView.scale = 20;"
        f" {_SETTINGS}; delete viewerPrefs.singleCell;"
        f" const {{ structure: _s, overlay: _o, ...rest }} = buildScene(structure, {OVERLAY}, {_ARGS});"
        " return { json: JSON.stringify(rest) }; })()"
    )
    absent, off = _evaluate((without, structure), (_scene("false"), structure))
    assert absent["json"] == off["json"]


def test_shown_cell_ignores_repeat_and_matrix() -> None:
    structure = _rutile_with_edges()
    shown = (
        "(() => { viewerPrefs.repeat = [3, 2, 2]; viewerPrefs.repeatMatrix = MATRIX;"
        " viewerPrefs.singleCell = SINGLE; const c = shownCell(structure);"
        " return { copies: c.copies, transformed: c.transformed, note: c.note,"
        " text: transformNote(structure) }; })()"
    ).replace("MATRIX", json.dumps(MATRIX))
    on, off = _evaluate(
        (shown.replace("SINGLE", "true"), structure),
        (shown.replace("SINGLE", "false"), structure),
    )
    assert on == {
        "copies": 1,
        "transformed": False,
        "note": "single cell only is on",
        "text": "Transformation matrix not applied: single cell only is on.",
    }
    assert off["copies"] == 3 and off["transformed"] is True
