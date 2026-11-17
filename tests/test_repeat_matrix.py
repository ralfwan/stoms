"""Repeat by a transformation matrix (viewer.js, run in Node; and its Python
setting): validation, atoms of the new cell, a diagonal matrix drawing
exactly what the repeat draws, measurements, slices, planes, wrap and rings
with the new cell."""

import json
from typing import Any

import numpy as np
import pytest
from ase import Atoms
from ase.build import fcc111, graphene
from test_bond_search import _payload, water_on_surface
from test_polyhedra import rutile
from test_web_viewer import _evaluate

from stoms.viewer import view
from stoms.viewer.base import check_repeat_matrix

THEME = (
    "{ text: '#000000', halo: '#ffffff', cell: '#888888', accent: '#ff0000' }"
)
ROOT3_60 = [[1, 1, 0], [-1, 2, 0], [0, 0, 1]]
ROOT3_120 = [[2, 1, 0], [-1, 1, 0], [0, 0, 1]]
ROOT2 = [[1, 1, 0], [-1, 1, 0], [0, 0, 1]]
OVERLAY = "{ colour: (i, s) => elementColor(s), value: (i) => String(i) }"


def _scene(settings: str, *, args: str = "null") -> str:
    """JS: the scene of `structure` with these settings (JS statements)."""
    return (
        "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]; sharedView.scale = 20;"
        f" {settings};"
        f" return buildScene(structure, {OVERLAY}, {args}); }})()"
    )


def _atoms(settings: str) -> str:
    return (
        f"(() => {{ const sc = {_scene(settings)};"
        " return { atoms: sc.atoms.map((a) => ({ index: a.index, image: a.image, position: a.position, extra: Boolean(a.extra) })),"
        " total: sc.totalAtoms, shown: sc.visibleAtoms, cell: sc.cellEdges, stored: sc.storedEdges,"
        " note: sc.cellNote, transform: sc.transform, planes: sc.planes, rings: sc.rings.length,"
        " marks: sc.marks }; })()"
    )


def _fractional(cell: Any, points: Any) -> np.ndarray:
    return np.asarray(points) @ np.linalg.inv(np.asarray(cell))


# ---------------------------------------------------------------- settings


def test_normalize_keeps_valid_matrices_and_drops_invalid_ones() -> None:
    bad = [
        [[1.5, 0, 0], [0, 1, 0], [0, 0, 1]],  # not whole
        [[1, 0, 0], [1, 0, 0], [0, 0, 1]],  # singular
        [[0, 1, 0], [1, 0, 0], [0, 0, 1]],  # left-handed
        [[13, 0, 0], [0, 1, 0], [0, 0, 1]],  # entry too large
        [[1, 0], [0, 1]],
        "[[1,0,0],[0,1,0],[0,0,1]]",
        [[1, 0, 0], [0, 1, 0], [0, 0, "2"]],
    ]
    results = _evaluate(
        (
            f"normalizePrefs({{ repeatMatrix: {json.dumps(ROOT3_120)}, storedCellOutline: true }})",
            {},
        ),
        *[
            (
                f"normalizePrefs({{ repeatMatrix: {json.dumps(m)} }}).repeatMatrix",
                {},
            )
            for m in bad
        ],
        (
            "normalizePrefs({ repeatMatrix: [[12, 0, 0], [0, 12, 0], [0, 0, 12]] }).repeatMatrix",
            {},
        ),
        (
            "[repeatMatrixProblem([[12, 1, 0], [0, 12, 1], [1, 0, 12]]),"
            " repeatMatrixProblem([[1, 0, 0], [1, 0, 0], [0, 0, 1]])]",
            {},
        ),
    )
    first, *dropped, largest, problems = results
    assert first["repeatMatrix"] == ROOT3_120
    assert first["storedCellOutline"] is True
    assert dropped == [None] * len(bad)
    # The largest repeat (12³ copies) is allowed, one more copy is not.
    assert largest == [[12, 0, 0], [0, 12, 0], [0, 0, 12]]
    assert "at most 1728" in problems[0]
    assert "determinant 0" in problems[1]


