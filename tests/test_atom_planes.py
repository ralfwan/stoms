"""Planes through atoms, plane angles and distances to a plane (viewer.js, run
in Node; and the Python API): the fit, clipping and patches, measurements,
settings old and new, and Python's add_plane and measurements."""

import json
import shutil
import subprocess
from typing import Any

import numpy as np
import pytest
from ase import Atoms
from ase.build import bulk, fcc100, molecule
from test_bond_search import _payload
from test_web_viewer import VIEWER, _evaluate

from stoms.viewer import view
from stoms.viewer.base import check_measurements, read_settings

THEME = (
    "{ text: '#000000', halo: '#ffffff', cell: '#888888', accent: '#ff0000' }"
)
OVERLAY = "{ colour: (i, s) => elementColor(s), value: (i) => String(i) }"

# planePolygon before planes through atoms (issue 06): Miller planes must
# come out of the generalised function exactly as they did.
PLANE_POLYGON_BEFORE = """function planePolygonBefore(cell, plane, box) {
  const g = (f) => plane.h * f[0] + plane.k * f[1] + plane.l * f[2];
  const rows = Array.isArray(box[0]) ? box : diagonalMatrix(box);
  const corners = [];
  for (const i of [0, 1]) for (const j of [0, 1]) for (const k of [0, 1]) {
    corners.push([0, 1, 2].map((x) => i * rows[0][x] + j * rows[1][x] + k * rows[2][x]));
  }
  const found = [];
  const pushUnique = (f) => { if (!found.some((q) => Math.abs(q[0] - f[0]) + Math.abs(q[1] - f[1]) + Math.abs(q[2] - f[2]) < 1e-6)) found.push(f); };
  for (let m = 0; m < 8; m++) for (let n = m + 1; n < 8; n++) {
    const p = corners[m], q = corners[n];
    if (![1, 2, 4].includes(m ^ n)) continue;
    const gp = g(p) - plane.t, gq = g(q) - plane.t;
    if (Math.abs(gp) < 1e-9) pushUnique(p);
    if (Math.abs(gq) < 1e-9) pushUnique(q);
    if (gp * gq < 0) pushUnique(add(p, mul(sub(q, p), gp / (gp - gq))));
  }
  if (found.length < 3) return null;
  const points = found.map((f) => add(add(mul(cell[0], f[0]), mul(cell[1], f[1])), mul(cell[2], f[2])));
  const normal = unit(planeNormal(cell, plane));
  const centre = mul(points.reduce(add, [0, 0, 0]), 1 / points.length);
  const u = unit(sub(points[0], centre)), v = cross(normal, u);
  const angle = (p) => Math.atan2(dot(sub(p, centre), v), dot(sub(p, centre), u));
  points.sort((p, q) => angle(p) - angle(q));
  return { points, normal, centre };
}"""


def slab() -> Atoms:
    """Cu(100), 2×2×3, flat layers at z = 6, 7.805 and 9.61 Å."""
    return fcc100("Cu", (2, 2, 3), vacuum=6.0)


def top_atoms(atoms: Atoms, count: int = 3) -> list[int]:
    z = atoms.positions[:, 2]
    return [int(i) for i in np.flatnonzero(z > z.max() - 0.1)[:count]]


def refs(atoms: Atoms, indices: list[int]) -> list[dict[str, Any]]:
    symbols = atoms.get_chemical_symbols()
    return [
        {
            "index": i,
            "image": [0, 0, 0],
            "symbol": symbols[i],
            "count": len(atoms),
        }
        for i in indices
    ]


def _scene(settings: str) -> str:
    return (
        "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]; sharedView.scale = 20;"
        f" {settings};"
        f" const sc = buildScene(structure, {OVERLAY}, null);"
        " return { planes: sc.planes.map((p) => ({ colour: p.colour, ...p.polygon })), marks: sc.marks }; })()"
    )


# ---------------------------------------------------------------- geometry


