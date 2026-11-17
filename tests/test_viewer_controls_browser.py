"""Control tags (GUI profiles) in a real browser, on both hosts.

Every control element carries its registry ID (data-control, see CONTROLS in
viewer.js). These tests open the structure page and the notebook viewer with
data that shows nearly every control (a step list, a comparison, rings,
planes, measurements, highlighted atoms, symmetry, phonons, frames with
forces) and check that every tagged element is a registry control and that
every registry control is tagged in at least one host.

Skipped unless the ``browser`` dependency group and Chromium are installed
(see test_viewer_browser.py).
"""

import importlib.util
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from ase.build import fcc111
from web_access_helpers import TEST_TOKEN

from stoms.atomsledger import AtomsLedger
from stoms.viewer import view
from stoms.web import AccessOptions, create_server

pytest.importorskip("playwright.sync_api")

from test_jupyter_viewer_browser import open_document  # noqa: E402
from test_rings import _overlayer  # noqa: E402
from test_viewer_browser import (  # noqa: E402,F401  (fixtures)
    RINGS,
    _open,
    browser,
    rutiles,
    site,
)

INAS = Path(__file__).parent / "data" / "phonopy" / "inas"
HAS_PHONOPY = importlib.util.find_spec("phonopy") is not None
HAS_SPGLIB = importlib.util.find_spec("spglib") is not None

# The IDs tagged on the page now, and those not in the registry.
TAGGED = "[...new Set([...document.querySelectorAll('[data-control]')].map((e) => e.dataset.control))]"
UNKNOWN = "[...document.querySelectorAll('[data-control]')].map((e) => e.dataset.control).filter((id) => !Object.hasOwn(CONTROLS, id))"
REGISTRY = "Object.keys(CONTROLS)"
# An atom reference of the left panel's structure (see measureState).
PICK = """(index) => {
  const s = currentPage.structures[0];
  currentPage.panels[0].onPick({ index, image: [0, 0, 0], symbol: s.symbols[index], count: s.symbols.length });
}"""

# Registry controls that no host shows with the data of these tests:
# Structure info and provenance metadata need a structure with stored info
# or metadata (none of the generated test structures has it).
NOT_IN_FIXTURES = {
    "info.structure-info": "a structure with stored info (atoms.info)",
    "info.provenance": "a structure with provenance metadata",
}


class Tags:
    """The IDs seen on a page over several states, and unknown ones."""

    def __init__(self) -> None:
        self.ids: set[str] = set()
        self.unknown: set[str] = set()

    def collect(self, page: Any) -> None:
        self.ids |= set(page.evaluate(TAGGED))
        self.unknown |= set(page.evaluate(UNKNOWN))


def _context_page(browser: Any) -> tuple[Any, Any, list[str]]:  # noqa: F811
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda m: errors.append(m.text) if m.type == "error" else None,
    )
    return context, page, errors


def _atom_plane() -> dict[str, Any]:
    """A plane through three atoms of the overlayer (structure 0 of `site`)."""
    atoms = _overlayer()
    refs = [
        {
            "index": i,
            "image": [0, 0, 0],
            "symbol": atoms[i].symbol,
            "count": len(atoms),
        }
        for i in (0, 1, 2)
    ]
    return {"atoms": refs, "show": True, "patch": True, "scale": 2}


def _structure_page(
    browser: Any,  # noqa: F811
    site: dict[str, Any],  # noqa: F811
    tags: Tags,
) -> None:
    """The overlayer from its aggregation (a step list), compared with a
    sheet, with rings, planes, measurements and highlighted atoms."""
    context, page, errors = _context_page(browser)
    page.goto(f"{site['base']}/?token={TEST_TOKEN}")
    prefs = {
        "tab": "info",
        "rings": RINGS,
        "planes": [
            {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True, "scale": 2},
            _atom_plane(),
        ],
    }
    _open(page, site, prefs, query=f"&compare={site['ids'][1]}")
    # Built in hidden tabs too: wait until they are there.
    for selector in [
        ".ring-signature code",
        ".related-chips",
        "table.info-facts",
    ]:
        page.wait_for_selector(selector, state="attached")
    tags.collect(page)
    # Measurements: a pending atom shows the click-mode bar, two a distance.
    page.get_by_role("tab", name="Measure").click()
    page.select_option("select[aria-label='Measure']", "distance")
    page.evaluate(PICK, 0)
    tags.collect(page)
    page.evaluate(PICK, 1)
    # Polyhedra: a click on a Cu atom lists its polyhedron.
    copper = page.evaluate("currentPage.structures[0].symbols.indexOf('Cu')")
    page.select_option("select[aria-label='Measure']", "polyhedron")
    page.evaluate(PICK, copper)
    page.wait_for_selector(".polyhedron-entry")
    tags.collect(page)
    # Planes through atoms: picking shows Make plane in the click-mode bar.
    page.select_option("select[aria-label='Measure']", "plane-angle")
    tags.collect(page)
    page.get_by_role("tab", name="Planes").click()
    page.locator(".plane-pick").click()
    tags.collect(page)
    page.locator(".plane-pick").click()
    # Highlighted atoms: select one, apply a colour.
    page.get_by_role("tab", name="Colour").click()
    page.locator("label:has-text('Select atoms by clicking') input").check()
    page.evaluate(PICK, 0)
    page.get_by_role("button", name="Apply colour").click()
    tags.collect(page)
    # The element editor (right-click on an element of the bar).
    page.locator(".element-chip").first.click(button="right")
    page.wait_for_selector(".element-editor")
    tags.collect(page)
    context.close()
    assert errors == []