@pytest.mark.parametrize(
    "old",
    [
        {},
        # 0.10.0 (repeat along a and b only, no matrix).
        {"version": 2, "repeat": [3, 2], "cell": True},
        {"version": 1, "repeat": [2, 2, 2], "wrap": True},
    ],
)
def test_old_settings_keep_the_repeat(old: dict[str, Any]) -> None:
    [prefs] = _evaluate((f"normalizePrefs({json.dumps(old)})", {}))
    assert prefs["repeatMatrix"] is None
    assert prefs["storedCellOutline"] is False
    expected = [*old.get("repeat", [1, 1]), 1, 1][:3]
    if len(old.get("repeat", [])) == 3:
        expected = old["repeat"]
    assert prefs["repeat"] == expected


def test_python_repeat_takes_a_matrix_or_a_list() -> None:
    viewer = view(fcc111("Pt", size=(1, 1, 3), vacuum=5.0))
    assert viewer.repeat == [1, 1, 1]
    viewer.repeat = ROOT3_60
    assert viewer.repeat == ROOT3_60
    assert viewer.settings["repeatMatrix"] == ROOT3_60
    viewer.repeat = np.array(ROOT2)
    assert viewer.settings["repeatMatrix"] == ROOT2
    # A 3-list is the diagonal repeat and drops the matrix.
    viewer.repeat = [2, 2, 1]
    assert viewer.repeat == [2, 2, 1]
    assert viewer.settings["repeatMatrix"] is None
    viewer.show_stored_cell = True
    assert viewer.settings["storedCellOutline"] is True
    # The frames keep the stored cell: the matrix is display only.
    viewer.repeat = ROOT3_60
    assert np.allclose(viewer._frames[0]["cell"], viewer._images[0].cell[:])


@pytest.mark.parametrize(
    ("matrix", "message"),
    [
        ([[1.5, 0, 0], [0, 1, 0], [0, 0, 1]], "whole numbers"),
        ([[True, 0, 0], [0, 1, 0], [0, 0, 1]], "whole numbers"),
        ([[1, 0, 0], [2, 0, 0], [0, 0, 1]], "determinant 0"),
        ([[0, 1, 0], [1, 0, 0], [0, 0, 1]], "left-handed"),
        ([[13, 0, 0], [0, 1, 0], [0, 0, 1]], "from -12 to 12"),
        ([[12, 1, 0], [0, 12, 1], [1, 0, 12]], "at most 1728"),
        ([[1, 0], [0, 1]], "3 rows of 3"),
        ([[1, 0, 0], [0, 1, 0], [0, 0]], "3 rows of 3"),
    ],
)
def test_python_rejects_bad_matrices(matrix: Any, message: str) -> None:
    viewer = view(fcc111("Pt", size=(1, 1, 3), vacuum=5.0))
    with pytest.raises(ValueError, match=message):
        viewer.repeat = matrix
    assert viewer.settings.get("repeatMatrix") is None
    assert check_repeat_matrix(None) is None


# ---------------------------------------------------------------- the new cell


@pytest.mark.parametrize(
    ("atoms", "matrix", "copies"),
    [
        (fcc111("Pt", size=(1, 1, 3), vacuum=5.0), ROOT3_60, 3),
        (graphene(), ROOT3_120, 3),
        (
            fcc111("Pt", size=(1, 1, 3), vacuum=5.0),
            [[2, -1, 0], [2, 1, 0], [0, 0, 1]],
            4,
        ),
        (rutile(), [[1, 1, 0], [-1, 1, 0], [0, 0, 2]], 4),
    ],
)
def test_atoms_fill_the_new_cell_once(
    atoms: Atoms, matrix: list[list[int]], copies: int
) -> None:
    structure = _payload(atoms, "surface")
    [scene] = _evaluate(
        (
            _atoms(
                f"viewerPrefs.wrap = true; viewerPrefs.repeatMatrix = {json.dumps(matrix)}"
            ),
            structure,
        )
    )
    n = len(atoms)
    assert scene["total"] == copies * n
    assert len(scene["atoms"]) == copies * n
    assert scene["transform"] == {"matrix": matrix, "copies": copies}
    # Every atom `copies` times, never twice at the same place modulo the new
    # lattice (no doubles at faces), and inside the new cell (wrapped: ASE's
    # fcc111 has an atom outside the stored cell, which the repeat and the
    # matrix otherwise draw where it is).
    outline = np.asarray(matrix) @ atoms.cell[:]
    new_cell = outline.copy()
    if not new_cell[2].any():
        new_cell[2] = [0, 0, 1]  # graphene: c = 0
    g = _fractional(new_cell, [a["position"] for a in scene["atoms"]])
    periodic = [0, 1] if not atoms.pbc[2] else [0, 1, 2]
    # (An atom on a face of the new cell is drawn at one of them.)
    assert (g[:, periodic] > -1e-6).all() and (g[:, periodic] < 1 + 1e-6).all()
    reduced = {
        (a["index"], *np.round(np.mod(gk[periodic] + 1e-7, 1.0), 5))
        for a, gk in zip(scene["atoms"], g, strict=True)
    }
    assert len(reduced) == copies * n
    counts = np.bincount([a["index"] for a in scene["atoms"]], minlength=n)
    assert (counts == copies).all()
    # The outline is the new cell.
    corners = {tuple(np.round(p, 6)) for edge in scene["cell"] for p in edge}
    expected = {
        tuple(np.round(i * outline[0] + j * outline[1] + k * outline[2], 6))
        for i in (0, 1)
        for j in (0, 1)
        for k in (0, 1)
    }
    assert corners == expected