@pytest.mark.parametrize(
    ("plane", "box"),
    [
        ({"h": 0, "k": 0, "l": 1, "t": 0.5}, [1, 1, 1]),
        ({"h": 1, "k": 1, "l": 1, "t": 1}, [2, 2, 1]),
        ({"h": 1, "k": 0, "l": 0, "t": 0.25}, [3, 1, 2]),
        (
            {"h": 1, "k": -1, "l": 2, "t": 0.7},
            [[2, 1, 0], [-1, 1, 0], [0, 0, 1]],
        ),
        ({"h": 0, "k": 0, "l": 1, "t": 0}, [1, 1, 1]),
        ({"h": 1, "k": 1, "l": 0, "t": 5}, [1, 1, 1]),  # misses the box
    ],
)
def test_miller_planes_are_cut_exactly_as_before(
    plane: dict[str, Any], box: Any
) -> None:
    structure = _payload(bulk("Cu", "fcc", a=3.6, orthorhombic=True), "c")
    args = f"structure.cell, {json.dumps(plane)}, {json.dumps(box)}"
    [now, before] = _evaluate(
        (f"JSON.stringify(planePolygon({args}))", structure),
        (
            f"(() => {{ {PLANE_POLYGON_BEFORE}; return JSON.stringify(planePolygonBefore({args})); }})()",
            structure,
        ),
    )
    assert now == before


def test_plane_through_surface_atoms_is_parallel_to_001() -> None:
    """Acceptance: the plane through three surface atoms of a flat slab is
    (001): plane angle 0°, and distances to it are the Info tab's heights
    less the surface height."""
    atoms = slab()
    plane = {"atoms": refs(atoms, top_atoms(atoms))}
    everyone = refs(atoms, list(range(len(atoms))))
    angle, fit, heights, distances = _evaluate(
        (
            "measureValue(structure, { kind: 'plane-angle', atoms: [], planes: ["
            f"{json.dumps(plane)}, {{ h: 0, k: 0, l: 1, t: 0.3 }}] }})",
            _payload(atoms, "slab"),
        ),
        (
            f"atomPlaneFit(structure, {json.dumps(plane['atoms'])})",
            _payload(atoms, "slab"),
        ),
        ("heights(structure)", _payload(atoms, "slab")),
        (
            f"{json.dumps(everyone)}.map((r) => measureValue(structure, "
            f"{{ kind: 'plane-distance', atoms: [r], planes: [{json.dumps(plane)}] }}).value)",
            _payload(atoms, "slab"),
        ),
    )
    assert angle["value"] == pytest.approx(0, abs=1e-6)
    assert angle["text"] == "0.0°"
    assert fit["normal"] == pytest.approx([0, 0, 1])
    assert fit["rms"] == pytest.approx(0, abs=1e-9)
    surface = max(heights)
    assert distances == pytest.approx([h - surface for h in heights])
    assert min(distances) == pytest.approx(-3.61)


def test_angle_between_100_and_110_of_a_cubic_cell_is_45_degrees() -> None:
    cubic = _payload(bulk("Cu", cubic=True), "cubic")
    [value, same] = _evaluate(
        (
            "measureValue(structure, { kind: 'plane-angle', atoms: [], planes: ["
            "{ h: 1, k: 0, l: 0, t: 0 }, { h: 1, k: 1, l: 0, t: 0.5 }] })",
            cubic,
        ),
        (
            "measureValue(structure, { kind: 'plane-angle', atoms: [], planes: ["
            "{ h: 1, k: 0, l: 0, t: 0 }, { h: -2, k: 0, l: 0, t: 1 }] })",
            cubic,
        ),
    )
    assert value["value"] == pytest.approx(45)
    assert value["text"] == "45.0°"
    assert same["value"] == pytest.approx(0, abs=1e-6)  # unoriented planes


def test_more_atoms_give_the_least_squares_plane() -> None:
    atoms = Atoms(
        "C5",
        positions=[
            [0, 0, 0],
            [3, 0, 0],
            [0, 3, 0],
            [3, 3, 0.4],
            [1.5, 1.5, 0],
        ],
        cell=[10, 10, 10],
        pbc=True,
    )
    [fit] = _evaluate(
        (
            f"atomPlaneFit(structure, {json.dumps(refs(atoms, list(range(5))))})",
            _payload(atoms, "c5"),
        )
    )
    positions = atoms.positions
    centred = positions - positions.mean(axis=0)
    normal = np.linalg.svd(centred)[2][-1]
    deviations = centred @ normal
    assert abs(np.dot(fit["normal"], normal)) == pytest.approx(1)
    assert fit["normal"][2] > 0  # up, like the surface normal
    assert fit["rms"] == pytest.approx(np.sqrt(np.mean(deviations**2)))
    assert fit["max"] == pytest.approx(np.abs(deviations).max())
    assert fit["point"] == pytest.approx(positions.mean(axis=0))


