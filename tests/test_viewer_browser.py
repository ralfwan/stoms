"""The structure viewer in a real browser (headless Chromium via Playwright).

Skipped unless the ``browser`` dependency group and Chromium are installed:

    uv sync --group dev --group browser
    uv run playwright install chromium
"""

import base64
import importlib.util
import json
import os
import re
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from ase.build import graphene
from web_access_helpers import TEST_TOKEN

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)
from stoms.web import AccessOptions, create_server, load_linked_pages

playwright = pytest.importorskip("playwright.sync_api")

# The Cu-O overlayer of test_rings: 4- and 8-rings of Cu-O pairs.
from test_rings import WINDOWS, _overlayer  # noqa: E402

RINGS = {
    "show": True,
    "elements": {
        s: {"use": True, "zmin": lo, "zmax": hi}
        for s, (lo, hi) in WINDOWS.items()
    },
}


# A 1x1 PNG.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    """Headless Chromium; the tests are skipped when it cannot start."""
    # Playwright's own Node.js driver must not inherit options meant for the
    # user's Node.js (NODE_OPTIONS, e.g. from ~/.bashrc): it rejects some and
    # fails to start.
    saved = os.environ.pop("NODE_OPTIONS", None)
    try:
        manager = playwright.sync_playwright()
        p = manager.start()
    except Exception as error:
        pytest.skip(f"Playwright cannot start: {error}")
    finally:
        if saved is not None:
            os.environ["NODE_OPTIONS"] = saved
    try:
        # STOMS_TEST_CHROMIUM_ARGS adds launch flags, for example
        # --single-process where a sandbox forbids Chromium's helpers.
        args = os.environ.get("STOMS_TEST_CHROMIUM_ARGS", "").split()
        chromium = p.chromium.launch(args=args)
    except Exception as error:  # Chromium not installed
        manager.__exit__(None, None, None)
        pytest.skip(f"Chromium is not available: {error}")
    yield chromium
    chromium.close()
    manager.__exit__(None, None, None)


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """A ledger with three structures in one aggregation: the overlayer (with
    tags and an evaluation with forces and per-atom charges) and two sheets."""
    path = tmp_path_factory.mktemp("viewer") / "viewer.ledger"
    ledger = AtomsLedger(path)
    source = StructureSourceSpec(kind="generated", name="test")
    overlayer = _overlayer()
    overlayer.set_tags(np.where(overlayer.positions[:, 2] < 9, 0, 1))
    sheets = [
        graphene(size=(3, 3, 1), vacuum=5),
        graphene(size=(2, 2, 1), vacuum=5),
    ]
    ids = [
        cast(
            str,
            ledger.add_structure(
                atoms, source, Provenance(created_by="t", purpose="viewer")
            ),
        )
        for atoms in [overlayer, *sheets]
    ]
    count = len(overlayer)
    evaluation = ledger.add_evaluation(
        ids[0],
        method=MethodSpec(method_identifier="pbe", family="DFT", name="VASP"),
        properties={
            "energy": -1.0,
            "forces": np.linspace(-1, 1, 3 * count).reshape(count, 3).tolist(),
            "charges": np.linspace(-1, 1, count).tolist(),
        },
        provenance=Provenance(created_by="t", purpose="label"),
    )
    aggregation = ledger.create_aggregation(
        name="viewer",
        members=[AggregationMemberInput(ids[0], evaluation)]
        + [AggregationMemberInput(i) for i in ids[1:]],
    )
    # Module scope runs before the STOMS_TOKEN fixture: pass the token.
    server = create_server(
        ledger, str(path), port=0, access=AccessOptions(token=TEST_TOKEN)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {
        "base": f"http://127.0.0.1:{server.server_address[1]}",
        "ids": ids,
        "aggregation": aggregation.id,
    }
    server.shutdown()
    server.server_close()


@pytest.fixture
def page(browser: Any, site: dict[str, Any]) -> Iterator[Any]:
    """A fresh browser page; console errors fail the test.

    Playwright's wait_for_function evaluates its predicate with eval, which
    the viewer's Content-Security-Policy forbids, so these pages bypass it;
    test_viewer_runs_under_its_content_security_policy keeps it.
    """
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000},
        accept_downloads=True,
        bypass_csp=True,
    )
    page = context.new_page()
    # Log in once with the token link; the session cookie does the rest.
    page.goto(f"{site['base']}/?token={TEST_TOKEN}")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            message.type == "error" and errors.append(message.text)
        ),
    )
    yield page
    context.close()
    assert errors == []


# Shows every control on the structure page (GUI profile "advanced", kept in
# this browser), for pages not opened with _open.
ADVANCED_PROFILE = "localStorage.setItem('stoms.viewer.profile', 'advanced')"


def _open(
    page: Any,
    site: dict[str, Any],
    prefs: dict[str, Any],
    query: str = "",
    index: int = 0,
    profile: str | None = "advanced",
) -> None:
    """The viewer for structure ``index``, with these viewer settings.

    ``profile`` is the GUI profile stored in the browser: "advanced" shows
    every control (the tests here use them all); None keeps what is stored
    (nothing: the default, simple)."""
    page.goto(f"{site['base']}/")
    page.evaluate(
        "prefs => localStorage.setItem('stoms.viewer', JSON.stringify(prefs))",
        prefs,
    )
    if profile is not None:
        page.evaluate(
            "p => localStorage.setItem('stoms.viewer.profile', p)", profile
        )
    page.goto(
        f"{site['base']}/#/structures/{site['ids'][index]}?from={site['aggregation']}{query}"
    )
    page.reload()
    page.wait_for_function(
        "currentPage && currentPage.panels.every((p) => p.scene)"
    )
    page.wait_for_timeout(300)


def _view_axis(page: Any) -> list[float]:
    return page.evaluate(
        "sharedView.R[2].map((v) => Math.round(v * 1000) / 1000)"
    )


def test_tabs_tripod_and_view_keys(page: Any, site: dict[str, Any]) -> None:
    _open(page, site, {"tab": "style"})
    assert page.locator("#tabpanel-style").is_visible()
    page.get_by_role("tab", name="Info").click()
    assert "Cu" in page.locator("table.info-facts").inner_text()
    page.reload()
    page.wait_for_function("currentPage && currentPage.panels[0].scene")
    assert page.locator(".tab[aria-selected=true]").inner_text() == "Info"
    # Click the tripod's a label (top view: a points right of the origin).
    box = page.locator(".viewer-stage").bounding_box()
    page.mouse.click(box["x"] + 48 + 44, box["y"] + box["height"] - 48)
    page.wait_for_timeout(500)
    assert _view_axis(page) == [1, 0, 0]
    page.keyboard.press("a")  # again: from the other side
    page.wait_for_timeout(500)
    assert _view_axis(page) == [-1, 0, 0]
    page.keyboard.press("t")
    page.wait_for_timeout(500)
    assert _view_axis(page) == [0, 0, 1]


def test_rings_from_the_server_are_drawn_and_summarised(
    page: Any, site: dict[str, Any]
) -> None:
    _open(page, site, {"tab": "rings", "rings": RINGS})
    page.wait_for_selector(".ring-signature code")
    assert (
        page.locator(".ring-signature code").inner_text()
        == "4,4,4,4,8,8,8,8+1Cu"
    )
    assert "Cu-O pairs" in page.locator(".ring-legend").inner_text()
    assert page.evaluate("currentPage.panels[0].scene.rings.length") == 8
    # Counting all atoms doubles the sizes.
    page.select_option("select[aria-label='Ring size counts']", "all")
    page.wait_for_function(
        "document.querySelector('.ring-signature code').textContent.startsWith('8,')"
    )
    page.select_option("select[aria-label='Ring method']", "shortest-path")
    page.wait_for_function(
        "currentPage.panels[0].ringData?.method === 'shortest-path'"
    )


def test_atomic_properties_colour_atoms(
    page: Any, site: dict[str, Any]
) -> None:
    _open(page, site, {"tab": "colour", "colour": "property"})

    def choose(label: str) -> str:
        value = page.eval_on_selector_all(
            "select[aria-label='Atomic property'] option",
            f"options => options.find((o) => o.textContent.split(' (')[0] === {json.dumps(label)}).value",
        )
        page.select_option("select[aria-label='Atomic property']", value)
        page.wait_for_timeout(400)
        return page.locator(".viewer-legend").inner_text()

    assert choose("tags").split("\n")[1:] == ["0", "1"]  # categories
    charges = choose("charges")
    assert charges.startswith("charges (VASP/pbe) per atom")
    assert "-1" in charges
    choose("forces")
    page.select_option("select[aria-label='Vector component']", "z")
    page.wait_for_timeout(300)
    assert page.locator(".viewer-legend").inner_text().startswith("forces_z")


def test_element_bar_hides_and_styles_elements(
    page: Any, site: dict[str, Any]
) -> None:
    _open(page, site, {})
    shown = page.evaluate("currentPage.panels[0].scene.atoms.length")
    page.locator(".element-chip", has_text="O").click()
    assert page.evaluate("viewerPrefs.hiddenElements") == ["O"]
    assert page.evaluate("currentPage.panels[0].scene.atoms.length") < shown
    page.locator(".element-chip", has_text="O").click()
    page.locator(".element-chip", has_text="Cu").click(button="right")
    editor = page.locator(".element-editor")
    editor.locator("input[type=number]").fill("0.9")
    editor.locator("input[type=number]").dispatch_event("change")
    assert page.evaluate("viewerPrefs.appearance.radii") == {"Cu": 0.9}
    page.keyboard.press("Escape")
    assert editor.count() == 0


def test_compare_steps_the_right_panel_and_swaps(
    page: Any, site: dict[str, Any]
) -> None:
    ids = site["ids"]
    _open(page, site, {}, f"&compare={ids[1]}&side=right")
    assert page.evaluate("currentPage.side") == 1
    page.keyboard.press("ArrowRight")
    page.wait_for_function(f"location.hash.includes('compare={ids[2]}')")
    page.wait_for_function(
        "currentPage && currentPage.panels.length === 2 && currentPage.panels[1].scene"
    )
    assert (
        page.evaluate("currentPage.structures[0].id") == ids[0]
    )  # the reference stays
    assert page.evaluate("currentPage.structures[1].id") == ids[2]
    page.get_by_role("button", name="⇄ Swap").click()
    page.wait_for_function(
        f"location.hash.startsWith('#/structures/{ids[2]}')"
    )