def test_root3_on_a_hexagonal_surface_triples_the_atoms() -> None:
    # Acceptance: (√3×√3)R30° gives 3× the atoms of the primitive surface
    # cell, through the preset for the angle between a and b.
    slab = fcc111("Pt", size=(1, 1, 4), vacuum=6.0)
    structure = _payload(slab, "pt111")
    [presets, scene, plain] = _evaluate(
        (
            "repeatPresets(structure).map(([label, matrix]) => [label, matrix])",
            structure,
        ),
        (
            _atoms(
                "viewerPrefs.repeatMatrix = repeatPresets(structure)[0][1]"
            ),
            structure,
        ),
        (_atoms("viewerPrefs.repeatMatrix = null"), structure),
    )
    assert presets[0] == ["(√3×√3)R30°", ROOT3_60]
    assert [label for label, _ in presets] == [
        "(√3×√3)R30°",
        "c(2×2), primitive",
        "p(2×1)",
        "c(4×2), primitive",
    ]
    assert len(scene["atoms"]) == 3 * len(plain["atoms"]) == 3 * len(slab)
    assert scene["shown"] == 3 * len(slab)


def test_graphene_preset_suits_120_degrees() -> None:
    [presets] = _evaluate(
        (
            "repeatPresets(structure).map(([, matrix]) => matrix)",
            _payload(graphene(), "g"),
        )
    )
    assert presets[0] == ROOT3_120


def test_non_periodic_axes_keep_one_copy() -> None:
    structure = _payload(fcc111("Pt", size=(1, 1, 3), vacuum=5.0), "slab")
    [coupled, diagonal, molecule, needs_c] = _evaluate(
        (
            _atoms(
                "viewerPrefs.repeatMatrix = [[1, 0, 1], [0, 1, 0], [0, 0, 1]]"
            ),
            structure,
        ),
        (
            _atoms(
                "viewerPrefs.repeatMatrix = [[2, 0, 0], [0, 1, 0], [0, 0, 3]]"
            ),
            structure,
        ),
        (
            _atoms(
                "viewerPrefs.repeatMatrix = [[2, 0, 0], [0, 1, 0], [0, 0, 1]]"
            ),
            {**structure, "pbc": [False, False, False]},
        ),
        # b′ = c and c′ = −b: in the surface only a is left (determinant 0).
        (
            _atoms(
                "viewerPrefs.repeatMatrix = [[2, 0, 0], [0, 0, 1], [0, -1, 0]]"
            ),
            structure,
        ),
    )
    assert len(coupled["atoms"]) == 3
    assert (
        coupled["note"]
        == "matrix entries along non-periodic axes are left out"
    )
    # As the repeat: c is not periodic, so no copies along it (and no note).
    assert len(diagonal["atoms"]) == 6
    assert diagonal["note"] is None
    assert len(molecule["atoms"]) == 3
    assert molecule["note"] is None
    assert len(needs_c["atoms"]) == 3
    assert needs_c["transform"] is None
    assert (
        needs_c["note"]
        == "the transformation matrix needs non-periodic axes: shown without it"
    )


# ---------------------------------------------------------------- a diagonal matrix is the repeat


def _shifted_rutile() -> dict[str, Any]:
    """Rutile, slightly sheared, with atoms outside the stored cell (the
    repeat copies atoms where they are), plus a water H for hydrogen bonds."""
    atoms = rutile()
    atoms.set_cell(
        atoms.cell[:] + [[0, 0, 0], [0.3, 0, 0], [0.1, 0.2, 0]],
        scale_atoms=True,
    )
    atoms.positions[2] -= atoms.cell[0]
    atoms.positions[3] += atoms.cell[1] + atoms.cell[2]
    return _payload(atoms, "rutile-shifted")


