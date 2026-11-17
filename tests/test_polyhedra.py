"""Coordination polyhedra: stoms.analysis.polyhedron and its twin in viewer.js
(polyhedronOf), which must give the same numbers."""

import json
import math
import shutil
from typing import Any

import numpy as np
import pytest
from ase import Atoms
from test_web_viewer import _evaluate

from stoms.analysis import hull_volume, polyhedron
from stoms.viewer import view

# Rutile TiO2, P4_2/mnm, at 15 K: a = 4.5937 Å, c = 2.9587 Å, O at (x, x, 0)
# with x = 0.30478. J. K. Burdett, T. Hughbanks, G. J. Miller, J. W.
# Richardson and J. V. Smith, J. Am. Chem. Soc. 109, 3639 (1987).
RUTILE_A, RUTILE_C, RUTILE_X = 4.5937, 2.9587, 0.30478


def rutile(
    a: float = RUTILE_A, c: float = RUTILE_C, x: float = RUTILE_X
) -> Atoms:
    return Atoms(
        "Ti2O4",
        scaled_positions=[
            [0, 0, 0],
            [0.5, 0.5, 0.5],
            [x, x, 0],
            [1 - x, 1 - x, 0],
            [0.5 + x, 0.5 - x, 0.5],
            [0.5 - x, 0.5 + x, 0.5],
        ],
        cell=[a, a, c],
        pbc=True,
    )


def rutile_reference(
    a: float = RUTILE_A, c: float = RUTILE_C, x: float = RUTILE_X
) -> dict[str, float]:
    """The TiO6 octahedron of rutile in closed form, independent of the code
    under test (no published table of these four numbers was found, so they
    are derived here from the published structure).

    Ti at the origin has two apical O at ±(x, x, 0) and four equatorial O at
    (±(1/2 − x), ∓(1/2 − x), ±1/2) (fractional): the apical bonds are
    perpendicular to the plane of a rectangle of equatorial O with sides
    2√2 (1/2 − x) a and c.
    """
    apical = math.sqrt(2) * x * a
    half_width = math.sqrt(2) * (0.5 - x) * a
    equatorial = math.hypot(half_width, c / 2)
    lengths = sorted([apical] * 2 + [equatorial] * 4)
    mean = sum(lengths) / 6
    volume = (2 * half_width * c) * 2 * apical / 3
    l0 = (3 * volume / 4) ** (1 / 3)
    # The equatorial O–Ti–O angles are θ and 180° − θ (two each); the 8
    # apical–equatorial angles are 90°.
    theta = 2 * math.degrees(math.atan2(c / 2, half_width))
    weights = [math.exp(1 - (v / lengths[0]) ** 6) for v in lengths]
    weighted = sum(v * w for v, w in zip(lengths, weights, strict=True)) / sum(
        weights
    )
    return {
        "apical": apical,
        "equatorial": equatorial,
        "mean": mean,
        "volume": volume,
        "distortion_index": sum(abs(v - mean) for v in lengths) / (6 * mean),
        "quadratic_elongation": sum((v / l0) ** 2 for v in lengths) / 6,
        "bond_angle_variance": 4 * (theta - 90) ** 2 / 11,
        "econ": sum(math.exp(1 - (v / weighted) ** 6) for v in lengths),
    }


def octahedron(length: float = 2.0) -> Atoms:
    vectors = [
        [1, 0, 0],
        [-1, 0, 0],
        [0, 1, 0],
        [0, -1, 0],
        [0, 0, 1],
        [0, 0, -1],
    ]
    return Atoms(
        "TiO6",
        positions=[[0, 0, 0]] + [[length * v for v in w] for w in vectors],
    )


def tetrahedron(length: float = 1.6) -> Atoms:
    vectors = np.array(
        [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]
    ) / math.sqrt(3)
    return Atoms("SiO4", positions=[[0, 0, 0], *(length * vectors)])


