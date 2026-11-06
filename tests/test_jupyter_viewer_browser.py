"""stoms.viewer in a real browser (headless Chromium via Playwright).

The standalone document (StaticView, pop-out tabs, saved HTML) is opened as
a file. The widget is tested with its real front end (widget.js) and the real
Python Viewer, linked by a stand-in for anywidget's model: what the page
saves is applied with Viewer.set_state, as ipywidgets does for messages from
the browser, and Python's changes are set on the stand-in model.

Skipped unless the ``browser`` dependency group and Chromium are installed
(see test_viewer_browser.py).
"""

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from ase.build import bulk, fcc111, molecule

from stoms.viewer import view
from stoms.viewer.base import DEFAULTS, NESTED_DEFAULTS

pytest.importorskip("playwright.sync_api")

from test_viewer_browser import browser  # noqa: E402,F401  (fixture)

SVG = "{http://www.w3.org/2000/svg}"
WIDGET_JS = (
    Path(__file__).parents[1] / "src" / "stoms" / "viewer" / "widget.js"
).read_text(encoding="utf-8")
IDENTITY_CAMERA = {
    "R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "scale": 40,
    "pan": [0, 0],
}


def frames() -> list:
    """A short trajectory: a slab whose top atom moves up."""
    images = []
    for i in range(3):
        atoms = fcc111("Pt", (2, 2, 3), vacuum=6.0)
        atoms.positions[-1, 2] += 0.5 * i
        images.append(atoms)
    return images


@pytest.fixture
def page(browser: Any) -> Any:  # noqa: F811
    context = browser.new_context(
        viewport={"width": 1000, "height": 800}, accept_downloads=True
    )
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.on(
        "console",
        lambda m: page.errors.append(m.text) if m.type == "error" else None,
    )
    yield page
    context.close()


def open_document(page: Any, viewer: Any, tmp_path: Path) -> Any:
    path = viewer.save(tmp_path / "viewer.html")
    page.goto(path.as_uri())
    page.wait_for_function("document.querySelector('canvas')?.width > 0")
    return page


def parse_svg(text: str) -> ET.Element:
    root = ET.fromstring(text.encode())
    assert root.tag == f"{SVG}svg"
    return root


def is_vector(root: ET.Element) -> bool:
    """Shapes only: no embedded raster image, no data URLs."""
    tags = {node.tag.removeprefix(SVG) for node in root.iter()}
    text = ET.tostring(root, encoding="unicode")
    return (
        "image" not in tags
        and "foreignObject" not in tags
        and "data:" not in text
    )


def spheres(root: ET.Element) -> list[ET.Element]:
    return [
        c
        for c in root.iter(f"{SVG}circle")
        if c.get("fill", "").startswith("url(#sphere")
    ]


# ---------------------------------------------------------------- the document


def test_document_draws_and_steps_through_frames(
    page: Any, tmp_path: Path
) -> None:
    open_document(page, view(frames(), static=True), tmp_path)
    assert (
        page.locator(".embed-status")
        .inner_text()
        .startswith("Pt12 · 12 atoms · pbc TTF")
    )
    number = page.locator(".frame-number")
    assert number.input_value() == "0"
    page.locator("button[title^='Next frame']").click()
    assert number.input_value() == "1"
    page.locator(".viewer-stage").click()
    page.keyboard.press("ArrowRight")
    assert number.input_value() == "2"
    page.keyboard.press("ArrowRight")  # no frame 3: stays
    assert number.input_value() == "2"
    assert page.errors == []


def test_single_structures_have_no_frame_controls(
    page: Any, tmp_path: Path
) -> None:
    open_document(page, view(molecule("C6H6"), static=True), tmp_path)
    assert page.locator(".frame-slider").count() == 0
    # A molecule has no periodic axis: no Wrap, no repeat.
    assert page.locator("label:has-text('Wrap')").count() == 0
    assert "pbc FFF" in page.locator(".embed-status").inner_text()
    assert page.errors == []


def test_python_defaults_match_the_viewer(page: Any, tmp_path: Path) -> None:
    open_document(page, view(molecule("H2O"), static=True), tmp_path)
    prefs = page.evaluate("normalizePrefs({})")
    assert {key: prefs[key] for key in DEFAULTS} == DEFAULTS
    for (group, key), value in NESTED_DEFAULTS.items():
        assert prefs[group][key] == value, (group, key)