# Everything that buildScene draws, switched on: bonds and polyhedra (with
# atoms bonded outside the repeat), labels, a slice, a Miller plane, rings,
# force arrows, measurements, picked and selected atoms, depth cueing.
_EVERYTHING = """
  viewerPrefs.cutoffs = bondCutoffs(structure); viewerPrefs.bonds = true; viewerPrefs.polyhedra = true;
  viewerPrefs.bondedOutside = 'partners'; viewerPrefs.labels = 'element-index';
  viewerPrefs.slice = [[null, null], [null, null], [0.2, null]];
  viewerPrefs.planes = [{ h: 1, k: 1, l: 0, t: 1, show: true }];
  viewerPrefs.arrows.show = true; viewerPrefs.appearance.depthCue = true;
  viewerPrefs.style = STYLE;
  measureState.items = [{ kind: 'distance', atoms: [
    { index: 0, image: [0, 0, 0], symbol: structure.symbols[0], count: structure.symbols.length },
    { index: 2, image: [1, 0, 0], symbol: structure.symbols[2], count: structure.symbols.length }] }];
  measureState.pending = [{ index: 1, image: [0, 1, 0], symbol: structure.symbols[1], count: structure.symbols.length }];
  paintState.selected = [{ index: 4, symbol: structure.symbols[4], count: structure.symbols.length }];
"""
_ARGS = (
    "{ vectors: structure.positions.map((p, i) => [0.1 * i, -0.05, 0.02 * i]),"
    " magnitudes: structure.positions.map((p, i) => Math.hypot(0.1 * i, 0.05, 0.02 * i)),"
    " included: structure.positions.map(() => true) },"
    " { rings: [{ size: 3, points: [structure.positions[0], structure.positions[2], structure.positions[4]],"
    "   centre: structure.positions[0].map((v, k) => (v + structure.positions[2][k] + structure.positions[4][k]) / 3) }] }"
)
_MOTION = (
    ", { q: [0.5, 0, 0.25], vectors: structure.positions.map((p, i) => [0.1, 0.02 * i, 0, 0, 0.05, 0.01]),"
    " scale: 1, phase: 0.7, moving: true, arrows: true, bonds: 'fixed', amplitude: 0.3 }"
)


def _drawn(settings: str, args: str) -> str:
    """JS: the scene (without the outline), its display list and its SVG,
    each as JSON."""
    return (
        f"(() => {{ const sc = {_scene(settings, args=args)};"
        f" const list = displayList(sc, 400, 400, {THEME}, {{ tripod: false }});"
        " const svg = panelsToSvg([{ stage: { clientWidth: 400, clientHeight: 400 }, scene: sc }], { transparent: true, tripod: false });"
        " const { cellEdges, storedEdges, transform, cellNote, structure: _s, overlay: _o, ...rest } = sc;"
        " return { scene: JSON.stringify(rest), list: JSON.stringify(list), svg, cell: cellEdges, stored: storedEdges }; })()"
    )