@pytest.mark.parametrize(
    ("atoms", "cn", "volume"),
    [
        (octahedron(2.0), 6, 4 / 3 * 2.0**3),
        (tetrahedron(1.6), 4, 8 * 1.6**3 / (9 * math.sqrt(3))),
    ],
)
def test_regular_polyhedra_are_undistorted(
    atoms: Atoms, cn: int, volume: float
) -> None:
    result = polyhedron(atoms, 0)
    assert result["cn"] == cn
    assert [ligand["symbol"] for ligand in result["ligands"]] == ["O"] * cn
    assert result["volume"] == pytest.approx(volume)
    assert result["distortion_index"] == pytest.approx(0, abs=1e-12)
    assert result["quadratic_elongation"] == pytest.approx(1)
    assert result["bond_angle_variance"] == pytest.approx(0, abs=1e-9)
    assert result["econ"] == pytest.approx(cn)


def test_rutile_octahedron_matches_the_closed_form() -> None:
    expected = rutile_reference()
    result = polyhedron(rutile(), 0)
    assert result["cn"] == 6
    # 1.9486 Å (×4) and 1.9800 Å (×2), as Burdett et al. report.
    assert result["lengths"] == pytest.approx(
        [expected["equatorial"]] * 4 + [expected["apical"]] * 2
    )
    assert expected["equatorial"] == pytest.approx(1.9486, abs=1e-4)
    assert expected["apical"] == pytest.approx(1.9800, abs=1e-4)
    for key in (
        "mean",
        "volume",
        "distortion_index",
        "quadratic_elongation",
        "bond_angle_variance",
        "econ",
    ):
        assert result[key] == pytest.approx(expected[key], rel=1e-9), key
    # Ligands come from periodic images: both Ti have the same octahedron.
    other = polyhedron(rutile(), 1)
    assert other["lengths"] == pytest.approx(result["lengths"])
    assert {tuple(lig["image"]) for lig in result["ligands"]} != {(0, 0, 0)}


def test_cutoffs_and_ligand_rule() -> None:
    atoms = rutile()
    # A cutoff between the two bond lengths keeps the four short bonds.
    short = polyhedron(atoms, 0, cutoffs={"Ti-O": 1.96})
    assert short["cn"] == 4
    assert short["volume"] is None  # flat: the four O lie in one plane
    assert short["quadratic_elongation"] is None
    assert polyhedron(atoms, 0, cutoffs={("O", "Ti"): 0})["cn"] == 0
    none = polyhedron(atoms, 0, cutoffs={"O-Ti": 0})
    assert none["mean"] is None and none["econ"] is None
    # Metals are never ligands, even with a Ti-Ti cutoff.
    assert polyhedron(atoms, 0, cutoffs={"Ti-Ti": 5.0})["cn"] == 6
    with pytest.raises(IndexError):
        polyhedron(atoms, 6)


def test_hull_volume_of_a_cube() -> None:
    corners = [[i, j, k] for i in (0, 2) for j in (0, 2) for k in (0, 2)]
    assert hull_volume(corners) == pytest.approx(8)
    assert hull_volume(corners[:3]) is None


def test_viewer_polyhedra_use_the_viewer_cutoffs() -> None:
    images = [rutile(), rutile(x=0.31)]
    viewer = view(images, static=True)
    assert viewer.polyhedron(0)["cn"] == 6
    # The setting that draws polyhedra keeps its name.
    assert isinstance(viewer.polyhedra, bool)
    assert viewer.polyhedron(0, frame=1)["lengths"] == pytest.approx(
        polyhedron(images[1], 0)["lengths"]
    )
    viewer.bond_cutoffs = {"O-Ti": 1.96}
    assert viewer.polyhedron(0)["cn"] == 4
    with pytest.raises(ValueError, match="out of range"):
        viewer.polyhedron(0, frame=5)


# ------------------------------------------------------------ JS = Python

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="needs node"
)