def test_save_svg_button_saves_the_view_as_vector_graphics(
    page: Any, tmp_path: Path
) -> None:
    viewer = view(
        bulk("Si", "diamond", a=5.43, cubic=True),
        static=True,
        settings={"bonds": True},
        width=500,
        height=400,
    )
    open_document(page, viewer, tmp_path)
    with page.expect_download() as download:
        page.get_by_role(
            "button", name="Save the view as an SVG (vector) image"
        ).click()
    assert download.value.suggested_filename == "Si8.svg"
    root = parse_svg(Path(download.value.path()).read_text(encoding="utf-8"))
    assert is_vector(root)
    # The panel size set from Python is the image size.
    assert (root.get("width"), root.get("height")) == ("500", "400")
    # Every atom is a shaded circle with an outline; cell edges and bonds
    # are lines (12 edges; 16 bonds, two halves each, plus their images).
    circles = spheres(root)
    assert len(circles) == 8
    assert all(c.get("stroke") == "#000" for c in circles)
    assert len(root.findall(f".//{SVG}radialGradient")) == 1
    assert len(root.findall(f".//{SVG}line")) > 12
    # Transparent by default: no background rectangle.
    assert root.find(f".//{SVG}rect") is None
    assert page.errors == []


def test_settings_and_camera_from_python_set_the_drawing(
    page: Any, tmp_path: Path
) -> None:
    radii = {}
    for scale in (1.0, 0.5):
        viewer = view(
            molecule("H2O"),
            static=True,
            settings={
                "stoms_viewer_settings": 1,
                "settings": {
                    "appearance": {"atomScale": scale},
                    "tripod": {"axes": "off"},
                },
                "view": IDENTITY_CAMERA,
            },
        )
        open_document(page, viewer, tmp_path)
        with page.expect_download() as download:
            page.get_by_role(
                "button", name="Save the view as an SVG (vector) image"
            ).click()
        root = parse_svg(
            Path(download.value.path()).read_text(encoding="utf-8")
        )
        radii[scale] = sorted(float(c.get("r")) for c in spheres(root))
        # The camera as given: 40 px per Å, so the O radius is 40 × its radius.
        assert page.evaluate("sharedView.scale") == 40
    assert radii[0.5] == pytest.approx([r / 2 for r in radii[1.0]], abs=0.02)


def test_pop_out_opens_a_copy_with_the_current_state(
    page: Any, tmp_path: Path
) -> None:
    open_document(page, view(frames(), static=True), tmp_path)
    page.locator("button[title^='Next frame']").click()
    page.locator("label[title='Bonds (ball and stick)'] input").check()
    with page.context.expect_page() as popup:
        page.get_by_role(
            "button", name="Open this view in a new browser tab"
        ).click()
    tab = popup.value
    tab.wait_for_function("document.querySelector('canvas')?.width > 0")
    assert tab.locator(".frame-number").input_value() == "1"
    assert tab.locator(
        "label[title='Bonds (ball and stick)'] input"
    ).is_checked()
    assert tab.evaluate("STOMS_EMBED.bridge") is False
    # A tab of its own: larger than the notebook panel.
    assert tab.evaluate("document.body.classList.contains('embed-standalone')")
    assert page.errors == []


# ---------------------------------------------------------------- the widget

needs_anywidget = pytest.mark.skipif(
    __import__("importlib").util.find_spec("anywidget") is None,
    reason="anywidget is not installed",
)

SETUP = """async ({ source, values }) => {
  const module = await import(URL.createObjectURL(new Blob([source], { type: "text/javascript" })));
  const handlers = {};
  window.saved = [];
  window.toKernel = [];
  const model = {
    get: (key) => values[key],
    set: (key, value) => { values[key] = value; for (const f of handlers[`change:${key}`] ?? []) f(); },
    on: (event, f) => { (handlers[event] ??= []).push(f); },
    off: (event, f) => { handlers[event] = (handlers[event] ?? []).filter((g) => g !== f); },
    save_changes: () => {
      const { frame, settings, camera, _snapshot, _measurements } = values;
      window.saved.push(JSON.parse(JSON.stringify({ frame, settings, camera, _snapshot, _measurements: _measurements ?? [] })));
    },
    send: (content) => { window.toKernel.push(JSON.parse(JSON.stringify(content))); },
    emit: (event, payload) => { for (const f of handlers[event] ?? []) f(payload); },
  };
  window.model = model;
  module.default.render({ model, el: document.getElementById("host") });
}"""