def _symmetry_page(
    browser: Any,  # noqa: F811
    rutiles: dict[str, Any],  # noqa: F811
    tags: Tags,
) -> None:
    """Rutile on the Info tab: the space group and its inequivalent sites."""
    context, page, errors = _context_page(browser)
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    _open(page, rutiles, {"tab": "info"})
    page.wait_for_selector(
        "details:has-text('Inequivalent sites')", state="attached"
    )
    tags.collect(page)
    context.close()
    assert errors == []


def _phonon_page(browser: Any, tmp_path: Path, tags: Tags) -> None:  # noqa: F811
    """InAs from phonopy: the Vibrations tab and the band structure; at
    q = (0.5, 0, 0) the hint offers a repeat."""
    from stoms.web import load_phonons

    ledger = AtomsLedger(tmp_path / "phonons.ledger")
    _, phonons = load_phonons(
        ledger,
        INAS / "POSCAR",
        dim="5",
        force_constants=INAS / "FORCE_CONSTANTS",
    )
    [structure_id] = phonons
    # Module scope runs before the STOMS_TOKEN fixture: pass the token.
    server = create_server(
        ledger,
        "InAs",
        port=0,
        phonons=phonons,
        access=AccessOptions(token=TEST_TOKEN),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    context, page, errors = _context_page(browser)
    try:
        page.goto(
            f"http://127.0.0.1:{server.server_address[1]}/?token={TEST_TOKEN}"
            f"#/structures/{structure_id}"
        )
        page.wait_for_function(
            "currentPage && currentPage.panels[0].scene"
            " && document.querySelector('.phonon-figure svg')"
        )
        tags.collect(page)
        q = page.get_by_label("q along a*")
        q.fill("0.5")
        q.dispatch_event("change")
        page.wait_for_selector(".repeat-apply", state="attached")
        tags.collect(page)
    finally:
        context.close()
        server.shutdown()
        server.server_close()
    assert errors == []


@pytest.fixture(scope="module")
def structure_page_tags(
    browser: Any,  # noqa: F811
    site: dict[str, Any],  # noqa: F811
    rutiles: dict[str, Any],  # noqa: F811
    tmp_path_factory: pytest.TempPathFactory,
) -> Tags:
    tags = Tags()
    _structure_page(browser, site, tags)
    if HAS_SPGLIB:
        _symmetry_page(browser, rutiles, tags)
    if HAS_PHONOPY:
        _phonon_page(browser, tmp_path_factory.mktemp("phonons"), tags)
    return tags


def _slab_frames() -> list[Any]:
    """Three frames of a Pt slab with calculator forces (a metal: polyhedron
    centres; per-atom vectors and displacements: the arrow controls)."""
    from ase.calculators.singlepoint import SinglePointCalculator

    images = []
    for i in range(3):
        atoms = fcc111("Pt", (2, 2, 2), vacuum=6.0)
        atoms.positions[-1, 2] += 0.3 * i
        forces = np.zeros((len(atoms), 3))
        forces[-1, 2] = 0.5
        atoms.calc = SinglePointCalculator(atoms, energy=-1.0, forces=forces)
        images.append(atoms)
    return images


@pytest.fixture(scope="module")
def notebook_tags(
    browser: Any,  # noqa: F811
    tmp_path_factory: pytest.TempPathFactory,
) -> Tags:
    """The notebook viewer of a trajectory (saved HTML, as in a notebook),
    with its settings box and measure box open."""
    tags = Tags()
    context, page, errors = _context_page(browser)
    viewer = view(_slab_frames(), static=True)
    open_document(page, viewer, tmp_path_factory.mktemp("notebook"))
    page.get_by_role("button", name="More settings").click()
    tags.collect(page)
    context.close()
    assert errors == []
    return tags


def test_structure_page_tags_only_registry_controls(
    structure_page_tags: Tags,
) -> None:
    assert structure_page_tags.unknown == set()
    assert len(structure_page_tags.ids) > 150


def test_notebook_tags_only_registry_controls(notebook_tags: Tags) -> None:
    assert notebook_tags.unknown == set()
    # The notebook's own controls.
    assert {
        "frames.step",
        "frames.slider",
        "frames.number",
        "frames.play",
        "view.along",
        "save.svg",
        "embed.pop-out",
        "embed.measure-toggle",
        "embed.settings-toggle",
        "embed.panel-size",
        "embed.save-html",
        "embed.reset-view",
        "arrows.vectors",
    } <= notebook_tags.ids


@pytest.mark.skipif(
    not (HAS_PHONOPY and HAS_SPGLIB),
    reason="needs phonopy and spglib for the phonon and symmetry controls",
)
def test_every_registry_control_is_tagged_in_a_host(
    browser: Any,  # noqa: F811
    structure_page_tags: Tags,
    notebook_tags: Tags,
) -> None:
    context, page, _ = _context_page(browser)
    page.set_content("<p></p>")
    page.add_script_tag(
        path=str(
            Path(__file__).parents[1]
            / "src"
            / "stoms"
            / "web"
            / "static"
            / "viewer.js"
        )
    )
    registry = set(page.evaluate(REGISTRY))
    context.close()
    tagged = structure_page_tags.ids | notebook_tags.ids
    assert sorted(registry - tagged - set(NOT_IN_FIXTURES)) == []
    # The allow-list holds only controls that are really missing here.
    assert sorted(set(NOT_IN_FIXTURES) & tagged) == []
    assert set(NOT_IN_FIXTURES) <= registry
