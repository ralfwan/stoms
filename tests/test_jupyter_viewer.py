"""stoms.viewer: ASE structures in the viewer, without a ledger.

The browser side (drawing, frame stepping, SVG output, the widget's
messages) is tested in test_jupyter_viewer_browser.py.
"""

import html
import json
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.build import bulk, fcc111, molecule
from ase.calculators.singlepoint import SinglePointCalculator
from ase.io import Trajectory, write

from stoms.viewer import StaticView, view
from stoms.viewer import frames as frames_module
from stoms.viewer.base import read_settings
from stoms.viewer.frames import as_images, frame_payload


def water() -> Atoms:
    return molecule("H2O")


def silicon() -> Atoms:
    return bulk("Si", "diamond", a=5.43)


def slab() -> Atoms:
    return fcc111("Pt", (2, 2, 3), vacuum=6.0)


def trajectory(path: Path, count: int = 4) -> Path:
    """A short trajectory with energies and forces, as an optimiser writes."""
    with Trajectory(str(path), "w") as writer:
        for i in range(count):
            atoms = slab()
            atoms.positions[-1, 2] += 0.1 * i
            forces = np.zeros((len(atoms), 3))
            forces[-1] = [0.0, 0.0, -0.5 + 0.1 * i]
            atoms.calc = SinglePointCalculator(
                atoms, energy=-10.0 - i, forces=forces
            )
            writer.write(atoms)
    return path


# ---------------------------------------------------------------- frame JSON


def test_molecule_frame_has_no_cell_and_no_periodicity() -> None:
    atoms = water()
    frame = frame_payload(atoms, 0)
    assert frame["id"] == "frame-0"
    assert frame["symbols"] == ["O", "H", "H"]
    assert frame["numbers"] == [8, 1, 1]
    assert frame["pbc"] == [False, False, False]
    assert frame["cell"] == [[0.0] * 3] * 3
    assert np.allclose(frame["positions"], atoms.positions, atol=1e-6)
    assert frame["formula"] == "H2O"
    json.dumps(frame, allow_nan=False)


def test_bulk_frame_keeps_cell_and_full_periodicity() -> None:
    atoms = silicon()
    frame = frame_payload(atoms, 3)
    assert frame["id"] == "frame-3" and frame["frame"] == 3
    assert frame["pbc"] == [True, True, True]
    assert np.allclose(frame["cell"], atoms.cell.array, atol=1e-6)
    assert len(frame["positions"]) == 2


def test_slab_frame_is_not_periodic_along_its_vacuum() -> None:
    atoms = slab()
    frame = frame_payload(atoms, 0)
    assert frame["pbc"] == [True, True, False]
    assert frame["cell"][2][2] == pytest.approx(atoms.cell[2, 2])
    # fcc111 tags the layers: an ASE array, one value per atom.
    tags = next(a for a in frame["arrays"] if a["name"] == "tags")
    assert tags["kind"] == "number" and tags["source"] == "arrays"
    assert tags["values"] == atoms.get_tags().tolist()


def test_calculator_results_and_info_become_properties_and_arrays() -> None:
    atoms = water()
    forces = np.arange(9.0).reshape(3, 3)
    atoms.calc = SinglePointCalculator(
        atoms,
        energy=-14.2,
        forces=forces,
        charges=[-0.8, 0.4, 0.4],
        stress=np.zeros(6),
    )
    atoms.info.update(
        {"temperature": 300.0, "label": "relaxed", "bad": float("nan")}
    )
    atoms.info["object"] = object()  # not JSON: left out
    frame = frame_payload(atoms, 0)
    arrays = {(a["source"], a["name"]): a for a in frame["arrays"]}
    assert arrays["calculator", "forces"]["kind"] == "vector"
    assert arrays["calculator", "forces"]["unit"] == "eV/Å"
    assert arrays["calculator", "forces"]["values"] == forces.tolist()
    assert arrays["calculator", "charges"]["values"] == [-0.8, 0.4, 0.4]
    properties = {(p["source"], p["name"]): p for p in frame["properties"]}
    assert properties["calculator", "energy"] == {
        "name": "energy",
        "source": "calculator",
        "unit": "eV",
        "value": -14.2,
    }
    # A stress has six values but belongs to the structure, not the atoms.
    assert properties["calculator", "stress"]["value"] == [0.0] * 6
    assert properties["info", "temperature"]["value"] == 300.0
    assert properties["info", "label"]["value"] == "relaxed"
    assert ("info", "object") not in properties
    assert ("info", "bad") not in properties  # NaN has no JSON value
    json.dumps(frame, allow_nan=False)