class Link:
    """A displayed Viewer: the page as its front end."""

    def __init__(self, page: Any, viewer: Any) -> None:
        self.page, self.viewer = page, viewer
        page.set_content('<div id="host"></div>')
        state = viewer.get_state()
        values = {
            k: state[k]
            for k in ("_document", "frame", "settings", "camera", "_snapshot")
        }
        page.evaluate(SETUP, {"source": WIDGET_JS, "values": values})
        self.frame = page.frame_locator("iframe")
        # Paths the page asked Python for (custom messages, see serve).
        self.requests: list[str] = []
        # Custom messages (set_view) go to the page as anywidget sends them.
        viewer.send = lambda message: page.evaluate(
            "m => window.model.emit('msg:custom', m)", message
        )
        self.receive()

    def receive(self) -> None:
        """Wait for the page's next snapshot and apply it to the Viewer."""
        count = self.page.evaluate("window.saved.length")
        self.page.wait_for_function(
            f"window.saved.length > {count}", timeout=5000
        )
        self.page.wait_for_timeout(300)  # and anything else it sends
        self.viewer.set_state(self.page.evaluate("window.saved.at(-1)"))

    def serve(self, done: Any, timeout: float = 30.0) -> None:
        """Answer the page's messages to the kernel, as the Viewer does in
        a notebook, until ``done()``."""
        waited = 0.0
        while True:
            for message in self.page.evaluate("window.toKernel.splice(0)"):
                if message.get("type") == "api":
                    self.requests.append(message["path"])
                self.viewer._on_message(self.viewer, message, [])
            if done():
                return
            assert waited < timeout, "the page did not get there"
            self.page.wait_for_timeout(100)
            waited += 0.1

    def send(self, *keys: str) -> None:
        """Python's changes to the page, as ipywidgets sends them."""
        for key in keys:
            self.page.evaluate(
                "([k, v]) => window.model.set(k, v)",
                [key, getattr(self.viewer, key)],
            )


@needs_anywidget
def test_widget_links_the_view_and_python(page: Any) -> None:
    from stoms.viewer import StaleViewError

    viewer = view(frames(), settings={"tripod": {"axes": "off"}})
    link = Link(page, viewer)
    # The page's normalised settings and its fitted camera came back.
    assert viewer.settings["appearance"]["atomScale"] == 1
    assert viewer.settings["cutoffs"] == {"Pt-Pt": 0}
    assert np.allclose(viewer.camera["R"], np.eye(3))  # top view of a slab
    first = parse_svg(viewer.to_svg())
    assert is_vector(first) and len(spheres(first)) == 12
    # The iframe takes its page's height.
    assert page.locator("iframe").evaluate("f => f.style.height") != "500px"

    # Python -> page: settings.
    viewer.repeat = (2, 1, 1)
    with pytest.raises(StaleViewError):
        viewer.to_svg()
    link.send("settings")
    link.receive()
    assert len(spheres(parse_svg(viewer.to_svg()))) == 24
    assert (
        link.frame.locator("input[aria-label='Repeat a']").input_value() == "2"
    )

    # Python -> page: frame.
    viewer.frame = 2
    link.send("frame")
    link.receive()
    assert link.frame.locator(".frame-number").input_value() == "2"
    assert viewer.to_svg() != ET.tostring(first, encoding="unicode")

    # Python -> page: a view along a (sent as a message).
    viewer.set_view("a")
    link.receive()
    assert np.allclose(viewer.camera["R"][2], [1, 0, 0], atol=1e-9)

    # Page -> Python: dragging turns the view, the frame slider steps.
    before = viewer.camera["R"]
    box = link.frame.locator(".viewer-stage").bounding_box()
    page.mouse.move(box["x"] + 100, box["y"] + 100)
    page.mouse.down()
    page.mouse.move(box["x"] + 160, box["y"] + 130, steps=5)
    page.mouse.up()
    link.receive()
    assert not np.allclose(viewer.camera["R"], before)
    link.frame.locator("button[title^='Previous frame']").click()
    link.receive()
    assert viewer.frame == 1
    assert viewer.selected_atoms.positions[-1, 2] == pytest.approx(
        frames()[1].positions[-1, 2]
    )
    # Every snapshot matches the state it was drawn for.
    assert viewer._snapshot["state"] == {
        "frame": viewer.frame,
        "settings": viewer.settings,
        "camera": viewer.camera,
    }
    assert page.errors == []


@needs_anywidget
def test_settings_of_one_viewer_reproduce_its_figure_in_another(
    page: Any,
) -> None:
    viewer = view(frames()[0], settings={"bonds": True})
    link = Link(page, viewer)
    viewer.set_view("side-a")
    link.receive()
    figure = viewer.to_svg()

    other = view(frames()[0], settings=viewer.get_settings())
    Link(page, other)
    assert other.camera == viewer.camera
    assert other.settings == viewer.settings
    assert other.to_svg() == figure
    assert page.errors == []
    assert math.isfinite(other.camera["scale"])
    json.dumps(other.get_settings())


needs_phonopy = pytest.mark.skipif(
    __import__("importlib").util.find_spec("phonopy") is None,
    reason="phonopy is not installed",
)
INAS = Path(__file__).parent / "data" / "phonopy" / "inas"