def test_atoms_on_a_line_give_no_plane() -> None:
    atoms = Atoms("C3", positions=[[0, 0, 0], [1, 1, 1], [2, 2, 2]])
    r = json.dumps(refs(atoms, [0, 1, 2]))
    fit, polygon = _evaluate(
        (f"atomPlaneFit(structure, {r})", _payload(atoms, "line")),
        (
            f"atomPlanePolygon(structure, {{ atoms: {r} }}, [1, 1, 1])",
            _payload(atoms, "line"),
        ),
    )
    assert fit is None and polygon is None


# ---------------------------------------------------------------- drawing


def _inside(cell: Any, box: Any, points: Any) -> bool:
    frac = np.asarray(points) @ np.linalg.inv(np.asarray(cell))
    rows = np.asarray(box) if np.ndim(box) == 2 else np.diag(box)
    coords = frac @ np.linalg.inv(rows)
    return bool(np.all(coords > -1e-6) and np.all(coords < 1 + 1e-6))


@pytest.mark.parametrize(
    "box", [[1, 1, 1], [2, 3, 1], [[1, 1, 0], [-1, 1, 0], [0, 0, 1]]]
)
def test_atom_planes_are_cut_to_the_shown_cell(box: Any) -> None:
    atoms = slab()
    plane = {
        "atoms": refs(atoms, top_atoms(atoms)),
        "show": True,
        "colour": "#123456",
    }
    repeat = (
        f"viewerPrefs.repeatMatrix = {json.dumps(box)}"
        if np.ndim(box) == 2
        else f"viewerPrefs.repeat = {json.dumps(box)}"
    )
    [scene] = _evaluate(
        (
            _scene(f"viewerPrefs.planes = [{json.dumps(plane)}]; {repeat}"),
            _payload(atoms, "slab"),
        )
    )
    [drawn] = scene["planes"]
    assert drawn["colour"] == "#123456" and drawn["patch"] is False
    points = np.asarray(drawn["points"])
    assert points[:, 2] == pytest.approx(9.61)
    assert _inside(atoms.cell[:], box, points)
    # The whole cross-section: its area is that of the shown a-b face.
    rows = np.asarray(box) if np.ndim(box) == 2 else np.diag(box)
    shown = rows @ atoms.cell[:]
    x, y = points[:, 0], points[:, 1]
    area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    assert area == pytest.approx(np.linalg.norm(np.cross(shown[0], shown[1])))


def test_patch_option_and_molecules_draw_a_patch_around_the_atoms() -> None:
    atoms = slab()
    picked = top_atoms(atoms)
    plane = {"atoms": refs(atoms, picked), "show": True, "patch": True}
    water = molecule("H2O")
    flat = {"atoms": refs(water, [0, 1, 2]), "show": True}
    patch, free = _evaluate(
        (
            _scene(f"viewerPrefs.planes = [{json.dumps(plane)}]"),
            _payload(atoms, "slab"),
        ),
        (
            _scene(f"viewerPrefs.planes = [{json.dumps(flat)}]"),
            _payload(water, "w"),
        ),
    )
    [drawn] = patch["planes"]
    assert drawn["patch"] is True and len(drawn["points"]) == 3
    corners = np.asarray(drawn["points"])
    assert corners[:, 2] == pytest.approx(9.61)
    # Each corner lies 1 Å (PATCH_MARGIN) beyond an atom.
    for corner in corners:
        gaps = np.linalg.norm(atoms.positions[picked] - corner, axis=1)
        assert gaps.min() == pytest.approx(1.0)
    # Without a cell there is nothing to cut: a patch.
    [around] = free["planes"]
    assert around["patch"] is True and len(around["points"]) == 3