@pytest.mark.parametrize("style", ["ball-and-stick", "stick", "wireframe"])
@pytest.mark.parametrize(
    ("structure", "repeat"),
    [
        (_shifted_rutile(), [2, 3, 1]),
        (_shifted_rutile(), [1, 2, 2]),
        # c is not periodic: the repeat and the matrix keep one copy along it.
        (_payload(water_on_surface(), "water"), [2, 2, 3]),
    ],
)
@pytest.mark.parametrize("motion", [False, True])
def test_a_diagonal_matrix_draws_what_the_repeat_draws(
    style: str, structure: dict[str, Any], repeat: list[int], motion: bool
) -> None:
    settings = _EVERYTHING.replace("STYLE", f"'{style}'")
    if structure["id"] == "water":
        settings += "; viewerPrefs.hbonds.show = true; viewerPrefs.slice = emptySlice();"
    args = _ARGS + (_MOTION if motion else "")
    diagonal = [[repeat[0], 0, 0], [0, repeat[1], 0], [0, 0, repeat[2]]]
    for wrap in (False, True):
        common = f"{settings}; viewerPrefs.wrap = {json.dumps(wrap)}"
        [by_repeat, by_matrix, outline_off] = _evaluate(
            (
                _drawn(
                    f"{common}; viewerPrefs.repeat = {repeat}; viewerPrefs.repeatMatrix = null",
                    args,
                ),
                structure,
            ),
            (
                _drawn(
                    f"{common}; viewerPrefs.repeat = [1, 1, 1]; viewerPrefs.repeatMatrix = {diagonal}",
                    args,
                ),
                structure,
            ),
            (
                _drawn(
                    f"{common}; viewerPrefs.cell = false; viewerPrefs.repeat = [1, 1, 1]; viewerPrefs.repeatMatrix = {diagonal}",
                    args,
                ),
                structure,
            ),
        )
        assert by_matrix["scene"] == by_repeat["scene"]
        [no_outline_repeat] = _evaluate(
            (
                _drawn(
                    f"{common}; viewerPrefs.cell = false; viewerPrefs.repeat = {repeat}; viewerPrefs.repeatMatrix = null",
                    args,
                ),
                structure,
            )
        )
        # Without the outline, the display lists and SVG are the same, byte
        # for byte.
        assert outline_off["list"] == no_outline_repeat["list"]
        assert outline_off["svg"] == no_outline_repeat["svg"]
        # With it, the matrix draws its own (bigger) cell: 12 edges.
        assert len(by_repeat["cell"]) == len(by_matrix["cell"]) == 12
        assert by_matrix["stored"] == []
    # The scenes really hold everything switched on.
    scene = json.loads(by_repeat["scene"])
    assert (
        scene["halfBonds"]
        and scene["arrows"]
        and scene["marks"]
        and scene["labels"]
    )
    assert scene["rings"] and scene["picked"]
    if structure["id"] != "water":
        assert scene["polyhedra"] and scene["planes"] and scene["extraAtoms"]
    else:
        assert scene["hbonds"]


def test_stored_cell_outline_beside_the_new_one() -> None:
    structure = _payload(graphene(), "g")
    [with_stored, without, off] = _evaluate(
        (
            _drawn(
                f"viewerPrefs.repeatMatrix = {ROOT3_120}; viewerPrefs.storedCellOutline = true",
                "null",
            ),
            structure,
        ),
        (
            _drawn(
                f"viewerPrefs.repeatMatrix = {ROOT3_120}; viewerPrefs.storedCellOutline = false",
                "null",
            ),
            structure,
        ),
        (
            _drawn(
                "viewerPrefs.repeatMatrix = null; viewerPrefs.storedCellOutline = true",
                "null",
            ),
            structure,
        ),
    )
    assert len(with_stored["stored"]) == 12 and len(with_stored["cell"]) == 12
    assert without["stored"] == []
    # Without a matrix the stored cell is the outline: nothing extra.
    assert off["stored"] == []
    lines = [p for p in json.loads(with_stored["list"]) if p["kind"] == "line"]
    dotted = [p for p in lines if p.get("dash") and p["width"] == 0.5]
    assert len(dotted) == 12


# ---------------------------------------------------------------- measurements, slices, planes, wrap, rings


def test_measurements_point_to_the_same_atoms_after_switching() -> None:
    # Acceptance: refs { index, image } made with the repeat name the same
    # atoms (same positions, same values) with the matrix, and every drawn
    # atom's ref resolves to where it is drawn.
    structure = _payload(fcc111("Pt", size=(2, 2, 2), vacuum=5.0), "pt")
    ref = lambda index, image: {  # noqa: E731
        "index": index,
        "image": image,
        "symbol": "Pt",
        "count": 8,
    }
    items = [
        {"kind": "distance", "atoms": [ref(0, [0, 0, 0]), ref(5, [1, 0, 0])]},
        {
            "kind": "angle",
            "atoms": [ref(1, [0, 1, 0]), ref(4, [0, 0, 0]), ref(6, [1, 1, 0])],
        },
    ]
    setup = f"measureState.items = {json.dumps(items)}"
    check = (
        "(() => { const sc = buildScene(structure, { colour: () => '#000' }, null);"
        " return { marks: sc.marks, resolved: sc.atoms.every((a) => norm(sub(refPosition(structure,"
        " { index: a.index, image: a.image }), a.position)) < 1e-9) }; })()"
    )
    [before, after] = _evaluate(
        (f"{setup}; viewerPrefs.repeat = [2, 2, 1]; {check}", structure),
        (
            f"{setup}; viewerPrefs.repeatMatrix = {ROOT3_60}; {check}",
            structure,
        ),
    )
    assert after["marks"] == before["marks"]
    assert before["resolved"] and after["resolved"]