def test_calculator_is_not_run() -> None:
    class Exploding(SinglePointCalculator):
        def get_property(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("the viewer must not compute properties")

    atoms = water()
    atoms.calc = Exploding(atoms, energy=1.0)
    assert frame_payload(atoms, 0)["properties"][0]["value"] == 1.0


def test_non_finite_positions_are_refused() -> None:
    atoms = water()
    atoms.positions[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        frame_payload(atoms, 0)


# ---------------------------------------------------------------- inputs


def test_inputs_one_atoms_a_list_a_trajectory_a_generator_a_file(
    tmp_path: Path,
) -> None:
    assert len(as_images(water())) == 1
    assert len(as_images([water(), silicon(), slab()])) == 3
    path = trajectory(tmp_path / "opt.traj")
    with Trajectory(str(path)) as reader:
        images = as_images(reader)
    assert len(images) == 4
    # Calculator results survive the copy (without the calculator object).
    assert images[2].calc.results["energy"] == -12.0
    assert len(as_images(atoms for atoms in [water(), water()])) == 2
    write(tmp_path / "frames.extxyz", [silicon(), silicon()])
    assert len(as_images(tmp_path / "frames.extxyz")) == 2
    assert len(as_images(str(tmp_path / "frames.extxyz"))) == 2


@pytest.mark.parametrize("bad", [42, {"a": water()}, [water(), "x"]])
def test_inputs_other_than_atoms_are_refused(bad: object) -> None:
    with pytest.raises(TypeError):
        as_images(bad)


def test_no_frames_is_refused() -> None:
    with pytest.raises(ValueError, match="no frames"):
        as_images([])


def test_too_many_frames_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(frames_module, "MAX_FRAMES", 3)
    with pytest.raises(ValueError, match=r"images\[::10\]"):
        as_images([water()] * 4)
    with pytest.raises(ValueError, match="at most 3"):
        as_images(water() for _ in range(4))


def test_view_does_not_change_or_keep_the_callers_atoms() -> None:
    atoms = slab()
    atoms.calc = SinglePointCalculator(atoms, energy=-1.0)
    before = atoms.positions.copy()
    viewer = view(atoms, static=True)
    viewer.show_bonds = True
    viewer.to_html()
    assert np.array_equal(atoms.positions, before)
    assert atoms.calc.results == {"energy": -1.0}
    # Later changes to the caller's atoms do not reach the viewer.
    atoms.positions += 1.0
    shown = viewer.selected_atoms
    assert np.allclose(shown.positions, before)
    assert shown.calc.results["energy"] == -1.0
    # selected_atoms is a copy too.
    shown.positions += 5.0
    assert np.allclose(viewer.selected_atoms.positions, before)


def test_stoms_viewer_does_not_load_the_ledger() -> None:
    code = (
        "import sys\n"
        "from ase.build import bulk\n"
        "from stoms.viewer import view\n"
        "v = view(bulk('Cu'), static=True)\n"
        "v.to_html()\n"
        "loaded = [m for m in sys.modules if m.startswith("
        "('stoms.atomsledger', 'stoms.web'))]\n"
        "assert not loaded, loaded\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


# ---------------------------------------------------------------- settings


def test_settings_files_viewer_settings_and_paths(tmp_path: Path) -> None:
    file = {
        "stoms_viewer_settings": 1,
        "settings": {"bonds": True},
        "view": {"R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "scale": 30},
    }
    assert read_settings(file) == (file["settings"], file["view"], [])
    assert read_settings({"cell": False}) == ({"cell": False}, {}, [])
    assert read_settings(None) == ({}, {}, [])
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(file))
    assert read_settings(path)[0] == {"bonds": True}
    # A copy: changing it later does not change the viewer.
    settings, _, _ = read_settings(file)
    settings["bonds"] = False
    assert file["settings"]["bonds"] is True
    with pytest.raises(ValueError, match="version"):
        read_settings({"stoms_viewer_settings": 2, "settings": {}})
    with pytest.raises(TypeError):
        read_settings(42)
    with pytest.raises(ValueError, match="JSON"):
        read_settings({"x": float("nan")})


def test_properties_are_views_onto_the_settings() -> None:
    viewer = view(silicon(), static=True, settings={"bonds": True})
    assert viewer.show_bonds is True
    assert viewer.show_cell is True  # the default
    assert viewer.atom_scale == 1.0 and viewer.repeat == [1, 1, 1]
    viewer.show_cell = False
    viewer.atom_scale = 0.8
    assert viewer.polyhedra_opacity == 0.45 and viewer.plane_opacity == 0.2
    viewer.polyhedra_opacity = 0.9
    viewer.plane_opacity = 0
    assert viewer.bond_radius == 0.08 and viewer.depth_cue is False
    assert viewer.depth_strength == 0.6
    viewer.bond_radius = 0.15
    viewer.depth_cue = True
    viewer.depth_strength = 0.3
    assert viewer.settings["appearance"]["polyAlpha"] == 0.9
    assert viewer.settings["appearance"]["planeAlpha"] == 0.0
    assert viewer.cell_width == 1.0 and viewer.cell_colour is None
    assert viewer.cell_style == "solid"
    viewer.cell_width = 2.5
    viewer.cell_colour = "#ff0000"
    viewer.cell_style = "dashed"
    viewer.repeat = (2, 2, 1)
    viewer.labels = "element"
    viewer.transparent = False
    viewer.panel_size = (600, 400)
    assert viewer.settings == {
        "bonds": True,
        "cell": False,
        "appearance": {
            "atomScale": 0.8,
            "polyAlpha": 0.9,
            "planeAlpha": 0.0,
            "bondRadius": 0.15,
            "depthCue": True,
            "depthStrength": 0.3,
            "cellWidth": 2.5,
            "cellColour": "#ff0000",
            "cellDash": "dashed",
        },
        "repeat": [2, 2, 1],
        "labels": "element",
        "svgTransparent": False,
        "panelSize": {"width": 600, "height": 400},
    }
    exported = viewer.get_settings()
    assert exported["stoms_viewer_settings"] == 1
    assert exported["settings"] == viewer.settings
    # The same look for another structure.
    other = view(slab(), static=True, settings=exported)
    assert other.settings == viewer.settings
    for name, value in [
        ("show_cell", 1),
        ("labels", "value"),
        ("repeat", (0, 1, 1)),
        ("atom_scale", 0),
        ("polyhedra_opacity", 1.5),
        ("plane_opacity", -0.1),
        ("bond_radius", 1.0),
        ("depth_strength", 0),
        ("depth_cue", "yes"),
        ("cell_width", 0),
        ("cell_width", 10),
        ("cell_colour", "red"),
        ("cell_style", "dashdot"),
        ("panel_size", (10, None)),
    ]:
        with pytest.raises((TypeError, ValueError)):
            setattr(viewer, name, value)


def test_width_and_height_set_the_panel_size() -> None:
    viewer = view(water(), static=True, width=500, height=300)
    assert viewer.panel_size == (500, 300)


def test_frames_can_be_chosen_and_counted_from_the_end() -> None:
    viewer = view([water(), silicon(), slab()], static=True, frame=-1)
    assert viewer.frame == 2
    assert viewer.selected_atoms.get_chemical_formula() == "Pt12"
    viewer.frame = 1
    assert viewer.selected_atoms.get_chemical_formula() == "Si2"
    with pytest.raises(IndexError):
        viewer.frame = 3
    with pytest.raises(TypeError):
        viewer.frame = 1.5


# ---------------------------------------------------------------- documents


def _embedded(document: str) -> dict:
    start = document.index('<script type="application/json" id="stoms-data">')
    start = document.index(">", start) + 1
    return json.loads(document[start : document.index("</script>", start)])


def test_html_document_holds_the_frames_and_state() -> None:
    viewer = view(
        [water(), silicon()],
        static=True,
        frame=1,
        settings={"bonds": True},
        title="Two structures",
    )
    document = viewer.to_html()
    data = _embedded(document)
    assert [f["formula"] for f in data["frames"]] == ["H2O", "Si2"]
    assert data["frame"] == 1 and data["settings"] == {"bonds": True}
    assert data["bridge"] is False
    assert "<title>Two structures</title>" in document
    # The viewer's own scripts, inlined: no server, nothing fetched.
    for name in ("function buildScene", "function panelsToSvg", "STOMS_EMBED"):
        assert name in document
    assert 'src="' not in document and "<link" not in document


def test_text_from_the_atoms_cannot_end_the_script() -> None:
    atoms = water()
    atoms.info["comment"] = "</script><script>alert(1)</script>"
    document = view(atoms, static=True).to_html()
    assert document.count("</script>") == document.count("<script")
    assert _embedded(document)["frames"][0]["properties"][0]["value"] == (
        "</script><script>alert(1)</script>"
    )


def test_static_view_is_html_output_and_saves_html_only(
    tmp_path: Path,
) -> None:
    viewer = view(water(), static=True)
    output = viewer._repr_html_()
    assert output.startswith("<iframe") and "srcdoc=" in output
    srcdoc = output.split('srcdoc="', 1)[1].split('"></iframe>', 1)[0]
    assert html.unescape(srcdoc) == viewer.to_html()
    path = viewer.save(tmp_path / "water.html")
    assert path.read_text(encoding="utf-8") == viewer.to_html()
    with pytest.raises(ValueError, match="Save SVG button"):
        viewer.save(tmp_path / "water.svg")
    with pytest.raises(ValueError, match=".png"):
        viewer.save(tmp_path / "water.png")


def test_open_in_browser_writes_the_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    viewer = view(water(), static=True)
    path = viewer.open_in_browser(tmp_path / "w.html")
    assert opened == [path.resolve().as_uri()]
    assert path.read_text(encoding="utf-8") == viewer.to_html()


def test_without_anywidget_view_warns_and_is_static(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "stoms.viewer.widget", None)
    with pytest.warns(UserWarning, match="stoms\\[jupyter\\]"):
        viewer = view(water())
    assert isinstance(viewer, StaticView)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert isinstance(view(water(), static=True), StaticView)


# ---------------------------------------------------------------- widget

# These need anywidget (the jupyter extra; installed with the dev group).
needs_anywidget = pytest.mark.skipif(
    __import__("importlib").util.find_spec("anywidget") is None,
    reason="anywidget is not installed",
)


@needs_anywidget
def test_view_is_a_widget_with_the_state_as_traits() -> None:
    import anywidget

    from stoms.viewer import StaleViewError, Viewer

    viewer = view([water(), silicon()], settings={"bonds": True})
    assert isinstance(viewer, Viewer) and isinstance(
        viewer, anywidget.AnyWidget
    )
    bundle = viewer._repr_mimebundle_()
    bundle = bundle[0] if isinstance(bundle, tuple) else bundle
    assert "application/vnd.jupyter.widget-view+json" in bundle
    state = viewer.get_state()
    assert state["settings"] == {"bonds": True} and state["frame"] == 0
    data = _embedded(state["_document"])
    assert data["bridge"] is True and len(data["frames"]) == 2
    viewer.frame = -1
    assert viewer.frame == 1
    with pytest.raises(Exception, match="no frame 2"):
        viewer.frame = 2
    with pytest.raises(StaleViewError, match="no SVG has been drawn"):
        viewer.to_svg()


@needs_anywidget
def test_save_writes_the_svg_drawn_for_the_current_state(
    tmp_path: Path,
) -> None:
    from stoms.viewer import StaleViewError

    viewer = view([water(), silicon()])
    drawn = {"frame": 0, "settings": {"cell": True}, "camera": {"scale": 20}}
    svg = '<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>\n'
    # As the browser sends it (see widget.js): state traits and snapshot.
    viewer.set_state({**drawn, "_snapshot": {"state": drawn, "svg": svg}})
    assert viewer.save(tmp_path / "a.svg").read_text(encoding="utf-8") == svg
    viewer.frame = 1  # changed in this cell: the browser has not drawn it
    with pytest.raises(StaleViewError, match="next cell"):
        viewer.save(tmp_path / "b.svg")
    assert not (tmp_path / "b.svg").exists()
    html_path = viewer.save(tmp_path / "v.html")
    assert _embedded(html_path.read_text(encoding="utf-8"))["frame"] == 1


@needs_anywidget
def test_set_images_and_set_view() -> None:
    viewer = view([water(), silicon(), slab()], frame=2)
    sent = []
    viewer.send = sent.append  # type: ignore[method-assign]
    viewer.set_view("-c")
    assert sent == [{"type": "view", "name": "-c"}]
    with pytest.raises(ValueError):
        viewer.set_view("diagonal")
    viewer.set_images(water())
    assert viewer.frame == 0 and viewer._snapshot == {}
    assert [f["formula"] for f in _embedded(viewer._document)["frames"]] == [
        "H2O"
    ]


# ---------------------------------------------------------------- phonons

needs_phonopy = pytest.mark.skipif(
    __import__("importlib").util.find_spec("phonopy") is None,
    reason="phonopy is not installed",
)
INAS = Path(__file__).parent / "data" / "phonopy" / "inas"


def inas_viewer():
    from stoms.viewer import view_phonons

    return view_phonons(
        INAS / "POSCAR", dim="5", force_constants=INAS / "FORCE_CONSTANTS"
    )


def ask(viewer, path: str, request_id: int = 1) -> dict:
    """A request of the page, as widget.js sends it; the reply sent back."""
    sent = []
    viewer.send = sent.append
    viewer._on_message(
        viewer, {"type": "api", "id": request_id, "path": path}, []
    )
    [reply] = sent
    assert reply["type"] == "api" and reply["id"] == request_id
    return reply


@needs_anywidget
@needs_phonopy
def test_view_phonons_shows_the_primitive_cell_with_modes() -> None:
    viewer = inas_viewer()
    [frame] = _embedded(viewer._document)["frames"]
    assert frame["has_modes"] is True and frame["has_phonons"] is True
    assert sorted(frame["symbols"]) == ["As", "In"]
    assert viewer.selected_atoms.get_chemical_formula() == "AsIn"
    assert viewer.phonons is not None
    # The live viewer asks Python; nothing is computed up front.
    assert _embedded(viewer._document)["api"] == {}


@needs_anywidget
@needs_phonopy
def test_phonon_requests_are_answered_like_the_server() -> None:
    viewer = inas_viewer()
    reply = ask(viewer, "structures/frame-0/modes?q=0.5,0,0.25")
    [point] = reply["data"]["qpoints"]
    assert reply["data"]["any_q"] is True
    assert point == viewer.phonons.modes((0.5, 0.0, 0.25))
    assert len(point["frequencies"]) == 6
    assert np.shape(point["displacements"]) == (6, 2, 6)
    gamma = ask(viewer, "structures/frame-0/modes", 2)["data"]["qpoints"][0]
    assert gamma["q"] == [0.0, 0.0, 0.0]
    bands = ask(viewer, "structures/frame-0/phonons/bands?nac=0", 3)["data"]
    assert bands == viewer.phonons.bands(False) and bands["segments"]
    dos = ask(viewer, "structures/frame-0/phonons/dos", 4)["data"]
    assert set(dos["elements"]) == {"In", "As"}


@needs_anywidget
@needs_phonopy
@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("structures/frame-0/rings?settings={}", "cannot answer"),
        ("structures/frame-0/modes?q=1,2", "three numbers"),
        ("structures/frame-0/phonons/dos?nac=yes", "nac"),
        ("structures/other/modes", "cannot answer"),
    ],
)
def test_phonon_request_errors_go_back_to_the_page(
    path: str, message: str
) -> None:
    reply = ask(inas_viewer(), path)
    assert "data" not in reply and message in reply["error"]


@needs_anywidget
def test_viewers_without_phonons_answer_with_an_error() -> None:
    reply = ask(view(water()), "structures/frame-0/modes")
    assert "no phonon calculation" in reply["error"]


@needs_anywidget
@needs_phonopy
def test_saved_html_keeps_gamma_the_bands_and_the_dos(tmp_path: Path) -> None:
    viewer = inas_viewer()
    data = _embedded(
        viewer.save(tmp_path / "inas.html").read_text(encoding="utf-8")
    )
    assert set(data["api"]) == {
        "structures/frame-0/modes",
        "structures/frame-0/phonons/bands",
        "structures/frame-0/phonons/dos",
    }
    assert data["bridge"] is False


@needs_anywidget
@needs_phonopy
def test_view_phonons_takes_a_phonopy_object_or_a_model() -> None:
    from stoms.viewer import view_phonons

    model = inas_viewer().phonons
    assert view_phonons(model).phonons is model
    assert view_phonons(model.phonon).phonons.phonon is model.phonon
    with pytest.raises(TypeError, match="phonopy yaml"):
        view_phonons(water())
    with pytest.raises(TypeError):
        view_phonons(model, dim="2")


@needs_anywidget
@needs_phonopy
def test_set_images_drops_the_phonons() -> None:
    viewer = inas_viewer()
    viewer.set_images(silicon())
    assert viewer.phonons is None
    assert "has_modes" not in _embedded(viewer._document)["frames"][0]


@needs_anywidget
@needs_phonopy
def test_view_phonons_takes_dim_and_mesh_as_numbers() -> None:
    from stoms.viewer import view_phonons

    viewer = view_phonons(
        INAS / "POSCAR",
        dim=[5, 5, 5],
        dos_mesh=10,
        force_constants=str(INAS / "FORCE_CONSTANTS"),
    )
    assert viewer.phonons.dos_mesh == 10.0
    assert len(viewer.phonons.phonon.supercell) == 250


def test_force_arrow_properties_are_views_onto_the_settings() -> None:
    viewer = view(water(), static=True)
    assert viewer.show_forces is False and viewer.force_scale == 1.0
    viewer.show_forces = True
    viewer.force_scale = 2.5
    assert viewer.settings["arrows"] == {"show": True, "scale": 2.5}
    viewer.atom_scale = 0.7  # another group, kept apart
    assert viewer.settings["appearance"] == {"atomScale": 0.7}
    for name, value in [
        ("show_forces", "yes"),
        ("force_scale", 0),
        ("force_scale", float("inf")),
    ]:
        with pytest.raises((TypeError, ValueError)):
            setattr(viewer, name, value)
    assert viewer.measurements == []  # not linked: nothing comes back


def test_vector_columns_reach_the_page_for_arrows() -> None:
    atoms = water()
    atoms.arrays["REF_forces"] = np.ones((3, 3))
    atoms.calc = SinglePointCalculator(atoms, forces=np.zeros((3, 3)))
    arrays = {
        (a["source"], a["name"]): a for a in frame_payload(atoms, 0)["arrays"]
    }
    assert arrays["arrays", "REF_forces"]["kind"] == "vector"
    assert arrays["calculator", "forces"]["unit"] == "eV/Å"


def test_show_displacements_writes_the_arrow_and_reference_settings() -> None:
    viewer = view([slab(), slab(), slab()], static=True)
    viewer.force_scale = 2.0
    viewer.show_displacements()
    assert viewer.settings["arrows"] == {
        "scale": 2.0,
        "show": True,
        "source": "displacement",
    }
    assert viewer.settings["displacement"] == {
        "reference": "first",
        "frame": 0,
    }
    assert viewer.arrow_source == "displacement" and viewer.show_forces
    viewer.show_displacements("previous", show=False)
    assert viewer.settings["displacement"]["reference"] == "previous"
    assert viewer.show_forces is False
    viewer.show_displacements(-1)  # from the end, as in Python
    assert viewer.settings["displacement"] == {
        "reference": "frame",
        "frame": 2,
    }
    viewer.show_displacements(1)
    assert viewer.settings["displacement"] == {
        "reference": "frame",
        "frame": 1,
    }
    viewer.arrow_source = "vectors"  # back to forces
    assert viewer.settings["arrows"]["source"] == "vectors"
    for reference in ("compared", "last", 3, -4, 1.0, True):
        with pytest.raises(ValueError):
            viewer.show_displacements(reference)
    with pytest.raises(TypeError):
        viewer.show_displacements(show="yes")
    with pytest.raises(ValueError):
        viewer.arrow_source = "forces"
    # One frame: nothing to compare with.
    with pytest.raises(ValueError, match="two frames"):
        view(slab(), static=True).show_displacements()


def test_colour_by_displacement() -> None:
    viewer = view([slab(), slab()], static=True)
    viewer.colour_by("displacement", component="z")
    assert viewer.settings["property"]["choice"] == {
        "source": "derived",
        "name": "displacement",
    }
    assert viewer.settings["property"]["component"] == "z"


@needs_anywidget
def test_measurements_come_from_the_browser() -> None:
    viewer = view(water())

    def ref(index: int, symbol: str, image=(0, 0, 0)) -> dict:
        return {
            "index": index,
            "image": list(image),
            "symbol": symbol,
            "count": 3,
        }

    viewer.set_state(
        {
            "_measurements": [
                {
                    "kind": "distance",
                    "atoms": [ref(0, "O"), ref(1, "H", (1, 0, 0))],
                    "value": 0.97,
                    "nearest": None,
                },
                {
                    "kind": "angle",
                    "atoms": [ref(1, "H"), ref(0, "O"), ref(2, "H")],
                    "value": 104.0,
                    "nearest": None,
                },
            ]
        }
    )
    distance, angle = viewer.measurements
    assert distance == {
        "kind": "distance",
        "atoms": [0, 1],
        "images": [(0, 0, 0), (1, 0, 0)],
        "value": 0.97,
        "unit": "Å",
        "nearest": None,
    }
    assert angle["unit"] == "°" and "nearest" not in angle
    # Saved HTML shows them again (the page computes the values).
    data = _embedded(viewer.to_html())
    assert [m["kind"] for m in data["measurements"]] == ["distance", "angle"]
    assert "value" not in data["measurements"][0]
    viewer.set_images(silicon())
    assert viewer.measurements == []


def test_position_measurements_come_from_the_browser() -> None:
    viewer = view(water())
    ref = {"index": 1, "image": [0, 1, 0], "symbol": "H", "count": 3}
    viewer.set_state(
        {
            "_measurements": [
                {
                    "kind": "position",
                    "atoms": [ref],
                    "value": [0.5, 1.25, -0.75],
                    "nearest": None,
                },
                {"kind": "position", "atoms": [ref], "value": None},
            ]
        }
    )
    shown, other_atoms = viewer.measurements
    assert shown == {
        "kind": "position",
        "atoms": [1],
        "images": [(0, 1, 0)],
        "value": (0.5, 1.25, -0.75),
        "unit": "Å",
    }
    assert other_atoms["value"] is None
    # A settings file keeps it (one atom).
    item = {"kind": "position", "atoms": [ref]}
    file = {"stoms_viewer_settings": 1, "measurements": [item]}
    assert read_settings(file)[2] == [item]


def atom(index: int, symbol: str, image=(0, 0, 0), count: int = 3) -> dict:
    return {
        "index": index,
        "image": list(image),
        "symbol": symbol,
        "count": count,
    }


O_H = {"kind": "distance", "atoms": [atom(0, "O"), atom(1, "H")]}
H_O_H = {"kind": "angle", "atoms": [atom(1, "H"), atom(0, "O"), atom(2, "H")]}


def test_settings_files_carry_measurements() -> None:
    file = {
        "stoms_viewer_settings": 1,
        "settings": {},
        "measurements": [O_H, H_O_H],
    }
    _, _, measurements = read_settings(file)
    assert measurements == [O_H, H_O_H]
    viewer = view(water(), static=True, settings=file)
    assert viewer.get_settings()["measurements"] == [O_H, H_O_H]
    assert _embedded(viewer.to_html())["measurements"] == [O_H, H_O_H]
    # A plain settings dictionary has none; a file without them neither.
    assert view(water(), static=True).get_settings()["measurements"] == []


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "torsion", "atoms": [atom(0, "O"), atom(1, "H")]},
        {"kind": "distance", "atoms": [atom(0, "O")]},
        {"kind": "distance", "atoms": [atom(0, "O"), atom(3, "H")]},  # count 3
        {"kind": "distance", "atoms": [atom(0, "O"), {"index": 1}]},
        {"kind": "distance", "atoms": [atom(0, "O"), atom(1, "H", (0, 0))]},
        {"kind": "distance", "atoms": [atom(0, "O"), atom(True, "H")]},
        {"kind": "position", "atoms": [atom(0, "O"), atom(1, "H")]},
    ],
)
def test_malformed_measurements_are_refused(bad: dict) -> None:
    with pytest.raises(ValueError, match="measurement 0"):
        read_settings({"stoms_viewer_settings": 1, "measurements": [bad]})