def test_atom_planes_follow_frames_and_skip_other_atoms() -> None:
    atoms = slab()
    plane = {"atoms": refs(atoms, top_atoms(atoms)), "show": True}
    measure = {
        "kind": "plane-distance",
        "atoms": refs(atoms, [0]),
        "planes": [{"atoms": plane["atoms"]}],
    }
    raised = atoms.copy()
    raised.positions[:, 2] += 1.5
    other = slab()[:-1]  # one atom fewer: refs name other atoms
    script = _scene(
        f"viewerPrefs.planes = [{json.dumps(plane)}]; "
        f"measureState.items = [{json.dumps(measure)}]"
    )
    first, moved, missing = _evaluate(
        (script, _payload(atoms, "a")),
        (script, _payload(raised, "b")),
        (script, _payload(other, "c")),
    )
    assert np.asarray(first["planes"][0]["points"])[:, 2] == pytest.approx(
        9.61
    )
    assert np.asarray(moved["planes"][0]["points"])[:, 2] == pytest.approx(
        11.11
    )
    # The distance mark runs from the atom to its foot on the plane.
    [mark] = moved["marks"]
    assert mark["label"] == "-3.610 Å"
    assert np.asarray(mark["points"])[:, 2] == pytest.approx([7.5, 11.11])
    assert missing["planes"] == [] and missing["marks"] == []


def test_the_display_list_draws_every_kind_of_plane() -> None:
    """Miller planes, cut atom planes and patches all become plane polygons
    of the display list (which canvas, SVG, PNG and video all draw)."""
    atoms = slab()
    planes = [
        {"atoms": refs(atoms, top_atoms(atoms)), "show": True},
        {"atoms": refs(atoms, [0, 1, 4]), "show": True, "patch": True},
        {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True},
    ]
    script = (
        "(() => { sharedView.R = [[1, 0, 0], [0, 0.8, -0.6], [0, 0.6, 0.8]]; sharedView.scale = 20;"
        f" viewerPrefs.planes = {json.dumps(planes)};"
        f" const scene = buildScene(structure, {OVERLAY}, null);"
        f" const list = displayList(scene, 400, 300, {THEME}, {{ tripod: false }});"
        " return list.filter((p) => p.kind === 'polygon' && p.fillAlpha === viewerPrefs.appearance.planeAlpha)"
        ".map((p) => p.points.length); })()"
    )
    [drawn] = _evaluate((script, _payload(atoms, "slab")))
    assert sorted(drawn) == [3, 4, 4]


# ---------------------------------------------------------------- settings


def test_old_settings_load_unchanged() -> None:
    old = [
        {"h": 1, "k": 1, "l": 1, "t": 0.5, "show": True, "colour": "#2a78d6"},
        {"h": 0, "k": 0, "l": 1, "t": 0.25, "show": False},
    ]
    [planes] = _evaluate(
        (f"normalizePrefs({{ planes: {json.dumps(old)} }}).planes", {})
    )
    assert planes == old