def test_slices_and_planes_refer_to_the_stored_cell() -> None:
    # Decision: slice bounds and Miller indices (h k l, t) stay those of the
    # stored cell, so they mean the same with and without a matrix; the
    # matrix sets the region (planes are cut to the new cell).
    slab = fcc111("Pt", size=(1, 1, 4), vacuum=6.0)
    structure = _payload(slab, "pt")
    top = float(_fractional(slab.cell[:], slab.positions)[:, 2].max())
    sliced = f"viewerPrefs.slice = [[null, null], [null, null], [{top - 0.01}, null]]"
    plane = (
        f"viewerPrefs.planes = [{{ h: 0, k: 0, l: 1, t: {top}, show: true }}]"
    )
    [plain, transformed] = _evaluate(
        (_atoms(f"{sliced}; {plane}"), structure),
        (
            _atoms(
                f"{sliced}; {plane}; viewerPrefs.repeatMatrix = {ROOT3_60}"
            ),
            structure,
        ),
    )
    # The top layer: one atom per stored cell, three per √3 cell.
    assert len(plain["atoms"]) == 1 and len(transformed["atoms"]) == 3
    z = [a["position"][2] for a in transformed["atoms"]]
    assert np.allclose(z, slab.positions[:, 2].max())

    # The (001) plane at the top layer, cut to the new cell: its area is 3×.
    def area(polygon: dict[str, Any]) -> float:
        p = np.asarray(polygon["points"])
        return 0.5 * np.linalg.norm(
            sum(np.cross(p[k], p[(k + 1) % len(p)]) for k in range(len(p)))
        )

    [plain_plane] = plain["planes"]
    [new_plane] = transformed["planes"]
    assert area(new_plane["polygon"]) == pytest.approx(
        3 * area(plain_plane["polygon"])
    )
    assert np.allclose(
        np.asarray(new_plane["polygon"]["points"])[:, 2],
        slab.positions[:, 2].max(),
    )


def test_wrap_puts_every_atom_inside_the_new_cell() -> None:
    slab = fcc111("Pt", size=(2, 2, 2), vacuum=5.0)
    slab.positions[0] -= 1.1 * slab.cell[0]
    slab.positions[3] += 2.3 * slab.cell[1]
    structure = _payload(slab, "pt")
    [unwrapped, wrapped] = _evaluate(
        (_atoms(f"viewerPrefs.repeatMatrix = {ROOT2}"), structure),
        (
            _atoms(
                f"viewerPrefs.wrap = true; viewerPrefs.repeatMatrix = {ROOT2}"
            ),
            structure,
        ),
    )
    new_cell = np.asarray(ROOT2) @ slab.cell[:]
    for scene in (unwrapped, wrapped):
        assert len(scene["atoms"]) == 2 * len(slab)
    g = _fractional(new_cell, [a["position"] for a in wrapped["atoms"]])[:, :2]
    assert (g > -1e-6).all() and (g < 1 + 1e-6).all()
    # Without wrapping, the atoms outside the stored cell stay outside (as
    # with the repeat), carried by their lattice vector.
    g = _fractional(new_cell, [a["position"] for a in unwrapped["atoms"]])[
        :, :2
    ]
    assert ((g < -1e-6) | (g > 1)).any()


def test_rings_are_drawn_once_per_new_cell() -> None:
    structure = _payload(graphene(), "g")
    ring = (
        "{ rings: [{ size: 6, points: [[0, 0, 0], [1, 0, 0], [1, 1, 0]],"
        " centre: [0.6, 0.4, 0] }] }"
    )
    [rings] = _evaluate(
        (
            f"viewerPrefs.repeatMatrix = {ROOT3_120};"
            f" buildScene(structure, {{ colour: () => '#000' }}, null, {ring}).rings.map((r) => r.centre)",
            structure,
        )
    )
    assert len(rings) == 3
    g = _fractional(
        np.asarray(ROOT3_120) @ np.asarray(structure["cell"])
        + [[0, 0, 0], [0, 0, 0], [0, 0, 1]],
        rings,
    )
    assert (g[:, :2] >= -1e-9).all() and (g[:, :2] < 1).all()