def test_wrap_draws_every_atom_inside_the_cell(
    page: Any, site: dict[str, Any]
) -> None:
    # The overlayer has atoms on the far faces of its cell (fraction 1).
    _open(page, site, {"tab": "view", "bonds": True, "rings": RINGS})
    fractions = (
        "(() => { const s = currentPage.structures[0], recip = reciprocal(s.cell);"
        " return currentPage.panels[0].scene.atoms.map((a) => fractional(recip, a.position)); })()"
    )
    before = page.evaluate(fractions)
    assert max(f[0] for f in before) > 1 - 1e-6
    bonds = page.evaluate("currentPage.panels[0].scene.halfBonds.length")
    rings = page.evaluate("currentPage.panels[0].scene.rings.length")
    page.get_by_label("Wrap atoms into cell").check()
    page.wait_for_function("currentPage.panels[0].scene && viewerPrefs.wrap")
    page.wait_for_timeout(300)
    after = page.evaluate(fractions)
    assert len(after) == len(before)
    for f in after:
        assert all(-1e-6 < f[k] < 1 - 1e-9 for k in (0, 1))
    # Along c (not periodic) nothing moves.
    assert [f[2] for f in after] == [f[2] for f in before]
    # The same network: bonds and rings do not depend on where atoms are drawn.
    assert (
        page.evaluate("currentPage.panels[0].scene.halfBonds.length") == bonds
    )
    assert page.evaluate("currentPage.panels[0].scene.rings.length") == rings
    # The stored positions are kept (Info tab, saved files).
    assert page.evaluate(
        "(() => { const s = currentPage.structures[0]; return positionsOf(s) !== s.positions"
        " && s.positions.some((p) => fractional(reciprocal(s.cell), p)[0] > 1 - 1e-6); })()"
    )
    # Repeated copies: each inside its own cell, so the whole repeat is filled.
    page.evaluate(
        "viewerPrefs.repeat = [2, 1, 1]; currentPage.panels[0].rebuild()"
    )
    repeated = page.evaluate(fractions)
    assert len(repeated) == 2 * len(after)
    assert all(-1e-6 < f[0] < 2 - 1e-9 for f in repeated)
    # Kept as a setting.
    page.reload()
    page.wait_for_function("currentPage && currentPage.panels[0].scene")
    assert page.get_by_label("Wrap atoms into cell").is_checked()


@pytest.fixture(scope="module")
def trajectory(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[dict[str, Any]]:
    """Three frames of CuO in one aggregation: Cu crosses the cell face along
    a between frames 1 and 2 (3.9 -> 0.1 -> 0.3 Å), O rises by 0.5 Å."""
    from ase import Atoms

    path = tmp_path_factory.mktemp("trajectory") / "trajectory.ledger"
    ledger = AtomsLedger(path)
    source = StructureSourceSpec(kind="generated", name="test")
    frames = [
        Atoms(
            "CuO",
            positions=[[x, 2.0, 1.0], [2.0, 2.0, z]],
            cell=[4.0, 4.0, 4.0],
            pbc=[True, True, False],
        )
        for x, z in [(3.9, 2.0), (0.1, 2.5), (0.3, 2.5)]
    ]
    ids = [
        cast(
            str,
            ledger.add_structure(
                atoms, source, Provenance(created_by="t", purpose="viewer")
            ),
        )
        for atoms in frames
    ]
    aggregation = ledger.create_aggregation(
        name="trajectory",
        members=[AggregationMemberInput(i) for i in ids],
    )
    server = create_server(
        ledger, str(path), port=0, access=AccessOptions(token=TEST_TOKEN)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {
        "base": f"http://127.0.0.1:{server.server_address[1]}",
        "ids": ids,
        "aggregation": aggregation.id,
    }
    server.shutdown()
    server.server_close()


DISPLACEMENT_ARROWS = {
    "tab": "forces",
    "arrows": {"show": True, "source": "displacement"},
    "displacement": {"reference": "previous", "frame": 0},
}


def test_displacement_arrows_take_the_shortest_image(
    browser: Any, trajectory: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{trajectory['base']}/?token={TEST_TOKEN}")
    _open(page, trajectory, DISPLACEMENT_ARROWS, index=1)
    # The step list loads after the structure; then the arrows come.
    page.wait_for_function("currentPage.displacements?.[0]")
    magnitudes = page.evaluate("currentPage.displacements[0].magnitudes")
    assert magnitudes == pytest.approx([0.2, 0.5])  # not 3.8 Å for Cu
    assert page.evaluate("currentPage.panels[0].scene.arrows.length") == 2
    assert page.locator("select[aria-label='Arrows of']").input_value() == (
        "displacement"
    )
    page.get_by_role("tab", name="Info").click()
    info = page.locator("table.info-displacements").inner_text()
    assert "0.500" in info and "O 1" in info
    assert (
        "previous frame" in page.locator("#tabpanel-info").inner_text().lower()
    )

    # Colour by displacement, from the first frame.
    page.get_by_role("tab", name="Forces").click()
    page.select_option("select[aria-label='Displacement reference']", "first")
    page.get_by_role("tab", name="Colour").click()
    page.select_option("select[aria-label='Colour atoms by']", "property")
    value = page.eval_on_selector_all(
        "select[aria-label='Atomic property'] option",
        "options => options.find((o) => o.textContent.startsWith('Displacement')).value",
    )
    page.select_option("select[aria-label='Atomic property']", value)
    page.wait_for_function(
        "document.querySelector('.viewer-legend').textContent.includes('Δr')"
    )
    assert (
        "from the first frame" in page.locator(".viewer-legend").inner_text()
    )

    # The first frame has no previous one: no arrows, and a note says why.
    page.evaluate(
        "localStorage.setItem('stoms.viewer', JSON.stringify("
        + json.dumps(DISPLACEMENT_ARROWS)
        + "))"
    )
    page.goto(
        f"{trajectory['base']}/#/structures/{trajectory['ids'][0]}?from={trajectory['aggregation']}"
    )
    page.reload()
    page.wait_for_function(
        "document.querySelector('.viewer-status')?.textContent.includes('no previous frame')"
    )
    assert page.evaluate("currentPage.panels[0].scene.arrows.length") == 0
    context.close()
    assert errors == []


def test_displacement_arrows_follow_the_movie_frames(
    browser: Any, trajectory: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    page.goto(f"{trajectory['base']}/?token={TEST_TOKEN}")
    _open(page, trajectory, DISPLACEMENT_ARROWS, index=2)
    page.wait_for_function("currentPage.displacements?.[0]")
    moved = "currentPage.displacements[0].magnitudes"
    assert page.evaluate(moved) == pytest.approx([0.2, 0.0])
    # Scrubbing shows frame 2 in place: its own previous frame is frame 1.
    page.evaluate(
        "(() => { const slider = document.querySelector('.player input[type=range]');"
        " slider.value = 1; slider.dispatchEvent(new Event('input')); })()"
    )
    page.wait_for_function(f"currentPage.movie && {moved}[1] > 0.4")
    assert page.evaluate(moved) == pytest.approx([0.2, 0.5])
    context.close()


def test_positions_on_hover_and_measured_along_the_movie(
    browser: Any, trajectory: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{trajectory['base']}/?token={TEST_TOKEN}")
    _open(page, trajectory, {"tab": "measure"}, index=2)
    # Cu (atom 0) of frame 3 sits at (0.3, 2, 1).
    where = page.evaluate(
        """() => {
          const panel = currentPage.panels[0], stage = panel.stage, box = stage.getBoundingClientRect();
          const atom = panel.scene.atoms.find((a) => a.index === 0 && a.image.every((n) => n === 0));
          const [x, y] = projector(panel.scene, box.width, box.height)(atom.position);
          return [box.left + x, box.top + y];
        }"""
    )
    page.mouse.move(*where)
    tooltip = page.locator(".tooltip")
    assert "(0.300, 2.000, 1.000) Å x, y, z" in tooltip.inner_text()
    # Measured: the value follows the frames of the movie, as a distance does.
    page.select_option("select[aria-label='Measure']", "position")
    page.mouse.click(*where)
    row = page.locator(".measure-row")
    assert (
        row.locator(".measure-value").inner_text() == "(0.300, 2.000, 1.000) Å"
    )
    label = "currentPage.panels[0].scene.marks.map((m) => m.label)"
    assert page.evaluate(label) == ["(0.300, 2.000, 1.000) Å"]
    page.evaluate(
        "(() => { const slider = document.querySelector('.player input[type=range]');"
        " slider.value = 1; slider.dispatchEvent(new Event('input')); })()"
    )
    page.wait_for_function(
        f"currentPage.movie && {label}[0].startsWith('(0.100')"
    )
    assert page.evaluate(label) == ["(0.100, 2.000, 1.000) Å"]
    context.close()
    assert errors == []


def test_displacements_need_the_same_atoms(
    page: Any, site: dict[str, Any]
) -> None:
    ids = site["ids"]
    _open(
        page,
        site,
        {
            **DISPLACEMENT_ARROWS,
            "displacement": {"reference": "compared", "frame": 0},
        },
        f"&compare={ids[2]}&side=right",
        index=1,
    )
    page.wait_for_function(
        "document.querySelector('.viewer-status').textContent.includes('No displacements')"
    )
    assert "atoms" in page.locator(".viewer-status").inner_text()
    assert page.evaluate(
        "currentPage.panels.every((p) => !p.scene.arrows.length)"
    )


def test_cell_outline_width_colour_and_style(
    page: Any, site: dict[str, Any]
) -> None:
    _open(page, site, {"tab": "view"})
    cell_lines = (
        "(() => { const p = currentPage.panels[0];"
        " return displayList(p.scene, 400, 300, LIGHT_THEME, {}).filter((x) => x.kind === 'line')"
        ".slice(0, 12).map((x) => [x.colour, x.width, x.dash ?? null]); })()"
    )
    assert page.evaluate(cell_lines)[0] == ["#6f6e69", 1, None]
    page.get_by_label("Outline width").fill("2")
    page.get_by_label("Cell outline colour").fill("#ff0000")
    page.get_by_label("Cell outline style").select_option("dotted")
    page.wait_for_function(
        "currentPage.panels[0].scene.appearance.cellDash === 'dotted'"
    )
    lines = page.evaluate(cell_lines)
    assert lines == [["#ff0000", 2, [2, 4]]] * 12
    # Kept as settings; Theme goes back to the theme's colour.
    page.reload()
    page.wait_for_function("currentPage && currentPage.panels[0].scene")
    assert page.get_by_label("Cell outline style").input_value() == "dotted"
    assert page.get_by_label("Cell outline colour").input_value() == "#ff0000"
    page.get_by_role("button", name="Theme").first.click()
    assert page.evaluate("viewerPrefs.appearance.cellColour") is None


def test_reset_view_asks_before_removing_measurements(
    page: Any, site: dict[str, Any]
) -> None:
    _open(page, site, {"tab": "view", "repeat": [2, 2, 2], "labels": "index"})
    page.evaluate(
        "measureState.items.push({ kind: 'distance', atoms: [0, 1].map((index) => ({ index, image: [0, 0, 0],"
        " symbol: currentPage.structures[0].symbols[index], count: currentPage.structures[0].symbols.length })) })"
    )
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.keyboard.press("r")
    page.wait_for_timeout(300)
    assert page.evaluate("measureState.items.length") == 1  # declined
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator(".reset-view").click()
    page.wait_for_function(
        "currentPage && currentPage.panels[0].scene && measureState.items.length === 0"
    )
    assert page.evaluate("[viewerPrefs.repeat, viewerPrefs.labels]") == [
        [1, 1, 1],
        "off",
    ]
    # One copy of every atom is drawn again.
    assert page.evaluate(
        "currentPage.panels[0].scene.atoms.length"
        " === currentPage.structures[0].symbols.length"
    )


def test_save_structure_formats_and_add_files(
    page: Any, site: dict[str, Any], tmp_path: Path
) -> None:
    _open(page, site, {"tab": "save"})
    for file_format, suffix in (
        ("vasp", ".vasp"),
        ("cif", ".cif"),
        ("extxyz", ".extxyz"),
    ):
        page.select_option("select[aria-label='File format']", file_format)
        with page.expect_download() as download:
            page.get_by_role("button", name="Save structure").click()
        assert download.value.suggested_filename.endswith(suffix)
    poscar = tmp_path / "POSCAR"
    poscar.write_text(
        "Si\n1.0\n5.43 0 0\n0 5.43 0\n0 0 5.43\nSi\n2\nDirect\n0 0 0\n0.25 0.25 0.25\n"
    )
    page.locator("#add-files-input").set_input_files(str(poscar))
    page.wait_for_function("location.hash.startsWith('#/aggregations/')")
    assert "added" in page.locator("#agg-list").inner_text()


def test_viewer_runs_under_its_content_security_policy(
    browser: Any, site: dict[str, Any]
) -> None:
    # No bypass here: the page runs under the policy the server sends, and
    # waits poll from Python (wait_for_function would need eval).
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, accept_downloads=True
    )
    page = context.new_page()
    # Every control shown (GUI profile "advanced"): the test uses them all.
    page.add_init_script(ADVANCED_PROFILE)
    page.add_init_script(
        "window.violations = [];"
        " document.addEventListener('securitypolicyviolation',"
        " (e) => window.violations.push(e.violatedDirective));"
    )
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            message.type == "error" and errors.append(message.text)
        ),
    )

    def wait(expression: str) -> None:
        for _ in range(100):
            if page.evaluate(expression):
                return
            page.wait_for_timeout(100)
        raise AssertionError(f"timed out waiting for {expression}")

    # The printed link: the token logs in, the redirect drops it, and the
    # browser keeps the fragment, so the structure opens.
    fragment = f"#/structures/{site['ids'][0]}?from={site['aggregation']}"
    response = page.goto(f"{site['base']}/?token={TEST_TOKEN}{fragment}")
    assert page.url == f"{site['base']}/{fragment}"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    wait("typeof currentPage !== 'undefined' && currentPage?.panels[0]?.scene")
    for tab in page.locator(".tab").all_inner_texts():
        page.get_by_role("tab", name=tab).click()
    # Viewer settings (export, import, defaults) sit under View, not Save.
    assert (
        page.locator("#tabpanel-save")
        .get_by_role("button", name="Import", include_hidden=True)
        .count()
        == 0
    )
    page.get_by_role("tab", name="View").click()
    view_panel = page.locator("#tabpanel-view")
    for label in ("Export", "Import", "Restore defaults"):
        assert view_panel.get_by_role("button", name=label).count() == 1
    page.evaluate("viewerPrefs.rings.show = true; savePrefs()")
    page.get_by_role("tab", name="Save").click()
    for label in ("Save SVG", "Save PNG"):
        with page.expect_download():
            page.locator("#tabpanel-save").get_by_role(
                "button", name=label
            ).click()
    assert page.evaluate("window.violations") == []
    context.close()
    assert errors == []


def test_without_the_link_the_viewer_says_how_to_get_in(
    browser: Any, site: dict[str, Any]
) -> None:
    context = browser.new_context()
    try:
        page = context.new_page()
        response = page.goto(f"{site['base']}/")
        assert response.status == 401
        assert "Open the link that was printed" in page.inner_text("body")
    finally:
        context.close()


def test_linked_pages_open_the_viewer_but_show_no_dialogs(
    browser: Any, tmp_path: Path
) -> None:
    # A linked page that tries a dialog and links back to the viewer in a
    # new tab, as the STM pages do.
    ledger = AtomsLedger(tmp_path / "linked.ledger")
    structure_id = cast(
        str,
        ledger.add_structure(
            graphene(size=(2, 2, 1), vacuum=5),
            StructureSourceSpec(kind="generated", name="test"),
            Provenance(created_by="t", purpose="linked"),
        ),
    )
    folder = tmp_path / "page"
    folder.mkdir()
    (folder / "stoms-link.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "name": "stm",
                "title": "STM",
                "structure_ids": [structure_id],
            }
        )
    )
    # Its own files load without the viewer's session cookie, which a
    # sandboxed page's requests never carry.
    (folder / "pixel.png").write_bytes(PIXEL)
    (folder / "index.html").write_text(
        "<!doctype html><script>try { alert('hi'); } catch (e) {}</script>"
        '<img id="pixel" src="pixel.png">'
        f'<a id="back" href="../../#/structures/{structure_id}" target="_blank">open</a>'
    )
    server = create_server(
        ledger, "linked", port=0, linked_pages=load_linked_pages([folder])
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # No CSP bypass: the sandbox arrives in the Content-Security-Policy.
    context = browser.new_context()
    try:
        page = context.new_page()
        dialogs: list[str] = []
        page.on(
            "dialog",
            lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()),
        )
        base = f"http://127.0.0.1:{server.server_address[1]}"
        page.goto(f"{base}/?token={TEST_TOKEN}")
        page.goto(f"{base}/linked/{server.gate.linked_key}/stm/")
        page.wait_for_timeout(300)
        assert dialogs == []
        assert (
            page.evaluate("document.getElementById('pixel').naturalWidth") == 1
        )
        with context.expect_page() as opened:
            page.locator("#back").click()
        viewer = opened.value
        for _ in range(100):  # wait_for_function would need eval
            if viewer.evaluate(
                "typeof currentPage !== 'undefined'"
                " && Boolean(currentPage?.panels[0]?.scene)"
            ):
                break
            viewer.wait_for_timeout(100)
        else:
            raise AssertionError(
                "the viewer opened from the page shows nothing"
            )
        assert viewer.evaluate("self.origin") != "null"
    finally:
        context.close()
        server.shutdown()
        server.server_close()