@needs_anywidget
@needs_phonopy
def test_phonon_viewer_asks_python_for_modes_bands_and_dos(page: Any) -> None:
    from stoms.viewer import view_phonons

    viewer = view_phonons(
        INAS / "POSCAR", dim="5", force_constants=INAS / "FORCE_CONSTANTS"
    )
    link = Link(page, viewer)
    inner = link.frame
    modes = inner.locator(".mode-list option")
    link.serve(
        lambda: (
            modes.count() == 6
            and inner.locator(".phonon-figure svg").count() == 1
        )
    )
    assert {
        "structures/frame-0/modes",
        "structures/frame-0/phonons/bands",
        "structures/frame-0/phonons/dos",
    } <= set(link.requests)
    at_gamma = modes.all_inner_texts()

    # Another q, typed in: computed by Python, the modes shown are its modes.
    q = inner.get_by_label("q along a*")
    q.fill("0.5")
    q.dispatch_event("change")
    link.serve(lambda: modes.all_inner_texts() != at_gamma)
    assert "structures/frame-0/modes?q=0.5,0,0" in link.requests
    highest = viewer.phonons.modes((0.5, 0.0, 0.0))["frequencies"][-1]
    assert f"{highest:.3f} THz" in modes.all_inner_texts()[-1]

    # NAC off (InAs has Born charges): bands and DOS again, without NAC.
    inner.locator(".phonon-plot-head label.check input").uncheck()
    link.serve(
        lambda: (
            {
                "structures/frame-0/phonons/bands?nac=0",
                "structures/frame-0/phonons/dos?nac=0",
            }
            <= set(link.requests)
        )
    )

    # Playing a mode moves the atoms, and the snapshot follows the drawing.
    inner.get_by_role("button", name="▶ Play").click()
    page.wait_for_timeout(400)
    inner.get_by_role("button", name="❚❚ Pause").click()
    link.receive()
    still = view_phonons(viewer.phonons, settings=viewer.get_settings())
    assert viewer.to_svg() != Link(page, still).viewer.to_svg()

    # What Python cannot answer comes back as the page's error.
    page.frames[-1].evaluate(
        "() => { api('structures/frame-0/rings').catch((e) => { window.failed = e.message; }); }"
    )
    link_page = page.frames[-1]
    link.serve(lambda: bool(link_page.evaluate("window.failed ?? ''")))
    assert "cannot answer" in link_page.evaluate("window.failed")
    assert page.errors == []


def arrow_heads(root: ET.Element) -> list[ET.Element]:
    """Filled triangles: arrow heads (no polyhedra or planes are shown)."""
    return [
        p
        for p in root.iter(f"{SVG}polygon")
        if len(p.get("points", "").split()) == 3
        and p.get("fill") not in (None, "none")
    ]


@needs_anywidget
def test_force_arrows_and_measurements_in_the_notebook(page: Any) -> None:
    from ase.calculators.singlepoint import SinglePointCalculator

    atoms = molecule("H2O")
    atoms.calc = SinglePointCalculator(
        # In the molecule's plane (y-z): the top view looks along x.
        atoms,
        energy=-14.0,
        forces=[[0, 0, 1.0], [0, 0.5, 0], [0, -0.5, 0.3]],
    )
    atoms.arrays["REF_forces"] = np.full((3, 3), 0.2)
    viewer = view(atoms, settings={"tripod": {"axes": "off"}})
    link = Link(page, viewer)
    inner = link.frame
    assert arrow_heads(parse_svg(viewer.to_svg())) == []

    # Force arrows from Python: the calculator forces, one arrow per atom.
    viewer.show_forces = True
    link.send("settings")
    link.receive()
    assert inner.locator("label[title^='Force arrows'] input").is_checked()
    assert len(arrow_heads(parse_svg(viewer.to_svg()))) == 3
    assert viewer.settings["arrows"]["show"] is True
    # Both vector columns can be chosen (⚙ › Arrows).
    inner.get_by_role("button", name="More settings").click()
    options = (
        inner.get_by_label("Arrow vectors").locator("option").all_inner_texts()
    )
    assert options == ["forces (eV/Å)", "REF_forces · arrays"]
    # Auto length: the largest force (1 eV/Å) becomes a 1.5 Å arrow.
    inner.get_by_role(
        "button", name="Largest vector of all frames → 1.5 Å arrow"
    ).click()
    link.receive()
    assert viewer.force_scale == 1.5

    # Measurements: click the two front-most atoms (the last circles drawn).
    viewer.show_forces = False
    link.send("settings")
    link.receive()
    inner.get_by_role(
        "button", name="Measure distances, angles and dihedrals"
    ).click()
    inner.get_by_label("Measure", exact=True).select_option("distance")
    box = inner.locator(".viewer-stage").bounding_box()
    for circle in spheres(parse_svg(viewer.to_svg()))[-2:]:
        page.mouse.click(
            box["x"] + float(circle.get("cx")),
            box["y"] + float(circle.get("cy")),
        )
        page.wait_for_timeout(150)  # two clicks, not a double click
    assert inner.locator(".measure-row").count() == 1, inner.locator(
        ".measure-controls"
    ).inner_text()
    link.receive()
    [measured] = viewer.measurements
    assert measured["kind"] == "distance" and measured["unit"] == "Å"
    assert len(set(measured["atoms"])) == 2
    assert measured["value"] == pytest.approx(
        atoms.get_distance(*measured["atoms"]), abs=1e-6
    )
    assert inner.locator(".measure-row").count() == 1
    # Drawn (dashed, with its value) in the SVG Python saves, and kept in HTML copies.
    text = viewer.to_svg()
    assert (
        'stroke-dasharray="5 4"' in text
        and f"{measured['value']:.3f} Å" in text
    )
    data = json.loads(
        viewer.to_html()
        .split('id="stoms-data">', 1)[1]
        .split("</script>", 1)[0]
    )
    assert [m["kind"] for m in data["measurements"]] == ["distance"]
    # Removed in the viewer: gone in Python too.
    inner.get_by_role("button", name="Remove measurement").click()
    link.receive()
    assert viewer.measurements == []
    assert page.errors == []