def test_bonded_outside_and_polyhedra_follow_the_new_cell() -> None:
    structure = _payload(rutile(), "rutile")
    common = (
        "viewerPrefs.cutoffs = bondCutoffs(structure); viewerPrefs.bonds = true;"
        " viewerPrefs.polyhedra = true; viewerPrefs.bondedOutside = 'ligands'"
    )
    expr = (
        "(() => {{ const sc = {scene};"
        " return {{ shown: sc.visibleAtoms, extra: sc.extraAtoms, polyhedra: sc.polyhedra.length,"
        " keys: sc.atoms.map((a) => a.index + '|' + a.image) }}; }})()"
    )
    [scene] = _evaluate(
        (
            expr.format(
                scene=_scene(f"{common}; viewerPrefs.repeatMatrix = {ROOT2}")
            ),
            structure,
        )
    )
    # Two copies of 2 Ti and 4 O; a polyhedron per Ti copy; no atom twice.
    assert scene["shown"] == 12
    assert scene["polyhedra"] == 4
    assert scene["extra"] > 0
    assert len(set(scene["keys"])) == len(scene["keys"])


# ------------------------------------------------- outline of every copy


def _segments(edges: list[Any]) -> set[tuple[Any, ...]]:
    """Edges as order-free sets of rounded endpoints."""
    return {
        tuple(sorted(tuple(round(x, 6) for x in p) for p in edge))
        for edge in edges
    }


def _every_copy(repeat: str, matrix: Any, on: bool, cell: bool = True) -> str:
    return _drawn(
        f"viewerPrefs.repeat = {repeat}; viewerPrefs.repeatMatrix = {json.dumps(matrix)};"
        f" viewerPrefs.storedCellOutline = false; viewerPrefs.cell = {json.dumps(cell)};"
        f" viewerPrefs.repeatCellOutline = {json.dumps(on)}",
        "null",
    )


def test_normalize_repeat_cell_outline() -> None:
    results = _evaluate(
        ("defaultPrefs().repeatCellOutline", {}),
        ("normalizePrefs({}).repeatCellOutline", {}),
        (
            "normalizePrefs({ version: 2, repeat: [2, 2] }).repeatCellOutline",
            {},
        ),
        ("normalizePrefs({ repeatCellOutline: true }).repeatCellOutline", {}),
        ("normalizePrefs({ repeatCellOutline: 'yes' }).repeatCellOutline", {}),
    )
    assert results == [False, False, False, True, False]


def test_outline_of_every_copy_of_the_repeat() -> None:
    structure = _shifted_rutile()
    off, on, no_cell, single = _evaluate(
        (_every_copy("[2, 2, 1]", None, False), structure),
        (_every_copy("[2, 2, 1]", None, True), structure),
        (_every_copy("[2, 2, 1]", None, True, cell=False), structure),
        (_every_copy("[1, 1, 1]", None, True), structure),
    )
    # Default off: the stored cell once.
    assert len(off["cell"]) == 12
    # 4 cells: 12 edges along a, 12 along b, 9 along c; shared ones once.
    assert len(on["cell"]) == 33
    assert len(_segments(on["cell"])) == 33
    assert _segments(off["cell"]) <= _segments(on["cell"])
    assert on["stored"] == []
    # Everything else is the same scene; the outline is drawn in its style.
    assert on["scene"] == off["scene"]
    lines = [p for p in json.loads(on["list"]) if p["kind"] == "line"]
    assert (
        len(lines)
        - len([p for p in json.loads(off["list"]) if p["kind"] == "line"])
        == 33 - 12
    )
    assert on["svg"].count("<line") - off["svg"].count("<line") == 33 - 12
    assert no_cell["cell"] == [] and no_cell["stored"] == []
    assert len(single["cell"]) == 12


def test_outline_of_every_copy_frames_the_view() -> None:
    # One atom at the origin of a 10 Å cell, repeated 3 times along a: the
    # atoms reach x = 20 Å, the copies' outlines x = 30 Å, and fitting the
    # view takes them in.
    def fit(on: bool) -> str:
        return (
            "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];"
            " viewerPrefs.repeat = [3, 1, 1]; viewerPrefs.repeatMatrix = null;"
            f" viewerPrefs.cell = true; viewerPrefs.repeatCellOutline = {json.dumps(on)};"
            f" const sc = buildScene(structure, {OVERLAY}, null);"
            " return fitView(sc, 400, 400); })()"
        )

    structure = _payload(Atoms("H", cell=[10, 10, 10], pbc=True), "h")
    off, on = _evaluate((fit(False), structure), (fit(True), structure))
    assert on["scale"] < off["scale"]