JS_KEYS = {
    "distortion_index": "distortion",
    "quadratic_elongation": "quadraticElongation",
    "bond_angle_variance": "angleVariance",
}


def _payload(atoms: Atoms, name: str) -> dict:
    return {
        "id": name,
        "symbols": atoms.get_chemical_symbols(),
        "positions": atoms.positions.tolist(),
        "cell": atoms.cell[:].tolist(),
        "pbc": [bool(p) for p in atoms.pbc],
    }


def _distorted() -> Atoms:
    """Rutile with a strained cell and every atom moved a little."""
    atoms = rutile(a=4.62, c=2.93, x=0.302)
    atoms.positions += np.random.default_rng(7).normal(0, 0.04, (6, 3))
    return atoms


def _thin() -> Atoms:
    """A 1.5 Å cubic cell with a 3 Å cutoff: ligands up to 1.5 cells away
    (32 O images; the earlier search of ±1 cells found 20)."""
    return Atoms(
        "TiO",
        scaled_positions=[[0, 0, 0], [0.5, 0.5, 0.5]],
        cell=[1.5, 1.5, 1.5],
        pbc=True,
    )


def _unwrapped() -> Atoms:
    """Rutile with one O two cells away from its place along a."""
    atoms = rutile()
    atoms.positions[2] += 2 * atoms.cell[0]
    return atoms


@needs_node
@pytest.mark.parametrize(
    ("name", "atoms", "index", "cutoffs"),
    [
        ("rutile", rutile(), 0, {}),
        ("distorted", _distorted(), 1, {}),
        ("tetrahedron", tetrahedron(), 0, {}),
        ("cut", _distorted(), 0, {"O-Ti": 1.97}),
        ("five", Atoms("TiO5", positions=octahedron().positions[:6]), 0, {}),
        ("thin", _thin(), 0, {"O-Ti": 3.0}),
        ("unwrapped", _unwrapped(), 0, {}),
        ("minimum", _distorted(), 0, {"O-Ti": (1.97, 2.3)}),
    ],
)
def test_viewer_js_gives_the_python_numbers(
    name: str, atoms: Atoms, index: int, cutoffs: dict[str, Any]
) -> None:
    expected = polyhedron(atoms, index, cutoffs=cutoffs)
    if name == "thin":
        assert expected["cn"] == 32
    if name == "unwrapped":
        assert expected["cn"] == 6
    # The viewer keeps minimums apart (viewerPrefs.bondMinimums).
    longest = {
        k: v[1] if isinstance(v, tuple) else v for k, v in cutoffs.items()
    }
    shortest = {k: v[0] for k, v in cutoffs.items() if isinstance(v, tuple)}
    [js] = _evaluate(
        (
            f"(Object.assign(viewerPrefs.cutoffs, {json.dumps(longest)}),"
            f" Object.assign(viewerPrefs.bondMinimums, {json.dumps(shortest)}),"
            f" polyhedronOf(structure, {index}))",
            _payload(atoms, name),
        )
    )
    assert js["cn"] == expected["cn"]
    assert [(lig["index"], lig["image"]) for lig in js["ligands"]] == [
        (lig["index"], lig["image"]) for lig in expected["ligands"]
    ]
    assert js["lengths"] == pytest.approx(expected["lengths"], abs=1e-12)
    for key in ("mean", "volume", "econ", *JS_KEYS):
        value = js[JS_KEYS.get(key, key)]
        if expected[key] is None:
            assert value is None, key
        else:
            assert value == pytest.approx(expected[key], rel=1e-9), key


@needs_node
def test_polyhedra_csv() -> None:
    [csv] = _evaluate(
        (
            "polyhedraCsv([{ structure: 'a', polyhedron: polyhedronOf(structure, 0) }])",
            _payload(rutile(), "csv"),
        )
    )
    header, row = csv.strip().split("\n")
    assert header.startswith("structure,centre,cn,ligands,lengths,mean,volume")
    assert row.startswith("a,Ti0,6,")