def test_phonon_plot_layout_resize_and_save_buttons(
    browser: Any, tmp_path: Path
) -> None:
    pytest.importorskip("phonopy")
    from stoms.web import load_phonons

    inas = Path(__file__).parent / "data" / "phonopy" / "inas"
    ledger = AtomsLedger(tmp_path / "phonons.ledger")
    _, phonons = load_phonons(
        ledger,
        inas / "POSCAR",
        dim="5",
        force_constants=inas / "FORCE_CONSTANTS",
    )
    [structure_id] = phonons
    server = create_server(ledger, "InAs", port=0, phonons=phonons)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000}, bypass_csp=True
    )
    try:
        page = context.new_page()
        # The whole Vibrations tab (GUI profile "advanced"), as tall as the
        # structure.
        page.add_init_script(ADVANCED_PROFILE)
        page.goto(
            f"http://127.0.0.1:{server.server_address[1]}/?token={TEST_TOKEN}"
            f"#/structures/{structure_id}"
        )
        ready = (
            "currentPage && currentPage.panels[0].scene"
            " && document.querySelector('.phonon-figure svg')"
        )
        page.wait_for_function(ready)
        # The fitted view centres the atoms and the cell outline together;
        # InAs's two atoms sit at one end of the cell, so centring on the atoms
        # pushed the outline off the panel.
        offset = page.evaluate(
            """() => {
              const panel = currentPage.panels[0], scene = panel.scene;
              const stage = document.querySelector('.viewer-stage');
              const project = projector(scene, stage.clientWidth, stage.clientHeight);
              const points = [...scene.atoms.map((a) => a.position), ...scene.cellEdges.flat()].map(project);
              const mid = (k) => (Math.min(...points.map((p) => p[k])) + Math.max(...points.map((p) => p[k]))) / 2;
              return [mid(0) - stage.clientWidth / 2, mid(1) - stage.clientHeight / 2];
            }"""
        )
        assert abs(offset[0]) < 1 and abs(offset[1]) < 1
        height = "(selector) => document.querySelector(selector).offsetHeight"
        # The settings end with the structure, not with the plot below it.
        assert page.evaluate(height, ".viewer-controls") == page.evaluate(
            height, ".viewer-main"
        )
        footer = page.locator(".viewer-footer .footer-actions")
        assert footer.locator("button").all_inner_texts() == [
            "Save SVG",
            "⟲ Clear all",
        ]
        assert page.locator(
            ".phonon-plot-actions button"
        ).all_inner_texts() == [
            "Beside the structure",
            "Save bands & DOS (SVG)",
        ]
        # The plot's grip resizes it, and the size is kept.
        grip = page.locator(".phonon-plot .resize-grip")
        grip.scroll_into_view_if_needed()
        box = grip.bounding_box()
        page.mouse.move(box["x"] + 8, box["y"] + 8)
        page.mouse.down()
        page.mouse.move(box["x"] + 8, box["y"] + 108, steps=5)
        page.mouse.up()
        assert page.evaluate("viewerPrefs.vibration.plotHeight") == 400
        assert page.evaluate(height, ".phonon-figure") == 400
        # Beside the structure, also after a reload.
        page.get_by_role("button", name="Beside the structure").click()
        page.reload()
        page.wait_for_function(ready)
        assert page.evaluate(
            "document.querySelector('.viewer-figures').classList.contains('side')"
        )
        assert page.evaluate(height, ".phonon-figure") == 400
    finally:
        context.close()
        server.shutdown()
        server.server_close()