@needs_anywidget
def test_measurements_made_in_one_viewer_come_back_in_another() -> None:
    first = view(water())
    first.set_state(
        {"_measurements": [{**O_H, "value": 0.97, "nearest": None}]}
    )
    settings = first.get_settings()
    assert settings["measurements"] == [
        O_H
    ]  # no values: the viewer computes them
    json.dumps(settings)
    second = view(water(), settings=settings)
    assert _embedded(second._document)["measurements"] == [O_H]
    assert [m["atoms"] for m in second.measurements] == [[0, 1]]
    assert (
        second.measurements[0]["value"] is None
    )  # until the page has drawn it


def test_colour_by_writes_the_viewers_property_settings() -> None:
    atoms = water()
    atoms.calc = SinglePointCalculator(atoms, charges=[-0.8, 0.4, 0.4])
    atoms.info["charges"] = [1, 2, 3]  # the same name in atoms.info
    viewer = view(atoms, static=True)
    viewer.colour_by(
        "charges", range=(-1, None), symmetric=True, palette="diverging"
    )
    assert viewer.settings["colour"] == "property"
    assert viewer.settings["property"] == {
        "choice": {
            "source": "array",
            "origin": "calculator",
            "name": "charges",
        },
        "component": "norm",
        "kind": "auto",
        "min": -1,
        "max": None,
        "symmetric": True,
    }
    assert viewer.settings["palettes"] == {"property": "diverging"}
    viewer.colour_by("charges", source="info", kind="categories")
    assert viewer.settings["property"]["choice"]["origin"] == "info"
    viewer.colour_by("z")
    assert viewer.settings["property"]["choice"] == {
        "source": "derived",
        "name": "z",
    }
    viewer.color_by(None)
    assert viewer.settings["colour"] == "element"
    for args, kwargs in [
        (("magmoms",), {}),
        (("charges",), {"source": "arrays"}),
        (("charges",), {"component": "w"}),
        (("charges",), {"kind": "bins"}),
        (("charges",), {"palette": "rainbow"}),
        (("charges",), {"range": (0, float("nan"))}),
    ]:
        with pytest.raises(ValueError):
            viewer.colour_by(*args, **kwargs)
    # The look, with its colouring, carries over to other structures.
    assert (
        view(atoms, static=True, settings=viewer.get_settings()).settings[
            "colour"
        ]
        == "element"
    )


