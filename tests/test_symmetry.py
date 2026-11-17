"""stoms.analysis.symmetry, its server endpoint and the notebook embedding;
with and without spglib (the optional ``symmetry`` extra)."""

import json
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest
from ase import Atoms
from ase.build import bulk, fcc111, molecule
from test_polyhedra import rutile
from web_access_helpers import TEST_TOKEN

from stoms.analysis import symmetry, symmetry_available
from stoms.analysis.symmetry import (
    DEFAULT_TOLERANCE,
    INSTALL_HINT,
    crystal_system,
    symmetry_payload,
)

# Tests that need spglib; the others run without it (as without the extra).
needs_spglib = pytest.mark.skipif(
    not symmetry_available(), reason="needs spglib (the symmetry extra)"
)


@pytest.fixture
def no_spglib(monkeypatch: pytest.MonkeyPatch) -> None:
    """An environment without spglib: importing it fails."""
    monkeypatch.setitem(sys.modules, "spglib", None)


def relaxed_rutile() -> Atoms:
    """Rutile after a "relaxation" that left noise of up to 3 mÅ."""
    atoms = rutile()
    noise = np.random.default_rng(7).uniform(-0.003, 0.003, (len(atoms), 3))
    atoms.positions += noise
    return atoms


# ------------------------------------------------------------------ analysis


@needs_spglib
def test_silicon_is_fd_3m() -> None:
    result = symmetry(bulk("Si"))
    assert result.applicable and result.reason is None
    assert (result.international, result.number) == ("Fd-3m", 227)
    assert result.symbol == "Fd-3m (227)"
    assert result.crystal_system == "cubic"
    assert result.tolerance == DEFAULT_TOLERANCE
    assert result.wyckoffs == ("a", "a") or result.wyckoffs == ("b", "b")
    assert result.site_symmetries == ("-43m", "-43m")
    assert result.equivalent_atoms == (0, 0)


@needs_spglib
def test_rutile_is_p4_2_mnm_with_its_wyckoff_sites() -> None:
    result = symmetry(rutile())
    assert (result.international, result.number) == ("P4_2/mnm", 136)
    assert result.crystal_system == "tetragonal"
    assert result.point_group == "4/mmm"
    # Ti on 2a (m.mm), O on 4f (m.2m); the two Ti and the four O are
    # equivalent.
    assert result.wyckoffs == ("a", "a", "f", "f", "f", "f")
    assert result.site_symmetries[0] == "m.mm"
    assert set(result.site_symmetries[2:]) == {"m.2m"}
    assert result.equivalent_atoms == (0, 0, 2, 2, 2, 2)


@needs_spglib
def test_slightly_distorted_structure_keeps_its_group_at_the_default() -> None:
    atoms = relaxed_rutile()
    assert symmetry(atoms).number == 136
    # A strict tolerance sees the noise.
    assert symmetry(atoms, tolerance=1e-4).number < 136


@needs_spglib
@pytest.mark.parametrize(
    ("atoms", "reason"),
    [
        (molecule("H2O"), "not periodic along abc"),
        (fcc111("Pt", (2, 2, 3), vacuum=5), "not periodic along c"),
        (
            Atoms("H", cell=[[1, 0, 0], [0, 1, 0], [0, 0, 0]], pbc=True),
            "volume",
        ),
    ],
)
@needs_spglib
def test_structures_without_a_3d_cell_are_not_applicable(
    atoms: Atoms, reason: str
) -> None:
    result = symmetry(atoms)
    assert not result.applicable
    assert reason in result.reason
    assert result.number is None and result.symbol is None
    assert result.wyckoffs == ()


@needs_spglib
def test_overlapping_atoms_report_spglib_failing() -> None:
    atoms = Atoms("H2", positions=[[0, 0, 0], [0, 0, 0]], cell=[3, 3, 3])
    atoms.pbc = True
    result = symmetry(atoms)
    assert result.applicable and result.number is None
    assert result.reason.startswith("spglib found no space group")