def test_wave_vector_and_group_velocity_on_the_axes(
    browser: Any, tmp_path: Path
) -> None:
    pytest.importorskip("phonopy")
    from stoms.web import load_phonons

    inas = Path(__file__).parent / "data" / "phonopy" / "inas"
    ledger = AtomsLedger(tmp_path / "phonons.ledger")
    _, phonons = load_phonons(
        ledger,
        inas / "POSCAR",
        dim="5",
        force_constants=inas / "FORCE_CONSTANTS",
    )
    [structure_id] = phonons
    server = create_server(ledger, "InAs", port=0, phonons=phonons)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    context = browser.new_context(
        viewport={"width": 1400, "height": 900}, bypass_csp=True
    )
    try:
        page = context.new_page()
        page.add_init_script(ADVANCED_PROFILE)
        page.goto(
            f"http://127.0.0.1:{server.server_address[1]}/?token={TEST_TOKEN}"
            f"#/structures/{structure_id}"
        )
        page.wait_for_function("currentPage && currentPage.panels[0].scene")
        box = "[data-control='vibration.wave-vector'] input"
        info = "document.querySelector('[data-control=\"vibration.wave-vector\"]').nextElementSibling.textContent"
        state = """() => ({ axes: viewerPrefs.tripod.axes, on: viewerPrefs.vibration.waveVector,
            select: document.querySelector('select[aria-label="Axes"]').value,
            wave: currentPage.panels[0].scene.wave })"""
        assert page.evaluate(state)["wave"] is None
        # Ticked at Γ: the Cartesian axes, but nothing to draw.
        page.evaluate(f"document.querySelector({box!r}).click()")
        at_gamma = page.evaluate(state)
        assert at_gamma["axes"] == at_gamma["select"] == "xyz"
        assert at_gamma["wave"]["q"] is None and at_gamma["wave"]["vg"] is None
        assert "q = Γ" in page.evaluate(info)
        # Beyond X (fcc): reduced to the shorter equivalent q in the zone.
        page.evaluate(
            """() => {
              const inputs = [...document.querySelectorAll('input[aria-label^="q along"]')];
              [0.6, 0.6, 0].forEach((x, k) => { inputs[k].value = String(x); });
              inputs[2].dispatchEvent(new Event('change'));
            }"""
        )
        page.wait_for_function(f"{info}.includes('q = (-0.4, -0.4, 0)')")
        # q alone, no note on its scale.
        legend = page.evaluate(info)
        assert "scale" not in legend and "% of that" not in legend
        assert "Å⁻¹" not in legend
        wave = page.evaluate(state)["wave"]
        extent = page.evaluate(
            "zoneExtent(currentPage.panels[0].structure.cell)"
        )
        k = page.evaluate(
            "firstZonePoint(currentPage.panels[0].structure.cell, [0.6, 0.6, 0]).cartesian"
        )
        assert wave["q"] == pytest.approx([x / extent for x in k])
        assert np.linalg.norm(wave["vg"]) == pytest.approx(1)
        # The served v_g of the shown mode, as a direction.
        mode = int(page.locator("select.mode-list").input_value())
        modes = phonons[structure_id].modes((-0.4, -0.4, 0.0))
        served = np.array(modes["group_velocities"][mode])
        assert wave["vg"] == pytest.approx(
            served / np.linalg.norm(served), abs=1e-5
        )
        arrows = page.evaluate(
            """() => {
              const stage = document.querySelector('.viewer-stage');
              return displayList(currentPage.panels[0].scene, stage.clientWidth, stage.clientHeight, themeColours(stage))
                .filter((p) => p.kind === 'label' && ['q', 'v'].includes(p.text)).map((p) => p.text + (p.sub ? '_' + p.sub : ''));
            }"""
        )
        assert sorted(arrows) == ["q", "v_g"]
        # Other axes switch it off.
        page.get_by_role("tab", name="View").click()
        page.select_option("select[aria-label='Axes']", "abc")
        after = page.evaluate(state)
        assert not after["on"] and after["wave"] is None
        assert not page.locator(box).is_checked()
    finally:
        context.close()
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def rutiles(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[dict[str, Any]]:
    """Rutile TiO2, a distorted rutile (same atoms) and a TiO2 cell missing
    one O, in one aggregation."""
    from test_polyhedra import rutile

    path = tmp_path_factory.mktemp("rutile") / "rutile.ledger"
    ledger = AtomsLedger(path)
    source = StructureSourceSpec(kind="generated", name="test")
    other = rutile()
    del other[5]
    structures = [rutile(), rutile(x=0.31), other]
    ids = [
        cast(
            str,
            ledger.add_structure(
                atoms, source, Provenance(created_by="t", purpose="viewer")
            ),
        )
        for atoms in structures
    ]
    aggregation = ledger.create_aggregation(
        name="rutile", members=[AggregationMemberInput(i) for i in ids]
    )
    server = create_server(
        ledger, str(path), port=0, access=AccessOptions(token=TEST_TOKEN)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {
        "base": f"http://127.0.0.1:{server.server_address[1]}",
        "ids": ids,
        "aggregation": aggregation.id,
        "structures": structures,
    }
    server.shutdown()
    server.server_close()


POLYHEDRON_CELLS = """() => Object.fromEntries([...document.querySelectorAll('.polyhedron-entry tr[data-field]')]
  .map((row) => [row.dataset.field, [...row.querySelectorAll('td')].map((td) => td.textContent)]))"""


def _polyhedron_texts(atoms: Any, index: int) -> dict[str, str]:
    """What the Measure tab shows for stoms.analysis.polyhedron."""
    from stoms.analysis import polyhedron

    p = polyhedron(atoms, index)
    return {
        "cn": str(p["cn"]),
        "ligands": " ".join(
            f"{lig['symbol']}{lig['index']}" for lig in p["ligands"]
        ),
        "lengths": " ".join(f"{v:.4f}" for v in p["lengths"]),
        "mean": f"{p['mean']:.4f}",
        "volume": f"{p['volume']:.4f}",
        "distortion": f"{p['distortion_index']:.5f}",
        "quadraticElongation": f"{p['quadratic_elongation']:.5f}",
        "angleVariance": f"{p['bond_angle_variance']:.4f}",
        "econ": f"{p['econ']:.4f}",
    }


def _shown(page: Any) -> list[Any]:
    """The structures of the panels, as the page received them (the ledger
    stores positions at its own precision)."""
    from ase import Atoms

    return [
        Atoms(
            s["symbols"],
            positions=s["positions"],
            cell=s["cell"],
            pbc=s["pbc"],
        )
        for s in page.evaluate(
            "currentPage.structures.map(({ symbols, positions, cell, pbc }) => ({ symbols, positions, cell, pbc }))"
        )
    ]


def test_polyhedra_match_python_and_follow_frames(
    browser: Any, rutiles: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            message.type == "error" and errors.append(message.text)
        ),
    )
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    ids = rutiles["ids"]
    _open(page, rutiles, {"tab": "measure"}, f"&compare={ids[1]}")
    page.select_option("select[aria-label='Measure']", "polyhedron")
    assert "polyhedron" in page.locator(".click-mode").inner_text()
    # A click on Ti 1 (the panels' pick handler, as a click on the atom).
    page.evaluate(
        "currentPage.panels[0].onPick({ index: 1, image: [0, 0, 0], symbol: 'Ti', count: 6 })"
    )
    page.wait_for_selector(".polyhedron-entry")
    # Both panels have the same atoms: a column each, as Python computes.
    cells = page.evaluate(POLYHEDRON_CELLS)
    left, right = (_polyhedron_texts(s, 1) for s in _shown(page))
    assert cells == {key: [left[key], right[key]] for key in left}
    heading = page.locator("#tabpanel-measure").inner_text().lower()
    assert "polyhedra" in heading
    # Copy as CSV: one row per structure.
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.get_by_role("button", name="Copy as CSV").click()
    csv = page.evaluate("navigator.clipboard.readText()")
    rows = csv.strip().split("\n")
    assert len(rows) == 3 and rows[1].startswith(f"{ids[0]},Ti1,6,")

    # Without the comparison, step through the frames: the entry follows
    # them, and is left out (with a note) on the structure with other atoms.
    # (In-page navigation: a reload would forget the entries, as it forgets
    # measurements.)
    page.evaluate(
        "hash => { location.hash = hash; }",
        f"#/structures/{ids[0]}?from={rutiles['aggregation']}",
    )
    page.wait_for_function(
        "currentPage && currentPage.structures.length === 1"
        " && currentPage.panels.every((p) => p.scene)"
    )
    page.wait_for_selector(".polyhedron-entry")
    assert page.evaluate(POLYHEDRON_CELLS)["mean"] == [left["mean"]]
    page.wait_for_function(
        "document.querySelector('.player input[type=range]')"
    )

    def scrub(value: int) -> None:
        page.evaluate(
            "(value) => { const slider = document.querySelector('.player input[type=range]');"
            " slider.value = value; slider.dispatchEvent(new Event('input')); }",
            value,
        )

    scrub(1)
    page.wait_for_function(
        f"document.querySelector('.polyhedron-entry tr[data-field=mean] td')?.textContent === '{right['mean']}'"
    )
    [frame] = _shown(page)
    assert page.evaluate(POLYHEDRON_CELLS) == {
        k: [v] for k, v in _polyhedron_texts(frame, 1).items()
    }
    scrub(2)
    page.wait_for_selector(".polyhedra-hidden")
    assert page.locator(".polyhedron-entry").count() == 0
    assert (
        "atoms of this structure differ"
        in page.locator(".polyhedra-hidden").inner_text()
    )
    scrub(0)
    page.wait_for_selector(".polyhedron-entry")
    context.close()
    assert errors == []


needs_spglib = pytest.mark.skipif(
    importlib.util.find_spec("spglib") is None,
    reason="needs spglib (the symmetry extra)",
)

# Moves the mouse onto atom `index` of the left panel (its front-most copy).
HOVER_ATOM = """(index) => {
  const panel = currentPage.panels[0];
  const box = panel.stage.getBoundingClientRect();
  const project = projector(panel.scene, box.width, box.height);
  const [x, y] = panel.scene.atoms.filter((a) => a.index === index).map((a) => project(a.position))
    .sort((p, q) => q[2] - p[2])[0];
  return [box.left + x, box.top + y];
}"""


def _hover_text(page: Any, index: int) -> str:
    x, y = page.evaluate(HOVER_ATOM, index)
    page.mouse.move(x, y)
    page.wait_for_selector(".tooltip", state="visible")
    return page.locator(".tooltip").inner_text()


def _console_page(browser: Any, site: dict[str, Any]) -> tuple[Any, list]:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            message.type == "error" and errors.append(message.text)
        ),
    )
    page.goto(f"{site['base']}/?token={TEST_TOKEN}")
    return page, errors