def test_saved_html_shows_its_measurements(page: Any, tmp_path: Path) -> None:
    viewer = view(molecule("H2O"), static=True)

    def ref(index: int, symbol: str, image=(0, 0, 0)) -> dict:
        return {
            "index": index,
            "image": list(image),
            "symbol": symbol,
            "count": 3,
        }

    viewer._measurement_items = lambda: [  # type: ignore[method-assign]
        {"kind": "angle", "atoms": [ref(1, "H"), ref(0, "O"), ref(2, "H")]},
        # Other atoms than the frame's: listed without a value, as for frames.
        {"kind": "distance", "atoms": [ref(0, "O"), ref(9, "C")]},
        {"kind": "angle", "atoms": [ref(0, "O")]},  # malformed: dropped
    ]
    open_document(page, viewer, tmp_path)
    page.get_by_role(
        "button", name="Measure distances, angles and dihedrals"
    ).click()
    rows = page.locator(".measure-row")
    assert rows.count() == 2
    angle = molecule("H2O").get_angle(1, 0, 2)
    assert f"{angle:.1f}°" in rows.first.inner_text()
    assert (
        "–" in rows.nth(1).inner_text() and "Å" not in rows.nth(1).inner_text()
    )
    assert page.errors == []


def test_measurements_from_settings_are_drawn_and_exported(
    page: Any, tmp_path: Path
) -> None:
    def atom(index: int, symbol: str) -> dict:
        return {
            "index": index,
            "image": [0, 0, 0],
            "symbol": symbol,
            "count": 3,
        }

    distance = {"kind": "distance", "atoms": [atom(0, "O"), atom(1, "H")]}
    settings = {
        "stoms_viewer_settings": 1,
        "settings": {},
        "measurements": [distance],
    }
    open_document(
        page, view(molecule("H2O"), static=True, settings=settings), tmp_path
    )
    with page.expect_download() as download:
        page.get_by_role(
            "button", name="Save the view as an SVG (vector) image"
        ).click()
    expected = f"{molecule('H2O').get_distance(0, 1):.3f} Å"
    assert expected in Path(download.value.path()).read_text(encoding="utf-8")
    # The viewer's own settings file has them too, and imports them.
    page.get_by_role("button", name="More settings").click()
    with page.expect_download() as download:
        page.get_by_role(
            "button", name="Save these settings and the view to a file"
        ).click()
    exported = json.loads(
        Path(download.value.path()).read_text(encoding="utf-8")
    )
    assert exported["measurements"] == [distance]
    angle = {
        "kind": "angle",
        "atoms": [atom(1, "H"), atom(0, "O"), atom(2, "H")],
    }
    file = tmp_path / "with-angle.json"
    file.write_text(json.dumps({**exported, "measurements": [angle]}))
    page.set_input_files("input[aria-label='Settings file']", file)
    page.get_by_role(
        "button", name="Measure distances, angles and dihedrals"
    ).click()
    rows = page.locator(".measure-row")
    rows.first.wait_for()
    assert rows.count() == 1
    assert (
        f"{molecule('H2O').get_angle(1, 0, 2):.1f}°" in rows.first.inner_text()
    )
    assert page.errors == []