def test_structure_setting_properties_check_their_values() -> None:
    viewer = view(silicon(), static=True)
    assert viewer.hidden_elements == [] and viewer.planes == []
    assert viewer.slice == {
        "a": (None, None),
        "b": (None, None),
        "c": (None, None),
    }
    assert viewer.polyhedron_centres is None and viewer.element_colours == {}
    viewer.slice = [(0, 0.5), None, (None, 0.8)]
    assert viewer.settings["slice"] == [[0, 0.5], [None, None], [None, 0.8]]
    viewer.bond_cutoffs = {"Si-O": 1.8, ("Si", "Si"): 2.6}
    assert viewer.bond_cutoffs == {"O-Si": 1.8, "Si-Si": 2.6}
    viewer.element_colours = {"Si": "#abcdef"}
    viewer.element_radii = {"Si": 1}
    viewer.atom_scale = 0.8  # the same group: kept apart
    assert viewer.settings["appearance"] == {
        "colours": {"Si": "#abcdef"},
        "radii": {"Si": 1.0},
        "atomScale": 0.8,
    }
    viewer.add_plane(1, 1, 1)
    viewer.add_plane(1, 0, 0, t=0.25, colour="#e34948", show=False)
    assert viewer.planes[1] == {
        "h": 1,
        "k": 0,
        "l": 0,
        "t": 0.25,
        "show": False,
        "colour": "#e34948",
    }
    viewer.clear_planes()
    assert viewer.planes == []
    # The position in Å from the origin: t = distance / d; in a cubic cell
    # d(1 1 1) = a / √3, d(0 0 2) = a / 2.
    cubic = view(bulk("Si", "diamond", a=5.43, cubic=True), static=True)
    cubic.add_plane(1, 1, 1, distance=5.43 / np.sqrt(3) / 4)
    cubic.add_plane(0, 0, 2, distance=5.43)
    assert [p["t"] for p in cubic.planes] == pytest.approx([0.25, 2.0])
    with pytest.raises(ValueError):
        cubic.add_plane(1, 1, 1, t=0.5, distance=1.0)
    with pytest.raises(ValueError):
        cubic.add_plane(0, 0, 0, distance=1.0)
    for name, value in [
        ("hidden_elements", "Si"),
        ("slice", {"c": ("low", None)}),
        ("slice", [None, None]),
        ("bond_cutoffs", {"Si": 2.0}),
        ("bond_cutoffs", {"Si-Si": -1}),
        ("element_colours", {"Si": "red"}),
        ("element_radii", {"Si": 0}),
        ("planes", [{"h": 0, "k": 0, "l": 0}]),
        ("planes", [{"h": 1.5, "k": 0, "l": 0}]),
    ]:
        with pytest.raises((TypeError, ValueError)):
            setattr(viewer, name, value)
    # Part of the look: reproduced by get_settings().
    viewer.add_plane(0, 0, 1)
    assert (
        view(silicon(), static=True, settings=viewer.get_settings()).planes
        == viewer.planes
    )