def test_outline_of_every_copy_with_a_matrix() -> None:
    structure = _shifted_rutile()
    diagonal, off = _evaluate(
        (
            _every_copy("[1, 1, 1]", [[2, 0, 0], [0, 2, 0], [0, 0, 1]], True),
            structure,
        ),
        (
            _every_copy("[1, 1, 1]", [[2, 0, 0], [0, 2, 0], [0, 0, 1]], False),
            structure,
        ),
    )
    # The new cell's outline stays; the 4 stored cells inside it add their
    # inner edges (33 less the 20 on the new cell's edges), dotted.
    assert len(diagonal["cell"]) == 12 and off["stored"] == []
    assert len(diagonal["stored"]) == 13
    assert len(_segments(diagonal["stored"])) == 13
    assert not _segments(diagonal["stored"]) & _segments(diagonal["cell"])
    lines = [p for p in json.loads(diagonal["list"]) if p["kind"] == "line"]
    assert len([p for p in lines if p.get("dash") and p["width"] == 0.5]) == 13


def _grid_problems(
    structure: dict[str, Any], matrix: Any, edges: Any
) -> list[str]:
    """What is wrong with `edges` (Cartesian) as the stored cells' grid inside
    the cell of `matrix`: pieces outside it, pieces on its edges, and points
    of the stored lattice lines inside it (brute force) that no piece covers.
    """
    cell = np.asarray(structure["cell"], dtype=float)
    to_lattice = np.linalg.pinv(cell)  # c may be zero (graphene)
    to_shown = np.linalg.inv(np.asarray(matrix, dtype=float))
    axes = [bool(np.linalg.norm(v) > 1e-8) for v in cell]
    segments = [np.asarray(e, dtype=float) @ to_lattice for e in edges]
    problems = []
    eps = 1e-6

    def on_cell_edge(f: np.ndarray, g: np.ndarray) -> bool:
        fixed = [
            k
            for k in range(3)
            if abs(f[k] - g[k]) < eps and min(abs(f[k]), abs(f[k] - 1)) < eps
        ]
        return len(fixed) >= 2

    for p, q in segments:
        f, g = p @ to_shown, q @ to_shown
        if (np.minimum(f, g) < -eps).any() or (
            np.maximum(f, g) > 1 + eps
        ).any():
            problems.append(f"outside: {f} {g}")
        if on_cell_edge(f, g):
            problems.append(f"on a cell edge: {f} {g}")

    def covered(x: np.ndarray) -> bool:
        for p, q in segments:
            d, v = q - p, x - p
            if (
                np.linalg.norm(np.cross(v, d)) < eps
                and -eps <= v @ d <= d @ d + eps
            ):
                return True
        return False

    real = [k for k in range(3) if axes[k]]
    span = range(-4, 5)
    for k in real:
        others = [j for j in real if j != k]
        for offset in np.ndindex(*[len(span)] * len(others)):
            for t in np.arange(-4, 5, 0.125):
                x = np.zeros(3)
                x[k] = t
                for j, o in zip(others, offset, strict=True):
                    x[j] = span[o]
                f = x @ to_shown
                inside = (f > -eps).all() and (f < 1 + eps).all()
                if inside and not on_cell_edge(f, f) and not covered(x):
                    problems.append(f"not covered: {x}")
    return problems


@pytest.mark.parametrize(
    ("name", "matrix", "count"),
    [
        # (√3×√3)R30° of graphene (c zero: flat), of a Pt(111) slab (γ = 60°),
        # c(2×2) of rutile, and the same matrix skewed on graphene.
        ("graphene", ROOT3_120, 7),
        ("slab", ROOT3_60, 16),
        ("rutile", ROOT2, 9),
        ("graphene", ROOT2, 4),
    ],
)
def test_stored_grid_is_clipped_to_the_new_cell(
    name: str, matrix: Any, count: int
) -> None:
    structure = {
        "graphene": lambda: _payload(graphene(), "g"),
        "slab": lambda: _payload(
            fcc111("Pt", size=(1, 1, 3), vacuum=5.0), "s"
        ),
        "rutile": lambda: _payload(rutile(), "r"),
    }[name]()
    [scene] = _evaluate((_every_copy("[1, 1, 1]", matrix, True), structure))
    assert scene["cell"] and scene["stored"]
    assert len(_segments(scene["stored"])) == len(scene["stored"])
    assert _grid_problems(structure, matrix, scene["stored"]) == []
    assert len(scene["stored"]) == count