@needs_anywidget
def test_get_settings_reproduces_the_measured_figure(page: Any) -> None:
    from ase.build import fcc111

    first = view(fcc111("Pt", (2, 2, 2), vacuum=5.0))
    link = Link(page, first)
    link.frame.get_by_role(
        "button", name="Measure distances, angles and dihedrals"
    ).click()
    link.frame.get_by_label("Measure", exact=True).select_option("distance")
    box = link.frame.locator(".viewer-stage").bounding_box()
    for circle in spheres(parse_svg(first.to_svg()))[-2:]:
        page.mouse.click(
            box["x"] + float(circle.get("cx")),
            box["y"] + float(circle.get("cy")),
        )
        page.wait_for_timeout(150)
    link.receive()
    [measured] = first.measurements
    figure = first.to_svg()

    # The same structure, relaxed a little: the same view and measurement.
    relaxed = fcc111("Pt", (2, 2, 2), vacuum=5.0)
    relaxed.positions[measured["atoms"][1], 2] += 0.2
    second = view(relaxed, settings=first.get_settings())
    Link(page, second)
    [again] = second.measurements
    assert again["atoms"] == measured["atoms"]
    assert again["value"] == pytest.approx(
        relaxed.get_distance(*measured["atoms"]), abs=1e-6
    )
    assert again["value"] != pytest.approx(measured["value"])
    assert second.camera == first.camera
    assert (
        second.to_svg() != figure
        and 'stroke-dasharray="5 4"' in second.to_svg()
    )
    assert page.errors == []


def sphere_colours(root: ET.Element) -> list[str]:
    """The colour of every drawn atom: the middle stop of its gradient."""
    middle = {
        g.get("id"): next(
            s.get("stop-color") for s in g if s.get("offset") == "0.5"
        )
        for g in root.iter(f"{SVG}radialGradient")
    }
    return [middle[c.get("fill")[5:-1]] for c in spheres(root)]


def charged_water() -> Any:
    from ase.calculators.singlepoint import SinglePointCalculator

    atoms = molecule("H2O")
    atoms.calc = SinglePointCalculator(atoms, charges=[-0.8, 0.4, 0.4])
    return atoms


def saved_svg(page: Any) -> ET.Element:
    with page.expect_download() as download:
        page.get_by_role(
            "button", name="Save the view as an SVG (vector) image"
        ).click()
    return parse_svg(Path(download.value.path()).read_text(encoding="utf-8"))


def test_python_colour_lists_match_the_viewer(
    page: Any, tmp_path: Path
) -> None:
    from stoms.viewer.base import DERIVED, PALETTES

    open_document(page, view(molecule("H2O"), static=True), tmp_path)
    assert tuple(page.evaluate("Object.keys(PALETTES)")) == PALETTES
    derived = page.evaluate("DERIVED_PROPERTIES.map(([name]) => name)")
    assert tuple(n for n in derived if n != "ring") == DERIVED


def test_cell_outline_style(page: Any, tmp_path: Path) -> None:
    from stoms.viewer.base import CELL_STYLES, MAX_CELL_WIDTH

    viewer = view(bulk("Si", "diamond", a=5.43, cubic=True), static=True)
    open_document(page, viewer, tmp_path)
    assert tuple(page.evaluate("Object.keys(CELL_DASHES)")) == CELL_STYLES
    assert page.evaluate("MAX_CELL_WIDTH") == MAX_CELL_WIDTH

    def cell_lines() -> list[ET.Element]:
        # Lines in the cell colour (bonds are off): the 12 cell edges.
        return [
            line
            for line in saved_svg(page).iter(f"{SVG}line")
            if line.get("stroke") in (light_cell, "#ff0000")
        ]

    light_cell = page.evaluate("LIGHT_THEME.cell")
    lines = cell_lines()
    assert len(lines) == 12
    assert all(
        line.get("stroke-width") == "1"
        and line.get("stroke-dasharray") is None
        for line in lines
    )
    viewer.cell_width = 2
    viewer.cell_colour = "#ff0000"
    viewer.cell_style = "dashed"
    open_document(page, viewer, tmp_path)
    lines = cell_lines()
    assert len(lines) == 12
    assert {
        (
            line.get("stroke"),
            line.get("stroke-width"),
            line.get("stroke-dasharray"),
        )
        for line in lines
    } == {("#ff0000", "2", "10 6")}


def test_atoms_are_coloured_by_a_calculator_property(
    page: Any, tmp_path: Path
) -> None:
    viewer = view(charged_water(), static=True)
    viewer.colour_by("charges", palette="diverging", symmetric=True)
    open_document(page, viewer, tmp_path)
    page.locator(".embed-legend .ramp-legend").wait_for()
    # Symmetric around 0: -0.8 e is the low end, 0.4 e three quarters up.
    low = page.evaluate("ramp('property', 0)")
    three_quarters = page.evaluate("ramp('property', 0.75)")
    root = saved_svg(page)
    assert sorted(sphere_colours(root)) == sorted(
        [low, three_quarters, three_quarters]
    )
    labels = page.locator(".embed-legend .ramp-labels").inner_text()
    assert "-0.8 e" in labels and "0.8 e" in labels
    assert page.get_by_label("Colour atoms by").input_value() == "property"
    # Back to element colours from the toolbar.
    page.get_by_label("Colour atoms by").select_option("element")
    page.wait_for_timeout(200)
    assert page.locator(".embed-legend").inner_text() == ""
    assert "#ff0d0d" in sphere_colours(saved_svg(page))  # oxygen red
    assert page.errors == []