def test_show_polyhedron_centres_round_trips() -> None:
    viewer = view(silicon(), static=True)
    assert viewer.show_polyhedron_centres is True  # the default
    viewer.show_polyhedron_centres = False
    assert viewer.settings == {"polyhedraCentres": False}
    with pytest.raises(TypeError):
        viewer.show_polyhedron_centres = "no"
    # Settings files and the notebook HTML carry it.
    file = viewer.get_settings()
    assert file["settings"]["polyhedraCentres"] is False
    again = view(silicon(), static=True, settings=file)
    assert again.show_polyhedron_centres is False
    assert _embedded(again.to_html())["settings"]["polyhedraCentres"] is False


def test_repeat_cell_outline_round_trips() -> None:
    viewer = view(silicon(), static=True)
    assert viewer.repeat_cell_outline is False  # the default
    viewer.repeat_cell_outline = True
    assert viewer.settings == {"repeatCellOutline": True}
    with pytest.raises(TypeError):
        viewer.repeat_cell_outline = 1
    # Settings files and the notebook HTML carry it.
    file = viewer.get_settings()
    assert file["settings"]["repeatCellOutline"] is True
    again = view(silicon(), static=True, settings=file)
    assert again.repeat_cell_outline is True
    assert _embedded(again.to_html())["settings"]["repeatCellOutline"] is True