@needs_spglib
def test_to_dict_is_plain_json() -> None:
    data = symmetry(rutile()).to_dict()
    assert json.loads(json.dumps(data)) == data
    assert data["equivalent_atoms"] == [0, 0, 2, 2, 2, 2]


@needs_spglib
@pytest.mark.parametrize("tolerance", [0, -0.1, 2.0, float("nan"), True])
def test_unusable_tolerances_are_refused(tolerance: Any) -> None:
    with pytest.raises((ValueError, TypeError)):
        symmetry(bulk("Si"), tolerance=tolerance)


def test_crystal_systems_follow_the_space_group_number() -> None:
    assert [crystal_system(n) for n in (1, 3, 16, 75, 143, 168, 195)] == [
        "triclinic",
        "monoclinic",
        "orthorhombic",
        "tetragonal",
        "trigonal",
        "hexagonal",
        "cubic",
    ]


def test_without_spglib_symmetry_names_the_extra(no_spglib: None) -> None:
    assert not symmetry_available()
    with pytest.raises(ImportError, match=r"stoms\[symmetry\]"):
        symmetry(bulk("Si"))
    assert symmetry_payload(bulk("Si")) == {
        "available": False,
        "install": INSTALL_HINT,
    }
    assert 'pip install "stoms[symmetry]"' in INSTALL_HINT


# ------------------------------------------------------------------ notebook


@needs_spglib
def test_notebook_frames_embed_their_symmetry(tmp_path: Path) -> None:
    from stoms.viewer import view

    viewer = view([rutile(), bulk("Si"), molecule("H2O")], static=True)
    frames = viewer._data(bridge=False)["frames"]
    assert frames[0]["symmetry"]["available"] is True
    assert frames[0]["symmetry"]["number"] == 136
    assert frames[1]["symmetry"]["international"] == "Fd-3m"
    assert frames[2]["symmetry"]["applicable"] is False
    # Another tolerance from Python: embedded again at that tolerance.
    viewer.symmetry_tolerance = 1e-4
    frames = viewer._data(bridge=False)["frames"]
    assert frames[0]["symmetry"]["tolerance"] == 1e-4
    html = viewer.to_html()
    assert "P4_2/mnm" in html


@needs_spglib
def test_frames_past_the_atom_budget_are_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from stoms.viewer import frames as frames_module
    from stoms.viewer.frames import embed_symmetry, frame_payload

    monkeypatch.setattr(frames_module, "MAX_SYMMETRY_ATOMS", 12)
    images = [rutile(), rutile(), rutile(), molecule("H2O")]
    payloads = [frame_payload(atoms, i) for i, atoms in enumerate(images)]
    embed_symmetry(payloads, images, 0.01)
    assert payloads[0]["symmetry"]["number"] == 136
    assert "deferred" not in payloads[0]["symmetry"]
    assert payloads[1]["symmetry"]["number"] == 136
    assert payloads[2]["symmetry"] == {
        "available": True,
        "deferred": True,
        "tolerance": 0.01,
    }
    # Frames without a 3D cell cost nothing: still embedded.
    assert payloads[3]["symmetry"]["applicable"] is False


def test_notebook_without_spglib_embeds_no_symmetry(no_spglib: None) -> None:
    from stoms.viewer import view

    viewer = view(rutile(), static=True)
    frames = viewer._data(bridge=False)["frames"]
    assert "symmetry" not in frames[0]
    with pytest.raises(ImportError, match=r"stoms\[symmetry\]"):
        viewer.colour_by("equivalent")


