"""The structure viewer in a real browser (headless Chromium via Playwright).

Skipped unless the ``browser`` dependency group and Chromium are installed:

    uv sync --group dev --group browser
    uv run playwright install chromium
"""

import json
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from ase.build import graphene

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    MethodSpec,
    Provenance,
    StructureSourceSpec,
)
from stoms.web import create_server, load_linked_pages

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
        chromium = p.chromium.launch()
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
    server = create_server(ledger, str(path), port=0)
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


def _open(
    page: Any,
    site: dict[str, Any],
    prefs: dict[str, Any],
    query: str = "",
    index: int = 0,
) -> None:
    """The viewer for structure ``index``, with these viewer settings."""
    page.goto(f"{site['base']}/")
    page.evaluate(
        "prefs => localStorage.setItem('stoms.viewer', JSON.stringify(prefs))",
        prefs,
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

    response = page.goto(
        f"{site['base']}/#/structures/{site['ids'][0]}?from={site['aggregation']}"
    )
    assert "script-src 'self'" in response.headers["content-security-policy"]
    wait("typeof currentPage !== 'undefined' && currentPage?.panels[0]?.scene")
    for tab in page.locator(".tab").all_inner_texts():
        page.get_by_role("tab", name=tab).click()
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
    (folder / "index.html").write_text(
        "<!doctype html><script>try { alert('hi'); } catch (e) {}</script>"
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
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/linked/stm/")
        page.wait_for_timeout(300)
        assert dialogs == []
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
        page.goto(
            f"http://127.0.0.1:{server.server_address[1]}/#/structures/{structure_id}"
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