@needs_spglib
def test_symmetry_in_info_tooltips_and_colours(
    browser: Any, rutiles: dict[str, Any]
) -> None:
    page, errors = _console_page(browser, rutiles)
    _open(page, rutiles, {"tab": "info"})
    page.wait_for_function(
        "document.querySelector('.space-group')?.textContent.includes('136')"
    )
    facts = page.locator("table.info-facts").inner_text()
    assert "P4_2/mnm (136)" in facts and "tetragonal" in facts
    assert page.locator(".symmetry-hint").count() == 0
    summary = page.locator(".info-extras summary, #tabpanel-info summary")
    assert "Inequivalent sites (2)" in summary.all_inner_texts()
    # Hovering an atom shows its Wyckoff letter and site symmetry.
    text = _hover_text(page, 1)
    assert "Wyckoff letter" in text and "m.mm" in text
    assert "m.2m" in _hover_text(page, 2)
    # Another tolerance: computed again by the server.
    tolerance = page.get_by_label("Symmetry tolerance")
    assert tolerance.input_value() == "0.01"
    tolerance.fill("0.2")
    tolerance.dispatch_event("change")
    page.wait_for_function(
        "viewerPrefs.symmetry.tolerance === 0.2"
        " && symmetryResolved.has(`${currentPage.structures[0].id}|0.2`)"
    )
    page.wait_for_function(
        "document.querySelector('.space-group')?.textContent.includes('136')"
    )
    page.evaluate(
        "() => { viewerPrefs.symmetry.tolerance = 0.01; savePrefs(); }"
    )

    # Colour by equivalent site: categories, one per inequivalent site.
    _open(
        page,
        rutiles,
        {
            "tab": "colour",
            "colour": "property",
            "property": {
                "choice": {"source": "derived", "name": "equivalent"}
            },
        },
    )
    page.wait_for_selector(".category-legend")
    legend = page.locator(".category-legend").inner_text()
    assert "Ti1 (a)" in legend and "O1 (f)" in legend
    colours = page.evaluate(
        "currentPage.panels[0].scene.atoms.map((a) => a.colour)"
    )
    assert len(set(colours)) == 2
    options = page.locator(
        "select[aria-label='Atomic property'] option"
    ).all_inner_texts()
    assert "Equivalent site (symmetry)" in options
    assert "Equivalent site" in _hover_text(page, 0)
    page.context.close()
    assert errors == []


@needs_spglib
def test_slabs_have_no_space_group(page: Any, site: dict[str, Any]) -> None:
    # A graphene sheet: not periodic along c.
    _open(page, site, {"tab": "info"}, index=1)
    page.wait_for_function(
        "document.querySelector('.space-group')?.textContent === 'not applicable'"
    )
    assert (
        "not periodic along c" in page.locator(".symmetry-note").inner_text()
    )


def test_without_spglib_the_info_tab_names_the_extra(
    browser: Any,
    rutiles: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The server's environment has no spglib.
    monkeypatch.setitem(sys.modules, "spglib", None)
    page, errors = _console_page(browser, rutiles)
    _open(page, rutiles, {"tab": "info"})
    page.wait_for_selector(".symmetry-hint")
    hint = page.locator(".symmetry-hint").inner_text()
    assert 'pip install "stoms[symmetry]"' in hint
    assert "stoms[symmetry]" in hint
    # The other rows are unchanged; no space group, tolerance or Wyckoff.
    facts = page.locator("table.info-facts").inner_text()
    assert "Space group" not in facts and "Formula" in facts
    assert page.get_by_label("Symmetry tolerance").count() == 0
    assert "Wyckoff" not in _hover_text(page, 1)
    # Equivalent sites are not offered as a colouring.
    _open(page, rutiles, {"tab": "colour", "colour": "property"})
    options = page.locator(
        "select[aria-label='Atomic property'] option"
    ).all_inner_texts()
    assert options and not any("Equivalent site" in o for o in options)
    page.context.close()
    assert errors == []


def test_bond_search_options_on_the_structure_page(
    browser: Any, rutiles: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            message.type == "error" and errors.append(message.text)
        ),
    )
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    # Rutile sliced to c in [0, 0.25]: Ti0's octahedron is cut.
    _open(
        page,
        rutiles,
        {
            "tab": "style",
            "bonds": True,
            "polyhedra": True,
            "slice": [[None, None], [None, None], [0, 0.25]],
        },
    )
    scene = "currentPage.panels[0].scene"
    assert page.evaluate(f"{scene}.extraAtoms") == 0
    page.locator("summary", has_text="Bond search").click()
    page.get_by_label("Bonded atoms outside").select_option("ligands")
    page.wait_for_function(f"{scene}.extraAtoms === 5")
    assert page.evaluate(
        f"{scene}.atoms.filter((a) => a.extra).every((a) => currentPage.structures[0].symbols[a.index] === 'O')"
    )
    # Not counted as shown: the slice line says so.
    assert "(and 5 bonded outside)" in page.evaluate(
        "document.body.textContent"
    )
    page.get_by_label("Bonded atoms outside").select_option("partners")
    page.wait_for_function(f"{scene}.extraAtoms > 5")
    # A minimum length: the four short Ti-O bonds (1.95 Å) go, and with
    # them the octahedra (fewer than 4 ligands).
    page.get_by_text("Bond cutoffs", exact=True).click()
    shortest = page.get_by_label("Shortest bond O–Ti")
    shortest.fill("1.96")
    shortest.dispatch_event("change")
    page.wait_for_function(f"{scene}.polyhedra.length === 0")
    assert page.evaluate("viewerPrefs.bondMinimums") == {"O-Ti": 1.96}
    # Hydrogen bonds: the checkbox sets the setting (no H here: none drawn).
    page.get_by_label("Hydrogen bonds", exact=True).check()
    assert page.evaluate("viewerPrefs.hbonds.show") is True
    assert page.evaluate(f"{scene}.hbonds.length") == 0
    assert errors == []
    context.close()


# ---------------------------------------------------------------- drawing styles

# The display list of panel 0 painted on a canvas that counts its calls, and
# the SVG of the same panel: sprites (shaded spheres), discs (dots) and line
# segments of both.
_PAINT_AND_SVG = """(() => {
  const panel = currentPage.panels[0], w = panel.stage.clientWidth, h = panel.stage.clientHeight;
  const list = displayList(panel.scene, w, h, LIGHT_THEME, { tripod: false });
  const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  const calls = { drawImage: 0, arc: 0, lineTo: 0 };
  for (const name of Object.keys(calls)) {
    const call = ctx[name].bind(ctx);
    ctx[name] = (...args) => { calls[name] += 1; return call(...args); };
  }
  paintCanvas(ctx, list, 1, { hairlines: true });
  const kinds = {};
  for (const p of list) kinds[p.kind] = (kinds[p.kind] ?? 0) + 1;
  return { calls, kinds, svg: panelsToSvg([panel], { transparent: true, tripod: false }) };
})()"""


@pytest.mark.parametrize(
    "style", ["ball-and-stick", "space-filling", "stick", "wireframe"]
)
def test_styles_paint_the_same_shapes_on_canvas_and_in_svg(
    page: Any, site: dict[str, Any], style: str
) -> None:
    # O has a radius of its own: a sphere in every style but space-filling,
    # also in wireframe.
    _open(
        page,
        site,
        {"style": style, "bonds": True, "appearance": {"radii": {"O": 0.5}}},
    )
    drawn = page.evaluate(_PAINT_AND_SVG)
    svg = drawn["svg"]
    shaded = svg.count('fill="url(#sphere')
    flat = len(re.findall(r'<circle [^>]*fill="#[0-9a-f]{6}"/>', svg))
    assert drawn["calls"]["drawImage"] == shaded > 0
    assert drawn["calls"]["arc"] == flat == drawn["kinds"].get("dot", 0)
    assert drawn["calls"]["lineTo"] == svg.count("<line ")
    if style == "space-filling":
        assert svg.count("<line ") == 12  # the cell only
    if style == "wireframe":
        assert drawn["kinds"]["lines"] >= 1
        assert "sphere" in drawn["kinds"]  # the O


def test_model_and_radius_type_controls(
    page: Any, site: dict[str, Any]
) -> None:
    _open(page, site, {"tab": "style", "bonds": True})
    panel = page.locator("#tabpanel-style")
    bonds = panel.get_by_role("checkbox", name="Bonds", exact=True)
    radius_type = page.get_by_label("Radius type")
    assert page.get_by_label("Model").input_value() == "ball-and-stick"
    assert not bonds.is_disabled()

    page.get_by_label("Model").select_option("space-filling")
    page.wait_for_function(
        "currentPage.panels[0].scene.style === 'space-filling'"
    )
    assert page.evaluate("currentPage.panels[0].scene.halfBonds.length") == 0
    assert bonds.is_disabled()
    radius_type.select_option("vdw")
    page.wait_for_function("viewerPrefs.radiusType === 'vdw'")
    # Cu at its van der Waals radius (Alvarez: 2.38 Å); the Cu radius
    # field shows it as its automatic value.
    radii = page.evaluate(
        "(() => { const s = currentPage.structures[0];"
        " return currentPage.panels[0].scene.atoms.filter((a) => s.symbols[a.index] === 'Cu').map((a) => a.radius); })()"
    )
    assert radii and all(r == pytest.approx(2.38) for r in radii)
    assert (
        page.get_by_label("Cu radius").get_attribute("placeholder") == "2.38"
    )

    page.get_by_label("Model").select_option("wireframe")
    page.wait_for_function("currentPage.panels[0].scene.style === 'wireframe'")
    assert page.evaluate("currentPage.panels[0].scene.halfBonds.length") > 0
    assert radius_type.is_disabled()
    assert bonds.is_disabled()
    # Saved with the settings.
    page.reload()
    page.wait_for_function("currentPage && currentPage.panels[0].scene")
    assert page.get_by_label("Model").input_value() == "wireframe"
    assert page.get_by_label("Radius type").input_value() == "vdw"


def test_size_controls_lock_where_unused(
    page: Any, site: dict[str, Any]
) -> None:
    # A size factor and a Cu radius of its own: both apply to ball and stick
    # only; space-filling draws the table radius, stick and wireframe atoms
    # the bond radius. The stored values are kept.
    _open(
        page,
        site,
        {
            "tab": "style",
            "appearance": {"atomScale": 1.4, "radii": {"Cu": 0.5}},
        },
    )
    panel = page.locator("#tabpanel-style")
    size = panel.get_by_label("Atom size (automatic radii)")
    size_field = panel.locator('[data-setting="atomScale"]')
    cu_radius = panel.get_by_label("Cu radius")
    cu_radii = (
        "(() => { const s = currentPage.structures[0];"
        " return [...new Set(currentPage.panels[0].scene.atoms"
        ".filter((a) => s.symbols[a.index] === 'Cu').map((a) => a.radius))]; })()"
    )
    assert not size.is_disabled() and not cu_radius.is_disabled()
    assert page.evaluate(cu_radii) == [pytest.approx(0.5)]

    page.get_by_label("Model").select_option("space-filling")
    page.wait_for_function(
        "currentPage.panels[0].scene.style === 'space-filling'"
    )
    assert size.is_disabled() and cu_radius.is_disabled()
    assert (
        size_field.get_attribute("title")
        == "Space-filling uses the true radii"
    )
    assert (
        cu_radius.get_attribute("title") == "Space-filling uses the true radii"
    )
    # Cu at its covalent radius (Cordero: 1.32 Å), not 0.5 Å or × 1.4.
    assert page.evaluate(cu_radii) == [pytest.approx(1.32)]
    # The structure page's element editor locks its radius field too.
    page.locator(".element-chip", has_text="Cu").click(button="right")
    editor_radius = page.locator(".element-editor").get_by_label("Cu radius")
    assert editor_radius.is_disabled()
    page.evaluate("currentPage.closeEditor()")
    # Reset appearance keeps the lock on the new slider.
    panel.get_by_role("button", name="Reset appearance").click()
    assert panel.get_by_label("Atom size (automatic radii)").is_disabled()
    page.evaluate(
        "viewerPrefs.appearance.atomScale = 1.4,"
        " viewerPrefs.appearance.radii = { Cu: 0.5 }, savePrefs()"
    )

    for style in ("stick", "wireframe"):
        page.get_by_label("Model").select_option(style)
        page.wait_for_function(
            f"currentPage.panels[0].scene.style === '{style}'"
        )
        assert panel.get_by_label("Atom size (automatic radii)").is_disabled()
        assert (
            panel.locator('[data-setting="atomScale"]').get_attribute("title")
            == "Stick and wireframe atoms take the bond radius"
        )
        assert not cu_radius.is_disabled()

    page.get_by_label("Model").select_option("ball-and-stick")
    page.wait_for_function(
        "currentPage.panels[0].scene.style === 'ball-and-stick'"
    )
    assert not panel.get_by_label("Atom size (automatic radii)").is_disabled()
    assert not cu_radius.is_disabled()
    assert page.evaluate(cu_radii) == [pytest.approx(0.5)]
    assert page.evaluate("viewerPrefs.appearance.atomScale") == 1.4