@needs_spglib
def test_python_answers_the_pages_symmetry_requests() -> None:
    from stoms.viewer import view

    viewer = view([molecule("H2O"), rutile()], static=True)
    answer = viewer._answer_symmetry(
        "structures/frame-1/symmetry?tolerance=0.05"
    )
    assert answer["number"] == 136 and answer["tolerance"] == 0.05
    assert viewer._answer_symmetry("structures/frame-0/modes") is None
    with pytest.raises(LookupError):
        viewer._answer_symmetry("structures/frame-7/symmetry")
    with pytest.raises(ValueError):
        viewer._answer_symmetry("structures/frame-1/symmetry?tolerance=5")


@needs_spglib
def test_tolerance_and_equivalent_site_colours_from_python() -> None:
    from stoms.viewer import view

    viewer = view(rutile(), static=True)
    assert viewer.symmetry_tolerance == DEFAULT_TOLERANCE
    viewer.symmetry_tolerance = 0.1
    assert viewer.settings["symmetry"] == {"tolerance": 0.1}
    with pytest.raises(ValueError):
        viewer.symmetry_tolerance = 0
    viewer.colour_by("equivalent")
    assert viewer.settings["colour"] == "property"
    assert viewer.settings["property"]["choice"] == {
        "source": "derived",
        "name": "equivalent",
    }
    assert viewer.settings["property"]["kind"] == "categories"


# ------------------------------------------------------------------ server


@pytest.fixture
def served(tmp_path: Path) -> Iterator[dict[str, Any]]:
    from stoms.atomsledger import AtomsLedger, Provenance, StructureSourceSpec
    from stoms.web import AccessOptions, create_server

    ledger = AtomsLedger(tmp_path / "symmetry.ledger")
    source = StructureSourceSpec(kind="generated", name="t")
    ids = [
        cast(
            str,
            ledger.add_structure(
                atoms, source, Provenance(created_by="t", purpose="symmetry")
            ),
        )
        for atoms in (rutile(), molecule("H2O"))
    ]
    server = create_server(
        ledger,
        "symmetry.ledger",
        port=0,
        access=AccessOptions(token=TEST_TOKEN),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"base": f"http://127.0.0.1:{server.server_address[1]}", "ids": ids}
    server.shutdown()
    server.server_close()


def _get(url: str) -> Any:
    request = Request(url, headers={"Authorization": f"token {TEST_TOKEN}"})
    with urlopen(request) as response:
        return json.load(response)


@needs_spglib
def test_server_computes_symmetry_per_structure(
    served: dict[str, Any],
) -> None:
    base, (crystal, water) = served["base"], served["ids"]
    assert _get(f"{base}/api/structures/{crystal}")["symmetry_available"]
    data = _get(f"{base}/api/structures/{crystal}/symmetry")
    assert data["available"] and data["number"] == 136
    assert data["tolerance"] == DEFAULT_TOLERANCE
    assert data["wyckoffs"] == ["a", "a", "f", "f", "f", "f"]
    loose = _get(f"{base}/api/structures/{crystal}/symmetry?tolerance=0.2")
    assert loose["tolerance"] == 0.2
    molecule_data = _get(f"{base}/api/structures/{water}/symmetry")
    assert molecule_data["available"] and not molecule_data["applicable"]


@needs_spglib
@pytest.mark.parametrize("tolerance", ["abc", "0", "3", "nan"])
@needs_spglib
def test_server_refuses_unusable_tolerances(
    served: dict[str, Any], tolerance: str
) -> None:
    crystal = served["ids"][0]
    with pytest.raises(HTTPError) as error:
        _get(
            f"{served['base']}/api/structures/{crystal}/symmetry"
            f"?tolerance={tolerance}"
        )
    assert error.value.code == 400


def test_server_without_spglib_says_so(
    served: dict[str, Any], no_spglib: None
) -> None:
    base, crystal = served["base"], served["ids"][0]
    assert (
        _get(f"{base}/api/structures/{crystal}")["symmetry_available"] is False
    )
    data = _get(f"{base}/api/structures/{crystal}/symmetry?tolerance=0.02")
    assert data == {"available": False, "install": INSTALL_HINT}