def test_categories_share_colours_across_frames(
    page: Any, tmp_path: Path
) -> None:
    from ase.build import fcc111

    slab = fcc111("Pt", (2, 2, 3), vacuum=5.0)  # tags 1, 2, 3 by layer
    viewer = view([slab, slab.copy()], static=True)
    viewer.colour_by("tags")
    open_document(page, viewer, tmp_path)
    page.locator(".category-legend").wait_for()
    assert page.locator(".category-legend span").all_inner_texts() == [
        "1",
        "2",
        "3",
    ]
    expected = {page.evaluate(f"categoryColour({t})") for t in (1, 2, 3)}
    assert set(sphere_colours(saved_svg(page))) == expected
    page.locator("button[title^='Next frame']").click()
    assert set(sphere_colours(saved_svg(page))) == expected
    assert page.errors == []


def test_property_controls_choose_what_colours_the_atoms(
    page: Any, tmp_path: Path
) -> None:
    atoms = charged_water()
    atoms.set_tags([5, 6, 6])
    open_document(page, view(atoms, static=True), tmp_path)
    page.get_by_role("button", name="More settings").click()
    page.get_by_label("Colour mode").select_option("property")
    options = (
        page.get_by_label("Atomic property")
        .locator("option")
        .all_inner_texts()
    )
    assert "charges (calculator)" in options and "tags" in options
    assert (
        "Smallest ring size (ring settings)" not in options
    )  # needs the server
    page.get_by_label("Atomic property").select_option(label="Cartesian z (Å)")
    page.locator(".embed-legend .ramp-legend").wait_for()
    assert "Cartesian z" in page.locator(".embed-legend").inner_text()
    assert page.evaluate("viewerPrefs.property.choice") == {
        "source": "derived",
        "name": "z",
    }
    assert page.errors == []


@needs_anywidget
def test_colouring_is_linked_with_python(page: Any) -> None:
    from ase.calculators.singlepoint import SinglePointCalculator

    frames = []
    for scale in (1.0, 2.0):
        atoms = molecule("H2O")
        atoms.calc = SinglePointCalculator(
            atoms, charges=[-0.8 * scale, 0.4 * scale, 0.4 * scale]
        )
        frames.append(atoms)
    viewer = view(frames)
    link = Link(page, viewer)
    viewer.colour_by("charges", range=(-1.6, 1.6), palette="diverging")
    link.send("settings")
    link.receive()
    assert viewer.settings["colour"] == "property"
    # Frame 0 on the scale of both frames: O at -0.8 of ±1.6 is a quarter up.
    quarter = link.page.frames[-1].evaluate("ramp('property', 0.25)")
    assert quarter in sphere_colours(parse_svg(viewer.to_svg()))
    # Chosen in the viewer: Python sees the choice.
    inner = link.frame
    inner.get_by_role("button", name="More settings").click()
    inner.get_by_label("Atomic property").select_option(label="Atom index")
    link.receive()
    assert viewer.settings["property"]["choice"] == {
        "source": "derived",
        "name": "index",
    }
    viewer.colour_by(None)
    link.send("settings")
    link.receive()
    assert "#ff0d0d" in sphere_colours(parse_svg(viewer.to_svg()))
    assert page.errors == []


def plane_polygons(root: ET.Element, colour: str) -> list[ET.Element]:
    return [p for p in root.iter(f"{SVG}polygon") if p.get("fill") == colour]


def test_structure_settings_from_python_shape_the_drawing(
    page: Any, tmp_path: Path
) -> None:
    from ase.build import fcc111

    slab = fcc111("Pt", (2, 2, 3), vacuum=6.0)
    slab += molecule("O")
    slab.positions[-1] = slab.positions[-2] + [0, 0, 1.9]
    viewer = view(slab, static=True, settings={"tripod": {"axes": "off"}})
    viewer.element_colours = {"O": "#123456"}
    viewer.element_radii = {"Pt": 0.7}
    viewer.add_plane(0, 0, 1, t=0.5, colour="#e34948")
    viewer.show_bonds = True
    viewer.bond_cutoffs = {("O", "Pt"): 2.0}
    open_document(page, viewer, tmp_path)
    root = saved_svg(page)
    assert len(spheres(root)) == 13
    assert "#123456" in sphere_colours(root)
    scale = page.evaluate("sharedView.scale")
    pt_radius = max(float(c.get("r")) for c in spheres(root))
    assert pt_radius == pytest.approx(0.7 * scale, abs=0.02)
    assert len(plane_polygons(root, "#e34948")) == 1
    bonds_with_cutoff = len(root.findall(f".//{SVG}line"))

    # Hidden elements and a slice: only the top Pt layer (c ≥ 0.6) without O.
    viewer.hidden_elements = ["O"]
    viewer.slice = {"c": (0.55, None)}
    viewer.bond_cutoffs = {}
    open_document(page, viewer, tmp_path)
    root = saved_svg(page)
    assert len(spheres(root)) == 4
    assert "#123456" not in sphere_colours(root)
    assert len(root.findall(f".//{SVG}line")) < bonds_with_cutoff
    assert page.errors == []