def test_atom_planes_are_checked_when_settings_load() -> None:
    atoms = slab()
    good = {
        "atoms": refs(atoms, [0, 1, 2]),
        "show": False,
        "patch": True,
        "colour": "#00ff00",
        "extra": 1,
    }
    bad = [
        {"atoms": refs(atoms, [0, 1])},  # too few
        {"atoms": [*refs(atoms, [0, 1]), {"index": 5}]},
        {"atoms": "0 1 2"},
    ]
    [planes] = _evaluate(
        (
            f"normalizePrefs({{ planes: {json.dumps([good, *bad])} }}).planes",
            {},
        )
    )
    assert planes == [
        {
            "atoms": good["atoms"],
            "show": False,
            "patch": True,
            "colour": "#00ff00",
        }
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_stored_atom_planes_load_as_the_script_starts() -> None:
    """normalizePrefs runs while viewer.js loads (the stored settings)."""
    atoms = slab()
    stored = json.dumps(
        {"planes": [{"atoms": refs(atoms, [0, 1, 2]), "show": True}]}
    )
    runner = (
        'const vm = require("vm"), fs = require("fs");'
        f" const context = vm.createContext({{ localStorage: {{ getItem: () => {json.dumps(stored)}, setItem() {{}} }} }});"
        " vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);"
        " process.stdout.write(JSON.stringify(vm.runInContext('viewerPrefs.planes', context)));"
    )
    result = subprocess.run(
        ["node", "-e", runner, str(VIEWER)],
        capture_output=True,
        text=True,
        check=True,
    )
    [plane] = json.loads(result.stdout)
    assert plane["atoms"][2]["index"] == 2 and plane["patch"] is False


def test_page_measurements_keep_plane_items() -> None:
    atoms = slab()
    good = [
        {
            "kind": "plane-angle",
            "atoms": [],
            "planes": [
                {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True},
                {"atoms": refs(atoms, [0, 1, 2]), "colour": "#000000"},
            ],
        },
        {
            "kind": "plane-distance",
            "atoms": refs(atoms, [3]),
            "planes": [{"h": 1, "k": 0, "l": 0}],
        },
    ]
    bad = [
        {
            "kind": "plane-angle",
            "atoms": [],
            "planes": [{"h": 0, "k": 0, "l": 1}],
        },
        {
            "kind": "plane-distance",
            "atoms": [],
            "planes": [{"h": 1, "k": 0, "l": 0}],
        },
        {
            "kind": "plane-angle",
            "atoms": [],
            "planes": [{"h": 0, "k": 0, "l": 0}] * 2,
        },
        {
            "kind": "plane-angle",
            "atoms": [],
            "planes": [{"atoms": refs(atoms, [0, 1])}] * 2,
        },
    ]
    [kept] = _evaluate((f"validMeasurements({json.dumps(good + bad)})", {}))
    assert kept == [
        {
            "kind": "plane-angle",
            "atoms": [],
            "planes": [
                {"h": 0, "k": 0, "l": 1, "t": 0.5},
                {"atoms": refs(atoms, [0, 1, 2])},
            ],
        },
        {
            "kind": "plane-distance",
            "atoms": refs(atoms, [3]),
            "planes": [{"h": 1, "k": 0, "l": 0, "t": 0}],
        },
    ]


# ---------------------------------------------------------------- Python


def test_add_plane_through_atoms() -> None:
    atoms = slab()
    viewer = view([atoms], static=True)
    viewer.add_plane(atoms=top_atoms(atoms), colour="#e34948")
    viewer.add_plane(
        atoms=[
            0,
            1,
            {"index": 4, "image": [0, 0, 1], "symbol": "Cu", "count": 12},
        ],
        patch=True,
        show=False,
    )
    viewer.add_plane(0, 0, 1)
    first, second, miller = viewer.planes
    assert first == {
        "atoms": refs(atoms, top_atoms(atoms)),
        "show": True,
        "patch": False,
        "colour": "#e34948",
    }
    assert second["patch"] is True and second["show"] is False
    assert second["atoms"][2]["image"] == [0, 0, 1]
    assert miller == {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True}
    # Through settings files and back.
    again = view([atoms], static=True, settings=viewer.get_settings())
    assert again.planes == viewer.planes


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"atoms": [0, 1]}, "3 or more different atoms"),
        ({"atoms": [0, 1, 1]}, "3 or more different atoms"),
        ({"atoms": [0, 1, 99]}, "not in the shown frame"),
        ({"atoms": [0, 1, 2], "h": 1}, "not both"),
        ({"atoms": "012"}, "list of 3 or more"),
        ({}, "Miller indices h, k, l or atoms"),
    ],
)
def test_add_plane_rejects_bad_atoms(
    kwargs: dict[str, Any], message: str
) -> None:
    viewer = view([slab()], static=True)
    with pytest.raises(ValueError, match=message):
        viewer.add_plane(**kwargs)


def test_add_plane_rejects_atoms_on_a_line() -> None:
    atoms = Atoms("C3", positions=[[0, 0, 0], [1, 1, 1], [2, 2, 2]])
    with pytest.raises(ValueError, match="on a line"):
        view([atoms], static=True).add_plane(atoms=[0, 1, 2])


def test_python_checks_plane_measurements() -> None:
    atoms = slab()
    items = [
        {
            "kind": "plane-angle",
            "planes": [
                {"h": 0, "k": 0, "l": 1, "t": 0.5},
                {"atoms": refs(atoms, [0, 1, 2])},
            ],
        },
        {
            "kind": "plane-distance",
            "atoms": refs(atoms, [3]),
            "planes": [{"h": 1, "k": 1, "l": 0}],
        },
    ]
    checked = check_measurements(items)
    assert checked[0]["atoms"] == []
    assert checked[1]["planes"] == [{"h": 1, "k": 1, "l": 0, "t": 0.0}]
    file = {
        "stoms_viewer_settings": 1,
        "settings": {},
        "measurements": checked,
    }
    assert read_settings(file)[2] == checked
    viewer = view([atoms], static=True, settings=file)
    assert viewer.get_settings()["measurements"] == checked
    for bad, message in [
        (
            {"kind": "plane-angle", "planes": [{"h": 0, "k": 0, "l": 1}]},
            "2 planes",
        ),
        (
            {"kind": "plane-distance", "planes": [{"h": 1, "k": 0, "l": 0}]},
            "not a distance",
        ),
        (
            {"kind": "plane-angle", "planes": [{"h": 0, "k": 0, "l": 0}] * 2},
            "a plane is",
        ),
        (
            {
                "kind": "plane-angle",
                "planes": [{"atoms": refs(atoms, [0, 1])}] * 2,
            },
            "3 or more",
        ),
    ]:
        with pytest.raises(ValueError, match=message):
            check_measurements([bad])