def test_transformation_matrix_on_the_structure_page(
    page: Any, site: dict[str, Any], tmp_path: Path
) -> None:
    # A graphene sheet (18 atoms, γ = 120°).
    _open(page, site, {"tab": "view"}, index=1)
    panel = page.locator("#tabpanel-view")
    total = "currentPage.panels[0].scene.totalAtoms"
    assert page.evaluate(total) == 18
    panel.get_by_role("checkbox", name="Transformation matrix").check()
    # It starts from the repeat (here 1 × 1 × 1) and replaces it.
    assert page.evaluate("viewerPrefs.repeatMatrix") == [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
    ]
    assert page.get_by_label("Matrix row 1 column 1").input_value() == "1"
    page.get_by_label("Matrix preset").select_option(label="(√3×√3)R30°")
    page.wait_for_function(f"{total} === 54")
    assert page.evaluate("viewerPrefs.repeatMatrix") == [
        [2, 1, 0],
        [-1, 1, 0],
        [0, 0, 1],
    ]
    assert page.evaluate("currentPage.panels[0].scene.atoms.length") == 54
    assert "3 cell copies" in panel.inner_text()
    assert page.locator(".repeat-row input").first.is_disabled()
    # Entries that make no cell: an error, and the last valid matrix stays.
    row2 = page.get_by_label("Matrix row 2 column 1")
    row2.fill("2")
    row2.dispatch_event("change")
    status = page.locator(".repeat-matrix-status")
    assert "determinant 0" in status.inner_text()
    assert page.evaluate("viewerPrefs.repeatMatrix")[1] == [-1, 1, 0]
    assert page.evaluate(total) == 54
    row2.fill("-1")
    row2.dispatch_event("change")
    # The stored cell beside the new one.
    panel.get_by_role("checkbox", name="Stored cell outline").check()
    page.wait_for_function(
        "currentPage.panels[0].scene.storedEdges.length === 12"
    )

    # Display only: the Info tab keeps the stored cell and says so.
    page.get_by_role("tab", name="Info").click()
    info = page.locator("#tabpanel-info")
    info.locator(".transform-note").wait_for()
    assert (
        "transformed by [[2, 1, 0], [-1, 1, 0], [0, 0, 1]]"
        in info.inner_text()
    )
    stored = page.evaluate("currentPage.structures[0].cell")
    # The cell vectors shown are the stored ones (a = 7.38 Å, not √3 a).
    assert f"{stored[0][0]:.4f}" in info.inner_text()
    assert f"{np.sqrt(3) * stored[0][0]:.4f}" not in info.inner_text()
    # ... and so do saved structures.
    page.get_by_role("tab", name="Save").click()
    page.select_option("select[aria-label='File format']", "extxyz")
    with page.expect_download() as download:
        page.get_by_role("button", name="Save structure").click()
    from ase.io import read

    saved = read(download.value.path(), format="extxyz")
    assert len(saved) == 18
    assert np.allclose(saved.cell[:], stored)

    # Kept with the settings; Clear all goes back to the repeat.
    page.reload()
    page.wait_for_function("currentPage && currentPage.panels[0].scene")
    assert page.evaluate(total) == 54
    page.get_by_role("tab", name="View").click()
    assert page.get_by_label("Matrix row 1 column 1").input_value() == "2"
    page.get_by_role("checkbox", name="Transformation matrix").uncheck()
    page.wait_for_function(f"{total} === 18")
    assert page.evaluate("viewerPrefs.repeatMatrix") is None
    assert not page.locator(".repeat-row input").first.is_disabled()


# ---------------------------------------------------------------- planes through atoms

# Plane polygons of panel `k`: in the display list, painted on a canvas (fill
# calls) and in the SVG.
_PLANES_CANVAS_SVG = """(k) => {
  const panel = currentPage.panels[k], w = panel.stage.clientWidth, h = panel.stage.clientHeight;
  const list = displayList(panel.scene, w, h, LIGHT_THEME, { tripod: false });
  const planes = list.filter((p) => p.kind === 'polygon' && p.fillAlpha === viewerPrefs.appearance.planeAlpha);
  const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  let fills = 0;
  const fill = ctx.fill.bind(ctx);
  ctx.fill = (...args) => { fills += 1; return fill(...args); };
  paintCanvas(ctx, planes, 1, {});
  return { count: planes.length, fills, colours: planes.map((p) => p.fill),
    svg: panelsToSvg([panel], { transparent: true, tripod: false }) };
}"""


def _plane_distance(atoms: Any, plane: list[int], atom: int) -> float:
    """The viewer's signed distance (normal up, else by the right-hand rule
    of the first three atoms)."""
    p = atoms.positions[plane]
    centre = p.mean(axis=0)
    normal = np.linalg.svd(p - centre)[2][-1]
    up = np.cross(atoms.cell[0], atoms.cell[1])
    side = np.dot(normal, up / np.linalg.norm(up))
    turn = (
        side
        if abs(side) > 1e-6
        else np.dot(normal, np.cross(p[1] - p[0], p[2] - p[0]))
    )
    return float(
        np.dot(atoms.positions[atom] - centre, normal if turn > 0 else -normal)
    )


def test_planes_through_atoms_in_the_ledger_viewer(
    browser: Any, rutiles: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda message: (
            message.type == "error" and errors.append(message.text)
        ),
    )
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    ids = rutiles["ids"]
    miller = {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True}
    _open(
        page,
        rutiles,
        {"tab": "planes", "planes": [miller]},
        f"&compare={ids[1]}",
    )
    planes_tab = page.locator("#tabpanel-planes")
    assert "d = " in planes_tab.inner_text()  # the Miller plane's spacing
    page.get_by_role("button", name="Plane through atoms").click()
    assert "picks them for a plane" in page.locator(".click-mode").inner_text()
    pick = (
        "(i) => currentPage.panels[0].onPick({ index: i, image: [0, 0, 0],"
        " symbol: currentPage.structures[0].symbols[i], count: 6 })"
    )
    for i in (0, 1, 4, 5):
        page.evaluate(pick, i)
    page.evaluate(pick, 5)  # a second click drops the atom
    assert "3 picked" in page.locator(".click-mode").inner_text()
    page.get_by_role("button", name="Make plane (3 atoms)").click()
    page.wait_for_selector(".atom-plane")
    plane = page.evaluate("viewerPrefs.planes[1]")
    assert [r["index"] for r in plane["atoms"]] == [0, 1, 4]
    assert page.evaluate("measureState.mode") == "off"
    assert "through 3 atoms" in planes_tab.inner_text().lower()
    # Drawn on both panels (same atoms), the same on canvas and in SVG.
    for k in (0, 1):
        assert (
            page.evaluate(f"currentPage.panels[{k}].scene.planes.length") == 2
        )
        drawn = page.evaluate(_PLANES_CANVAS_SVG, k)
        assert drawn["count"] == drawn["fills"] == 2
        for colour in drawn["colours"]:
            assert f'fill="{colour}" fill-opacity=' in drawn["svg"]
    # Patch around the atoms instead.
    page.locator(".plane-patch").check()
    page.wait_for_function(
        "currentPage.panels[0].scene.planes.some((p) => p.polygon.patch)"
    )

    # Measure: distance of O 2 to the plane, and the angle to (001).
    page.get_by_role("tab", name="Measure").click()
    page.select_option("select[aria-label='Measure']", "plane-distance")
    page.select_option("select[aria-label='Plane']", "1")
    page.evaluate(pick, 2)
    page.select_option("select[aria-label='Measure']", "plane-angle")
    page.select_option("select[aria-label='Plane']", "0")
    page.select_option("select[aria-label='Second plane']", "1")
    page.get_by_role("button", name="Measure angle").click()
    rows = page.locator(".measure-row")
    assert rows.count() == 2
    shown = _shown(page)
    distances = [_plane_distance(s, [0, 1, 4], 2) for s in shown]
    assert min(abs(d) for d in distances) > 0.1
    assert rows.nth(0).locator(".measure-value").inner_text() == " | ".join(
        f"{d:.3f} Å" for d in distances
    )
    normals = []
    for s in shown:
        p = s.positions[[0, 1, 4]]
        normals.append(np.linalg.svd(p - p.mean(axis=0))[2][-1])
    angles = [np.degrees(np.arccos(min(1.0, abs(n[2])))) for n in normals]
    assert rows.nth(1).locator(".measure-value").inner_text() == " | ".join(
        f"{a:.1f}°" for a in angles
    )
    assert "∠ (0 0 1) / plane Ti0 Ti1 O4" in rows.nth(1).inner_text()

    # Compared with a structure with other atoms: the plane and the
    # measurements stay on the left only, with notes.
    page.evaluate(
        "hash => { location.hash = hash; }",
        f"#/structures/{ids[0]}?from={rutiles['aggregation']}&compare={ids[2]}",
    )
    page.wait_for_function(
        f"currentPage && currentPage.structures[1]?.id === '{ids[2]}'"
        " && currentPage.panels.every((p) => p.scene)"
    )
    assert page.evaluate("currentPage.panels[0].scene.planes.length") == 2
    assert page.evaluate("currentPage.panels[1].scene.planes.length") == 1
    assert page.evaluate("currentPage.panels[1].scene.marks.length") == 0
    assert rows.nth(0).locator(".measure-value").inner_text().endswith("| –")
    page.get_by_role("tab", name="Planes").click()
    assert "atoms of this structure differ" in planes_tab.inner_text()
    # Only the structure with other atoms: plane measurements stay in the
    # list with their labels and "–", like other measurements (issue 14).
    page.evaluate(
        "hash => { location.hash = hash; }",
        f"#/structures/{ids[2]}?from={rutiles['aggregation']}",
    )
    page.wait_for_function(
        f"currentPage && currentPage.structures[0]?.id === '{ids[2]}'"
        " && currentPage.structures.length === 1 && currentPage.panels[0].scene"
    )
    page.get_by_role("tab", name="Measure").click()
    assert rows.count() == 2
    assert [
        rows.nth(k).locator(".measure-value").inner_text() for k in (0, 1)
    ] == [
        "–",
        "–",
    ]
    assert "O2 → plane Ti0 Ti1 O4" in rows.nth(0).inner_text()
    assert "∠ (0 0 1) / plane Ti0 Ti1 O4" in rows.nth(1).inner_text()
    assert "not shown" not in page.locator("#tabpanel-measure").inner_text()
    assert page.evaluate("currentPage.panels[0].scene.marks.length") == 0
    # Deleted like any row; the other one shows its value again on a
    # structure it fits.
    rows.nth(1).get_by_role("button", name="Remove measurement").click()
    assert rows.count() == 1
    page.evaluate(
        "hash => { location.hash = hash; }",
        f"#/structures/{ids[0]}?from={rutiles['aggregation']}",
    )
    page.wait_for_function(
        f"currentPage && currentPage.structures[0]?.id === '{ids[0]}'"
        " && currentPage.structures.length === 1 && currentPage.panels[0].scene"
    )
    page.get_by_role("tab", name="Measure").click()
    assert rows.count() == 1
    assert rows.nth(0).locator(".measure-value").inner_text() == (
        f"{distances[0]:.3f} Å"
    )
    assert errors == []
    context.close()