@needs_anywidget
def test_structure_controls_are_linked_with_python(page: Any) -> None:
    from ase.build import fcc111

    viewer = view(
        fcc111("Pt", (2, 2, 3), vacuum=6.0),
        settings={"tripod": {"axes": "off"}},
    )
    link = Link(page, viewer)
    inner = link.frame
    inner.get_by_role("button", name="More settings").click()
    # Hide Pt in the viewer: Python sees it.
    inner.get_by_label("Show Pt").uncheck()
    link.receive()
    assert viewer.hidden_elements == ["Pt"]
    inner.get_by_role(
        "button", name="Show every element and the whole cell"
    ).click()
    link.receive()
    assert viewer.hidden_elements == []
    # A slice and a plane in the viewer.
    inner.get_by_label("c minimum").fill("0.5")
    inner.get_by_label("c minimum").dispatch_event("change")
    link.receive()
    assert viewer.slice["c"] == (0.5, None)
    inner.get_by_role("button", name="Add plane").click()
    link.receive()
    assert [(p["h"], p["k"], p["l"], p["t"]) for p in viewer.planes] == [
        (0, 0, 1, 0.5)
    ]
    # Its position in Å (t·d; d of (0 0 1) is the cell height) follows t,
    # and t follows it.
    height = viewer.selected_atoms.cell[2, 2]
    distance = inner.get_by_label("Distance from origin (Å)")
    assert float(distance.input_value()) == pytest.approx(height / 2, abs=1e-3)
    distance.fill(f"{height / 4:.6f}")
    distance.dispatch_event("change")
    link.receive()
    assert viewer.planes[0]["t"] == pytest.approx(0.25, abs=1e-6)
    assert float(
        inner.get_by_label("Position t").input_value()
    ) == pytest.approx(0.25, abs=1e-6)
    inner.get_by_label("Position t").fill("0.75")
    inner.get_by_label("Position t").dispatch_event("change")
    link.receive()
    assert viewer.planes[0]["t"] == 0.75
    assert float(distance.input_value()) == pytest.approx(
        0.75 * height, abs=1e-3
    )
    # Plane and polyhedra opacity.
    inner.get_by_label("Plane opacity").fill("0.6")
    link.receive()
    assert viewer.plane_opacity == 0.6
    inner.get_by_label("Polyhedra opacity").fill("0.8")
    link.receive()
    assert viewer.polyhedra_opacity == 0.8
    inner.get_by_label("Bond radius").fill("0.2")
    link.receive()
    assert viewer.bond_radius == 0.2
    inner.get_by_label("Depth fade at the back").fill("0.3")
    link.receive()
    assert viewer.depth_strength == 0.3
    # The cell outline.
    inner.get_by_label("Cell outline width").fill("2.5")
    link.receive()
    assert viewer.cell_width == 2.5
    inner.get_by_label("Cell outline colour").fill("#00ff00")
    link.receive()
    assert viewer.cell_colour == "#00ff00"
    inner.get_by_label("Cell outline style").select_option("dotted")
    link.receive()
    assert viewer.cell_style == "dotted"
    # An element radius and a bond cutoff.
    inner.get_by_label("Pt radius").fill("0.9")
    inner.get_by_label("Pt radius").dispatch_event("change")
    link.receive()
    assert viewer.element_radii == {"Pt": 0.9}
    inner.locator("summary", has_text="Bond cutoffs").click()
    inner.get_by_label("Bond cutoff Pt–Pt").fill("3")
    inner.get_by_label("Bond cutoff Pt–Pt").dispatch_event("change")
    link.receive()
    assert viewer.bond_cutoffs == {"Pt-Pt": 3.0}
    # From Python: the controls show the new settings.
    viewer.clear_planes()
    viewer.add_plane(1, 1, 1, t=1)
    viewer.add_plane(1, 0, 0, t=0.25)
    link.send("settings")
    link.receive()
    assert inner.get_by_role("button", name="Remove plane").count() == 2
    assert inner.get_by_label("h", exact=True).first.input_value() == "1"
    assert page.errors == []