def test_widget_reports_plane_measurements() -> None:
    pytest.importorskip("anywidget")
    atoms = slab()
    plane = {"atoms": refs(atoms, [0, 1, 2])}
    viewer = view([atoms])
    # As the page reports them (with values).
    viewer._measurements = [
        {
            "kind": "plane-angle",
            "atoms": [],
            "planes": [plane, {"h": 0, "k": 0, "l": 1, "t": 0.5}],
            "value": 0.0,
        },
        {
            "kind": "plane-distance",
            "atoms": refs(atoms, [8]),
            "planes": [plane],
            "value": 3.61,
        },
    ]
    angle, distance = viewer.measurements
    assert angle["unit"] == "°" and angle["atoms"] == []
    assert angle["planes"] == [
        {"atoms": [0, 1, 2], "images": [(0, 0, 0)] * 3},
        {"h": 0, "k": 0, "l": 1, "t": 0.5},
    ]
    assert distance["unit"] == "Å" and distance["value"] == 3.61
    assert viewer.get_settings()["measurements"][1]["planes"] == [plane]
    # On a frame they do not fit, the page reports them without a value,
    # like other measurements (issue 14); they are not left out.
    viewer._measurements = [
        {"kind": "distance", "atoms": refs(atoms, [0, 8]), "value": None},
        {
            "kind": "plane-distance",
            "atoms": refs(atoms, [8]),
            "planes": [plane],
            "value": None,
        },
    ]
    assert [(m["kind"], m["value"]) for m in viewer.measurements] == [
        ("distance", None),
        ("plane-distance", None),
    ]


# ---------------------------------------------------------------- extend factor (issue 10)


def _extend_planes(atoms: Atoms, scale: Any) -> list[dict[str, Any]]:
    """A Miller plane, a cut plane through atoms and a patch; with `scale`
    on each unless it is None."""
    planes = [
        {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True},
        {"atoms": refs(atoms, top_atoms(atoms)), "show": True},
        {"atoms": refs(atoms, [0, 1, 4]), "show": True, "patch": True},
    ]
    if scale is not None:
        for plane in planes:
            plane["scale"] = scale
    return planes


@pytest.mark.parametrize(
    "repeat",
    [
        "viewerPrefs.repeat = [2, 1, 1]",
        "viewerPrefs.repeatMatrix = [[1, 1, 0], [-1, 1, 0], [0, 0, 1]]",
    ],
)
def test_extend_factor_doubles_every_kind_of_plane(repeat: str) -> None:
    """Scale 2: each corner twice as far from the polygon's centre, for a
    Miller plane, a plane through atoms cut to the shown cell and a patch."""
    atoms = slab()
    plain, doubled = _evaluate(
        *(
            (
                _scene(
                    f"viewerPrefs.planes = {json.dumps(_extend_planes(atoms, scale))}; {repeat}"
                ),
                _payload(atoms, "slab"),
            )
            for scale in (None, 2)
        )
    )
    assert len(plain["planes"]) == len(doubled["planes"]) == 3
    assert [p.get("patch") for p in doubled["planes"]] == [None, False, True]
    for before, after in zip(plain["planes"], doubled["planes"], strict=True):
        centre = np.asarray(before["centre"])
        assert after["centre"] == pytest.approx(before["centre"])
        assert after["normal"] == pytest.approx(before["normal"])
        old, new = np.asarray(before["points"]), np.asarray(after["points"])
        assert new.shape == old.shape
        assert new - centre == pytest.approx(2 * (old - centre))


def test_extend_factor_one_draws_exactly_todays_planes() -> None:
    atoms = slab()

    def script(scale: Any) -> str:
        return (
            "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]; sharedView.scale = 20;"
            f" viewerPrefs.planes = {json.dumps(_extend_planes(atoms, scale))};"
            " viewerPrefs.repeat = [2, 2, 1];"
            f" return JSON.stringify(buildScene(structure, {OVERLAY}, null).planes); }})()"
        )

    without, one = _evaluate(
        *((script(scale), _payload(atoms, "slab")) for scale in (None, 1))
    )
    assert one == without