_HIDDEN_CENTRE_POINT = """(() => {
  const panel = currentPage.panels[0], box = panel.stage.getBoundingClientRect();
  const atom = panel.scene.atoms.find((a) => a.hiddenCentre);
  const [x, y] = projector(panel.scene, box.width, box.height)(atom.position);
  return [box.left + x, box.top + y];
})()"""


def test_polyhedra_without_their_centre_atoms(
    browser: Any, rutiles: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    _open(
        page,
        rutiles,
        {"tab": "style", "polyhedra": True, "polyhedraCentres": False},
    )

    def spheres() -> int:
        return page.evaluate(_PAINT_AND_SVG)["svg"].count('fill="url(#sphere')

    # Both Ti are drawn centres: the 4 O are drawn, the polyhedra stay, and
    # the Ti still count as shown.
    assert (
        page.evaluate(
            "currentPage.panels[0].scene.atoms.filter((a) => a.hiddenCentre).length"
        )
        == 2
    )
    assert spheres() == 4
    faces = page.evaluate("currentPage.panels[0].scene.polyhedra.length")
    assert faces == 2
    assert page.evaluate(
        "document.body.textContent.includes('6 of 6 atoms shown')"
    )

    # A hidden centre is still hovered and picked inside its polyhedron.
    page.keyboard.press("c")
    page.wait_for_timeout(200)
    x, y = page.evaluate(_HIDDEN_CENTRE_POINT)
    page.mouse.move(x, y)
    page.wait_for_selector(".tooltip", state="visible")
    assert "not drawn" in page.locator(".tooltip").inner_text()

    panel = page.locator("#tabpanel-style")
    centres = panel.get_by_role("checkbox", name="Show centre atoms")
    assert not centres.is_disabled() and not centres.is_checked()
    centres.check()
    page.wait_for_function("viewerPrefs.polyhedraCentres === true")
    assert spheres() == 6
    assert page.evaluate("currentPage.panels[0].scene.polyhedra.length") == 2

    # Disabled while polyhedra are off, and in space-filling.
    panel.get_by_role("checkbox", name="Polyhedra", exact=True).uncheck()
    assert centres.is_disabled()
    panel.get_by_role("checkbox", name="Polyhedra", exact=True).check()
    assert not centres.is_disabled()
    page.get_by_label("Model").select_option("space-filling")
    assert centres.is_disabled()
    assert errors == []
    context.close()


def test_outline_of_every_repeated_copy(
    browser: Any, rutiles: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    _open(page, rutiles, {"tab": "view", "repeat": [2, 2, 1]})
    edges = "currentPage.panels[0].scene.cellEdges.length"
    assert page.evaluate(edges) == 12
    lines = page.evaluate(_PAINT_AND_SVG)["svg"].count("<line")

    panel = page.locator("#tabpanel-view")
    every = panel.get_by_role("checkbox", name="Outline every copy")
    assert not every.is_disabled() and not every.is_checked()
    every.check()
    page.wait_for_function(f"{edges} === 33")
    # Saved images draw the 4 outlines, each shared edge once.
    assert page.evaluate(_PAINT_AND_SVG)["svg"].count("<line") == lines + 21
    assert page.evaluate(
        "JSON.parse(localStorage.getItem('stoms.viewer')).repeatCellOutline"
    )
    # Kept across a reload (the saved settings).
    page.reload()
    page.wait_for_function("currentPage && currentPage.panels[0].scene")
    assert page.evaluate(edges) == 33

    # Disabled while the outline is off.
    panel = page.locator("#tabpanel-view")
    every = panel.get_by_role("checkbox", name="Outline every copy")
    panel.get_by_role("checkbox", name="Cell outline").uncheck()
    assert every.is_disabled()
    assert page.evaluate(edges) == 0
    panel.get_by_role("checkbox", name="Cell outline").check()
    assert not every.is_disabled()
    assert errors == []
    context.close()


def test_outline_every_copy_locks_the_stored_cell_outline(
    browser: Any, rutiles: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    matrix = [[1, 1, 0], [-1, 1, 0], [0, 0, 1]]
    _open(page, rutiles, {"tab": "view", "repeatMatrix": matrix})
    panel = page.locator("#tabpanel-view")
    stored = panel.get_by_label("Stored cell outline")
    every = panel.get_by_role("checkbox", name="Outline every copy")
    assert not stored.is_disabled() and not stored.is_checked()
    every.check()
    # Locked and shown ticked; the setting itself is kept.
    assert stored.is_disabled() and stored.is_checked()
    assert "Outline every copy" in stored.evaluate(
        "i => i.parentElement.title"
    )
    assert page.evaluate("viewerPrefs.storedCellOutline") is False
    # The clipped grid of c(2×2): 9 dotted pieces.
    assert page.evaluate("currentPage.panels[0].scene.storedEdges.length") == 9
    every.uncheck()
    assert not stored.is_disabled() and not stored.is_checked()
    assert page.evaluate("currentPage.panels[0].scene.storedEdges.length") == 0
    assert errors == []
    context.close()


def test_plane_extend_factor_in_the_ledger_viewer(
    page: Any, site: dict[str, Any]
) -> None:
    """Issue 10: "Extend ×" scales the drawn plane about its centre; it is
    saved with the settings and kept across a reload."""
    miller = {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True}
    _open(page, site, {"tab": "planes", "planes": [miller]})
    polygon = "currentPage.panels[0].scene.planes[0].polygon"
    before = page.evaluate(polygon)
    field = page.locator("#tabpanel-planes").get_by_label("Extend factor")
    assert field.input_value() == "1"

    def extend(value: str) -> None:
        field.fill(value)
        field.dispatch_event("change")

    extend("2")
    page.wait_for_function("viewerPrefs.planes[0].scale === 2")
    after = page.evaluate(polygon)
    centre = np.asarray(before["centre"])
    assert after["centre"] == pytest.approx(before["centre"])
    assert np.asarray(after["points"]) - centre == pytest.approx(
        2 * (np.asarray(before["points"]) - centre)
    )
    saved = "JSON.parse(localStorage.getItem('stoms.viewer')).planes[0]"
    assert page.evaluate(saved)["scale"] == 2
    page.reload()
    page.wait_for_function("currentPage && currentPage.panels[0].scene")
    field = page.locator("#tabpanel-planes").get_by_label("Extend factor")
    assert field.input_value() == "2"
    assert np.asarray(page.evaluate(polygon)["points"]) == pytest.approx(
        np.asarray(after["points"])
    )
    # Out of range: the field goes back, the plane keeps its scale.
    extend("20")
    assert field.input_value() == "2"
    assert page.evaluate("viewerPrefs.planes[0].scale") == 2
    # 1 is today's plane, stored without a scale.
    extend("1")
    page.wait_for_function("!('scale' in viewerPrefs.planes[0])")
    assert "scale" not in page.evaluate(saved)
    assert np.asarray(page.evaluate(polygon)["points"]) == pytest.approx(
        np.asarray(before["points"])
    )


# ---------------------------------------------------------------- hydrogen bonds per acceptor


@pytest.fixture(scope="module")
def amine_site(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[dict[str, Any]]:
    """Water on a surface with an amine N: H···O 1.8 Å, H···N 2.2 Å."""
    from test_bond_search import water_and_amine

    path = tmp_path_factory.mktemp("amine") / "amine.ledger"
    ledger = AtomsLedger(path)
    source = StructureSourceSpec(kind="generated", name="test")
    structure_id = cast(
        str,
        ledger.add_structure(
            water_and_amine(),
            source,
            Provenance(created_by="t", purpose="viewer"),
        ),
    )
    aggregation = ledger.create_aggregation(
        name="amine", members=[AggregationMemberInput(structure_id)]
    )
    server = create_server(
        ledger, str(path), port=0, access=AccessOptions(token=TEST_TOKEN)
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {
        "base": f"http://127.0.0.1:{server.server_address[1]}",
        "ids": [structure_id],
        "aggregation": aggregation.id,
    }
    server.shutdown()
    server.server_close()


def test_hydrogen_bond_ranges_per_acceptor_in_the_ledger_viewer(
    browser: Any, amine_site: dict[str, Any]
) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{amine_site['base']}/?token={TEST_TOKEN}")
    _open(page, amine_site, {"tab": "style", "hbonds": {"show": True}})
    pairs = "currentPage.panels[0].scene.hbonds.length"
    assert page.evaluate(pairs) == 2
    page.locator("summary", has_text="Bond search").click()
    per_acceptor = page.get_by_label("Per acceptor H···A ranges")
    assert not per_acceptor.is_checked()
    assert not page.get_by_label("Longest H···O").is_visible()

    # On, no row edited: the rows show the single range, nothing changes.
    per_acceptor.check()
    page.wait_for_function("viewerPrefs.hbonds.perAcceptor === true")
    for symbol in ("O", "N", "F"):
        assert (
            page.get_by_label(f"Shortest H···{symbol}").input_value() == "1.5"
        )
        assert (
            page.get_by_label(f"Longest H···{symbol}").input_value() == "2.5"
        )
    assert page.evaluate("viewerPrefs.hbonds.ranges") == {}
    assert page.evaluate(pairs) == 2

    # O gets 1.5–1.7 Å: its bond (1.8 Å) goes, the N one (2.2 Å) stays.
    longest_o = page.get_by_label("Longest H···O")
    longest_o.fill("1.7")
    longest_o.dispatch_event("change")
    page.wait_for_function("currentPage.panels[0].scene.hbonds.length === 1")
    assert page.evaluate("viewerPrefs.hbonds.ranges") == {"O": [1.5, 1.7]}
    # Only the edited row has a ↺.
    assert page.get_by_label("Single H···A range for O").is_visible()
    assert not page.get_by_label("Single H···A range for N").is_visible()
    assert not page.get_by_label("Single H···A range for F").is_visible()
    # N gets 1.5–2.0 Å as well: none left.
    longest_n = page.get_by_label("Longest H···N")
    longest_n.fill("2")
    longest_n.dispatch_event("change")
    page.wait_for_function("currentPage.panels[0].scene.hbonds.length === 0")
    # A new single range moves the rows without a value of their own.
    longest = page.get_by_label("Longest H···A")
    longest.fill("2.4")
    longest.dispatch_event("change")
    page.wait_for_function("viewerPrefs.hbonds.max === 2.4")
    assert page.get_by_label("Longest H···F").input_value() == "2.4"
    assert longest_o.input_value() == "1.7"

    # Acceptors: a removed element's row goes, an added one starts from
    # the single range.
    acceptors = page.get_by_label("Hydrogen bond acceptors")
    acceptors.fill("O N Cl")
    acceptors.dispatch_event("change")
    page.wait_for_function(
        'JSON.stringify(viewerPrefs.hbonds.acceptors) === \'["O","N","Cl"]\''
    )
    assert page.get_by_label("Longest H···F").count() == 0
    assert page.get_by_label("Longest H···Cl").input_value() == "2.4"
    assert longest_o.input_value() == "1.7"

    # ↺ on N: its own range goes, the row follows the single range again
    # (1.5–2.4 Å: the N bond is back) and its ↺ hides.
    reset_n = page.get_by_label("Single H···A range for N")
    reset_n.click()
    page.wait_for_function("currentPage.panels[0].scene.hbonds.length === 1")
    assert page.evaluate("viewerPrefs.hbonds.ranges") == {"O": [1.5, 1.7]}
    assert longest_n.input_value() == "2.4"
    assert not reset_n.is_visible()
    longest.fill("2.1")
    longest.dispatch_event("change")
    page.wait_for_function("currentPage.panels[0].scene.hbonds.length === 0")
    assert longest_n.input_value() == "2.1"
    longest.fill("2.4")
    longest.dispatch_event("change")
    page.wait_for_function("currentPage.panels[0].scene.hbonds.length === 1")

    # Off: the single range (1.5–2.4) again, ranges kept.
    per_acceptor.uncheck()
    page.wait_for_function("currentPage.panels[0].scene.hbonds.length === 2")
    assert not longest_o.is_visible()
    assert page.evaluate("viewerPrefs.hbonds.ranges") == {"O": [1.5, 1.7]}
    assert errors == []
    context.close()


_SINGLE_CELL_SCENE = """(() => {
  const sc = currentPage.panels[0].scene;
  return { atoms: sc.atoms.length, extra: sc.extraAtoms, polyhedra: sc.polyhedra.length,
    edges: sc.cellEdges.length, stored: sc.storedEdges.length, transform: sc.transform !== null,
    planes: sc.planes.length };
})()"""


def _cell_controls(page: Any) -> dict[str, Any]:
    """What the controls single cell only overrides show."""
    panel = page.locator("#tabpanel-view")
    return {
        "repeat": [
            panel.locator(".repeat-row input").nth(k).input_value()
            for k in range(3)
        ],
        "wrap": panel.get_by_role(
            "checkbox", name="Wrap atoms into cell"
        ).is_checked(),
        "every": panel.get_by_role(
            "checkbox", name="Outline every copy"
        ).is_checked(),
        "matrix": panel.get_by_role(
            "checkbox", name="Transformation matrix"
        ).is_checked(),
        "outside": page.get_by_label("Bonded atoms outside").input_value(),
    }


_STORED_CONTROLS = {
    "repeat": ["2", "2", "1"],
    "wrap": False,
    "every": True,
    "matrix": True,
    "outside": "partners",
}
# While single cell only is on: what is in effect.
_SINGLE_CONTROLS = {
    "repeat": ["1", "1", "1"],
    "wrap": True,
    "every": False,
    "matrix": False,
    "outside": "hide",
}


def test_single_cell_only(browser: Any, rutiles: dict[str, Any]) -> None:
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{rutiles['base']}/?token={TEST_TOKEN}")
    prefs = {
        "tab": "view",
        "repeat": [2, 2, 1],
        "repeatMatrix": [[1, 1, 0], [-1, 1, 0], [0, 0, 1]],
        "repeatCellOutline": True,
        "wrap": False,
        "polyhedra": True,
        "bondedOutside": "partners",
        "planes": [
            {"h": 0, "k": 0, "l": 1, "t": 0.5, "show": True, "scale": 2}
        ],
    }
    _open(page, rutiles, prefs)
    before = page.evaluate(_SINGLE_CELL_SCENE)
    assert before["atoms"] > 6 and before["transform"] is True
    stored = page.evaluate("JSON.stringify(viewerPrefs)")

    panel = page.locator("#tabpanel-view")
    single = panel.get_by_role("checkbox", name="Single cell only")
    assert not single.is_checked()
    wrap = panel.get_by_role("checkbox", name="Wrap atoms into cell")
    every = panel.get_by_role("checkbox", name="Outline every copy")
    matrix = panel.get_by_role("checkbox", name="Transformation matrix")
    outside = page.get_by_label("Bonded atoms outside")
    extend = page.locator("#tabpanel-planes").get_by_label("Extend factor")
    for control in (wrap, every, matrix, outside, extend):
        assert not control.is_disabled()
    assert _cell_controls(page) == _STORED_CONTROLS

    single.check()
    page.wait_for_function("viewerPrefs.singleCell === true")
    # The 6 atoms of the stored cell once, no bonded atoms outside, no
    # polyhedra (both TiO6 reach into neighbouring cells), the stored outline.
    assert page.evaluate(_SINGLE_CELL_SCENE) == {
        "atoms": 6,
        "extra": 0,
        "polyhedra": 0,
        "edges": 12,
        "stored": 0,
        "transform": False,
        "planes": 1,
    }
    assert page.evaluate(
        "document.body.textContent.includes('6 of 6 atoms shown')"
    )
    assert page.evaluate(
        "JSON.parse(localStorage.getItem('stoms.viewer')).singleCell"
    )
    # The overridden controls are locked with the reason and show what is in
    # effect; the settings are kept (no change event from the shown values).
    assert _cell_controls(page) == _SINGLE_CONTROLS
    repeat_a = panel.locator(".repeat-row input").first
    for control in (repeat_a, wrap, every, matrix, outside, extend):
        assert control.is_disabled()
    assert "Single cell only is on" in repeat_a.get_attribute("title")
    assert "Single cell only is on" in wrap.evaluate(
        "i => i.closest('label').title"
    )
    assert "Single cell only is on" in extend.evaluate(
        "i => i.closest('label').title"
    )
    assert (
        page.evaluate("JSON.stringify({ ...viewerPrefs, singleCell: false })")
        == stored
    )
    # Hover and stepping keep working; it stays on for the next structure.
    assert "Ti" in _hover_text(page, 0)

    def step(key: str) -> None:
        page.evaluate("document.activeElement?.blur()")
        old = page.evaluate("location.hash")
        page.keyboard.press(key)
        page.wait_for_function("old => location.hash !== old", arg=old)
        page.wait_for_function(
            "currentPage && currentPage.panels[0].scene"
            " && location.hash.includes(currentPage.structures[0].id)"
        )

    step("ArrowRight")
    assert page.evaluate(_SINGLE_CELL_SCENE)["atoms"] == 6
    assert _cell_controls(page) == _SINGLE_CONTROLS

    # Off again: the previous view.
    step("ArrowLeft")
    panel = page.locator("#tabpanel-view")
    panel.get_by_role("checkbox", name="Single cell only").uncheck()
    page.wait_for_function("viewerPrefs.singleCell === false")
    assert page.evaluate(_SINGLE_CELL_SCENE) == before
    assert page.evaluate("JSON.stringify(viewerPrefs)") == stored
    # The stored values show again.
    assert _cell_controls(page) == _STORED_CONTROLS
    assert not panel.get_by_role(
        "checkbox", name="Wrap atoms into cell"
    ).is_disabled()
    assert not page.get_by_label("Bonded atoms outside").is_disabled()
    assert errors == []
    context.close()


def test_single_cell_locks_the_vibration_repeat_apply(
    browser: Any, tmp_path: Path
) -> None:
    pytest.importorskip("phonopy")
    from stoms.web import load_phonons

    inas = Path(__file__).parent / "data" / "phonopy" / "inas"
    ledger = AtomsLedger(tmp_path / "phonons.ledger")
    _, phonons = load_phonons(
        ledger,
        inas / "POSCAR",
        dim="5",
        force_constants=inas / "FORCE_CONSTANTS",
    )
    [structure_id] = phonons
    server = create_server(ledger, "InAs", port=0, phonons=phonons)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000}, bypass_csp=True
    )
    try:
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(
            f"http://127.0.0.1:{server.server_address[1]}/?token={TEST_TOKEN}"
            f"#/structures/{structure_id}"
        )
        page.wait_for_function("currentPage && currentPage.panels[0].scene")
        page.get_by_role("tab", name="Vibrations").click()
        # At q = (½, 0, 0) a repeat of 2 × 1 × 1 shows a whole wavelength.
        q = page.get_by_label("q along a*")
        q.fill("0.5")
        q.dispatch_event("change")
        apply = page.locator(".repeat-apply")
        apply.wait_for()
        assert apply.inner_text() == "Apply"
        assert not apply.is_disabled()

        page.get_by_role("tab", name="View").click()
        page.get_by_role("checkbox", name="Single cell only").check()
        page.wait_for_function("viewerPrefs.singleCell === true")
        assert apply.is_disabled()
        assert apply.get_attribute("title") == "Single cell only is on"
        page.get_by_role("checkbox", name="Single cell only").uncheck()
        page.wait_for_function("viewerPrefs.singleCell === false")
        assert not apply.is_disabled()
        assert apply.get_attribute("title") == "Set the repeat to this"
        assert errors == []
    finally:
        context.close()
        server.shutdown()
        server.server_close()