def test_single_cell_round_trips() -> None:
    viewer = view(silicon(), static=True)
    assert viewer.single_cell is False  # the default
    viewer.single_cell = True
    assert viewer.settings == {"singleCell": True}
    with pytest.raises(TypeError):
        viewer.single_cell = 1
    # Settings files and the notebook HTML carry it.
    file = viewer.get_settings()
    assert file["settings"]["singleCell"] is True
    again = view(silicon(), static=True, settings=file)
    assert again.single_cell is True
    assert _embedded(again.to_html())["settings"]["singleCell"] is True


def test_profile_is_simple_by_default_and_round_trips(tmp_path: Path) -> None:
    """viewer.profile (GUI profiles): which controls the viewer shows; in
    the page and saved HTML, never in the settings."""
    viewer = view(water(), static=True)
    assert viewer.profile == "simple"
    assert _embedded(viewer.to_html())["profile"] == "simple"
    viewer.profile = "advanced"
    assert viewer.profile == "advanced"
    path = viewer.save(tmp_path / "viewer.html")
    assert _embedded(path.read_text(encoding="utf-8"))["profile"] == "advanced"
    for wrong in ("expert", "Simple", None, 1):
        with pytest.raises(ValueError, match="simple"):
            viewer.profile = wrong
    assert viewer.profile == "advanced"
    # Not a setting: settings files and get_settings() never hold it.
    saved = viewer.get_settings()
    assert "profile" not in saved and "profile" not in saved["settings"]
    assert "profile" not in json.dumps(saved)
    assert view(water(), static=True, profile="advanced").profile == "advanced"
    with pytest.raises(ValueError):
        view(water(), static=True, profile="all")


@needs_anywidget
def test_widget_profile_is_synced_state() -> None:
    viewer = view(water())
    assert viewer.profile == "simple"
    assert viewer.get_state()["_profile"] == "simple"
    assert _embedded(viewer._document)["profile"] == "simple"
    viewer.profile = "advanced"
    assert viewer.get_state()["_profile"] == "advanced"
    # Saved HTML keeps it (the live page has it from the widget state).
    assert _embedded(viewer.to_html())["profile"] == "advanced"
    # The browser's choice arrives as widget state.
    viewer.set_state({"_profile": "simple"})
    assert viewer.profile == "simple"
    with pytest.raises(ValueError):
        viewer.profile = "expert"
    assert "profile" not in viewer.settings
    assert view(water(), profile="advanced").profile == "advanced"