def test_extend_factor_leaves_plane_measurements_alone() -> None:
    """Plane measurements use the plane, not the drawn polygon; a plane
    taken into a measurement does not take its scale along."""
    atoms = slab()
    measure = {
        "kind": "plane-distance",
        "atoms": refs(atoms, [0]),
        "planes": [{"atoms": refs(atoms, top_atoms(atoms))}],
    }

    def script(scale: Any) -> str:
        return (
            "(() => { sharedView.R = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]; sharedView.scale = 20;"
            f" viewerPrefs.planes = {json.dumps(_extend_planes(atoms, scale))};"
            f" measureState.items = [{json.dumps(measure)}];"
            f" const sc = buildScene(structure, {OVERLAY}, null);"
            " return { marks: sc.marks, definitions: viewerPrefs.planes.map(planeDefinition) }; })()"
        )

    plain, extended = _evaluate(
        *((script(scale), _payload(atoms, "slab")) for scale in (None, 10))
    )
    assert extended["marks"] == plain["marks"]
    assert extended["marks"][0]["label"] == "-3.610 Å"
    assert extended["definitions"] == plain["definitions"]
    assert all("scale" not in d for d in extended["definitions"])


def test_extend_factor_is_checked_when_settings_load() -> None:
    atoms = slab()
    ok = [
        {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True, "scale": 2.5},
        {"h": 1, "k": 0, "l": 0, "t": 0.5, "show": True, "scale": 1},
        {
            "atoms": refs(atoms, [0, 1, 2]),
            "show": True,
            "patch": False,
            "colour": "#00ff00",
            "scale": 10,
        },
    ]
    bad = [0.5, 0, 10.5, -2, "2", None, True, [2]]
    miller = [
        {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True, "scale": s}
        for s in bad
    ]
    through = [
        {
            "atoms": refs(atoms, [0, 1, 2]),
            "show": True,
            "patch": True,
            "colour": "#00ff00",
            "scale": s,
        }
        for s in bad
    ]
    [kept, dropped] = _evaluate(
        (f"normalizePrefs({{ planes: {json.dumps(ok)} }}).planes", {}),
        (
            f"normalizePrefs({{ planes: {json.dumps(miller + through)} }}).planes",
            {},
        ),
    )
    assert kept == ok
    assert dropped == [{"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True}] * len(
        bad
    ) + [
        {
            "atoms": refs(atoms, [0, 1, 2]),
            "show": True,
            "patch": True,
            "colour": "#00ff00",
        }
    ] * len(bad)


def test_add_plane_scale_round_trips_and_matches_the_viewer() -> None:
    atoms = slab()
    viewer = view([atoms], static=True)
    viewer.add_plane(0, 0, 1, scale=2.5)
    viewer.add_plane(atoms=top_atoms(atoms), patch=True, scale=3)
    viewer.add_plane(1, 0, 0)  # no scale: as before
    miller, through, plain = viewer.planes
    assert miller["scale"] == 2.5 and through["scale"] == 3
    assert "scale" not in plain
    again = view([atoms], static=True, settings=viewer.get_settings())
    assert again.planes == viewer.planes
    viewer.planes = [{**plain, "scale": 1}]
    assert viewer.planes[0]["scale"] == 1
    # The viewer keeps what Python writes.
    [loaded] = _evaluate(
        (
            f"normalizePrefs({{ planes: {json.dumps(again.planes)} }}).planes",
            {},
        )
    )
    assert loaded == again.planes


@pytest.mark.parametrize(
    "scale", [0.5, 0, 10.5, "2", True, None, float("nan")]
)
def test_python_rejects_bad_extend_factors(scale: Any) -> None:
    atoms = slab()
    viewer = view([atoms], static=True)
    with pytest.raises(ValueError, match="scale is a number from 1 to 10"):
        viewer.add_plane(0, 0, 1, scale=scale)
    with pytest.raises(ValueError, match="scale is a number from 1 to 10"):
        viewer.planes = [{"h": 0, "k": 0, "l": 1, "scale": scale}]
    with pytest.raises(ValueError, match="scale is a number from 1 to 10"):
        viewer.planes = [{"atoms": refs(atoms, [0, 1, 2]), "scale": scale}]
