"""GUI profiles: the search for a control on the structure page (browser).

A field in the row of the profile switch finds controls by label, keyword,
tab and section name (createControlSearch in viewer.js), also those the
profile hides ("adv."); choosing one goes to it and shows it there until the
tab is left. Controls the page does not have for this structure are listed
greyed with what they need, and cannot be chosen. Keys: "/" goes to the
field, ↓/↑ move, Enter chooses, Esc clears.

Skipped unless the ``browser`` dependency group and Chromium are installed
(see test_viewer_browser.py).
"""

import threading
from pathlib import Path
from typing import Any

import pytest
from ase import Atoms

from stoms.atomsledger import AtomsLedger, Provenance, StructureSourceSpec
from stoms.web import AccessOptions, create_server

pytest.importorskip("playwright.sync_api")

from test_viewer_browser import (  # noqa: E402,F401  (fixtures)
    _open,
    browser,
    rutiles,
    site,
)
from test_viewer_controls_browser import (  # noqa: E402
    HAS_PHONOPY,
    HAS_SPGLIB,
    _phonon_page,
    _structure_page,
    _symmetry_page,
)
from test_viewer_profile_reveal_browser import PREFS  # noqa: E402
from test_viewer_profiles_browser import _ledger, _settled  # noqa: E402
from web_access_helpers import TEST_TOKEN  # noqa: E402


@pytest.fixture
def page(browser: Any) -> Any:  # noqa: F811
    """A fresh page; errors and console errors are kept in page.errors."""
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
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


FIELD = ".control-search"
LIST = ".control-search-list"
SEARCH_TITLE = "Advanced setting, shown because you searched for it"
HIDDEN_TITLE = "Advanced setting, hidden by the Simple profile"
MATRIX = "label[data-control='cell.matrix']"
# The search results shown: id, can be chosen, place, "adv.", note.
RESULTS = """() => [...document.querySelectorAll('.control-search-list [data-search-result]')].map((li) => ({
  id: li.dataset.searchResult,
  available: !li.classList.contains('unavailable'),
  place: li.querySelector('.control-search-place')?.textContent ?? '',
  adv: li.querySelector('.profile-mark')?.title ?? null,
  note: li.querySelector('.control-search-note')?.textContent ?? null,
  via: li.dataset.searchVia ?? null,
  disabled: li.getAttribute('aria-disabled') === 'true',
}))"""


def _search(page: Any, query: str) -> list[dict[str, Any]]:
    page.locator(FIELD).fill(query)
    _settled(page)
    return page.evaluate(RESULTS)


def _focused_control(page: Any) -> str | None:
    return page.evaluate(
        "document.activeElement?.closest('[data-control]')?.dataset.control ?? null"
    )


def test_search_finds_the_hidden_matrix_and_reveals_it_until_the_tab_is_left(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    _ledger(page, site, {"tab": "style"})
    prefs = page.evaluate(PREFS)
    assert page.locator(MATRIX).is_hidden()
    results = _search(page, "supercell")
    matrix = next(r for r in results if r["id"] == "cell.matrix")
    # Hidden by simple: "adv."; where it sits.
    assert matrix == {
        "id": "cell.matrix",
        "available": True,
        "place": "View › Cell",
        "adv": HIDDEN_TITLE,
        "note": None,
        "via": None,
        "disabled": False,
    }
    # A simple control: no "adv.".
    assert next(r for r in results if r["id"] == "cell.repeat")["adv"] is None
    page.locator("[data-search-result='cell.matrix']").click()
    _settled(page)
    # Its tab, the control shown with its mark, focused; the list closed.
    assert page.evaluate("viewerPrefs.tab") == "view"
    assert page.locator(MATRIX).is_visible()
    mark = page.locator(f"{MATRIX} .profile-mark")
    assert mark.get_attribute("title") == SEARCH_TITLE
    assert SEARCH_TITLE in mark.text_content()
    assert _focused_control(page) == "cell.matrix"
    assert page.locator(LIST).is_hidden()
    assert page.locator(FIELD).input_value() == "supercell"
    # Settings untouched (apart from the open tab).
    assert page.evaluate(PREFS) == prefs
    # Shown until the tab is left.
    page.get_by_role("tab", name="Colour").click()
    page.get_by_role("tab", name="View").click()
    _settled(page)
    assert page.locator(MATRIX).is_hidden()
    assert page.evaluate(PREFS) == prefs
    assert page.errors == []


def test_search_keys(page: Any, site: dict[str, Any]) -> None:  # noqa: F811
    _ledger(page, site, {"tab": "style"})
    # "/" goes to the field (from anywhere but a text field).
    page.locator("body").click(position={"x": 5, "y": 5})
    page.keyboard.press("/")
    assert page.evaluate("document.activeElement.matches('.control-search')")
    page.keyboard.type("supercell")
    _settled(page)
    assert page.locator(LIST).is_visible()
    # Enter: the first result that can be chosen (the repeat).
    page.keyboard.press("Enter")
    _settled(page)
    assert page.evaluate("viewerPrefs.tab") == "view"
    assert _focused_control(page) == "cell.repeat"
    # Not from a field that takes text (the repeat's number field).
    page.keyboard.press("/")
    assert _focused_control(page) == "cell.repeat"
    # ↓ ↓: the second result; Enter chooses it.
    page.locator(FIELD).click()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    selected = page.locator(f"{LIST} [aria-selected=true]")
    assert selected.get_attribute("data-search-result") == "cell.matrix"
    assert page.locator(FIELD).get_attribute(
        "aria-activedescendant"
    ) == selected.get_attribute("id")
    page.keyboard.press("Enter")
    _settled(page)
    assert _focused_control(page) == "cell.matrix"
    assert page.locator(MATRIX).is_visible()
    # Esc clears and closes, and is not the page's Escape.
    page.evaluate(
        "() => { currentPage.closeEditor = () => { window.pageEscape = true; return true; }; }"
    )
    # "/" from a check box (where the result left the focus).
    assert page.evaluate("document.activeElement.type") == "checkbox"
    page.keyboard.press("/")
    assert page.evaluate("document.activeElement.matches('.control-search')")
    page.keyboard.press("Control+a")
    page.keyboard.type("bonds")
    _settled(page)
    assert page.locator(LIST).is_visible()
    page.keyboard.press("Escape")
    assert page.locator(FIELD).input_value() == ""
    assert page.locator(LIST).is_hidden()
    assert page.evaluate("document.activeElement.matches('.control-search')")
    # Esc again (empty): leaves the field.
    page.keyboard.press("Escape")
    assert not page.evaluate(
        "document.activeElement.matches('.control-search')"
    )
    assert page.evaluate("window.pageEscape ?? null") is None
    # Enter with nothing that can be chosen does nothing.
    page.keyboard.press("/")
    page.keyboard.type("apply the repeat")
    _settled(page)
    assert [r["available"] for r in page.evaluate(RESULTS)] == [False]
    page.keyboard.press("Enter")
    _settled(page)
    assert page.evaluate("viewerPrefs.tab") == "view"
    assert page.locator(LIST).is_visible()
    # Nothing found.
    page.locator(FIELD).fill("no such control")
    _settled(page)
    assert page.locator(LIST).inner_text() == "No control found"
    assert page.errors == []


def test_search_lists_controls_that_need_data_greyed(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """The overlayer has no modes, no phonon data and is not compared."""
    _ledger(page, site, {"tab": "style"})
    prefs = page.evaluate(PREFS)
    mode = next(
        r for r in _search(page, "mode") if r["id"] == "vibration.mode"
    )
    assert mode == {
        "id": "vibration.mode",
        "available": False,
        "place": "Vibrations",
        "adv": None,
        "note": "needs vibrational modes",
        "via": None,
        "disabled": True,
    }
    item = page.locator("[data-search-result='vibration.mode']")
    assert "unavailable" in (item.get_attribute("class") or "")
    assert item.get_attribute("title") == "needs vibrational modes"
    # It cannot be chosen: nothing happens, the list stays.
    item.dispatch_event("click")
    _settled(page)
    assert page.evaluate("viewerPrefs.tab") == "style"
    assert page.locator(LIST).is_visible()
    swap = next(r for r in _search(page, "swap") if r["id"] == "compare.swap")
    assert swap["note"] == "only while comparing" and not swap["available"]
    # Needs data: cannot be chosen; never "adv." on a greyed result.
    assert swap["disabled"] and swap["via"] is None and swap["adv"] is None
    assert swap["place"] == "Compare"
    bands = {r["id"]: r for r in _search(page, "band structure")}
    assert bands["phonon.save-svg"]["note"] == "needs phonon data (phonopy)"
    # There, but hidden by another setting: its place, why, and where that
    # setting is (see test_search_greyed_result_goes_to_the_setting_it_needs).
    entries = {r["id"]: r for r in _search(page, "matrix entries")}
    assert entries["cell.matrix-entries"]["note"] == (
        "only with Transformation matrix on: choose to go to Transformation matrix"
    )
    assert entries["cell.matrix-entries"]["place"] == "View › Cell"
    assert entries["cell.matrix-entries"]["via"] == "cell.matrix"
    assert entries["cell.matrix-entries"]["adv"] is None
    # The notebook's own controls are not listed.
    assert _search(page, "save html") == []
    assert _search(page, "frame number") == []
    assert page.evaluate(PREFS) == prefs
    assert page.errors == []


@pytest.mark.parametrize("index", [0, 1])
def test_search_says_why_each_missing_control_is_missing(
    page: Any,
    site: dict[str, Any],  # noqa: F811
    index: int,
) -> None:
    """Every control the page lacks here has a reason of its own
    (CONTROL_NEEDS), not the generic note."""
    page.goto(f"{site['base']}/?token={TEST_TOKEN}")
    _open(page, site, {"tab": "view"}, index=index, profile=None)
    missing = page.evaluate(
        "controlSearchEntries(currentPage.profileView, currentPage.controlContext())"
        ".filter((r) => !r.available && !Object.hasOwn(CONTROL_NEED_OF, r.id)).map((r) => r.id)"
    )
    assert missing == []


def test_search_finds_a_control_of_the_info_tab(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """The Info tab is built only while open: its controls are found
    anyway, and built when chosen."""
    _ledger(page, site, {"tab": "view"})
    assert page.locator("[data-control='info.atom-positions']").count() == 0
    results = _search(page, "atom positions")
    assert results[0]["id"] == "info.atom-positions"
    assert results[0]["available"] and results[0]["place"] == "Info"
    page.keyboard.press("Enter")
    page.wait_for_function("viewerPrefs.tab === 'info'")
    page.wait_for_function(
        "document.activeElement?.closest('[data-control]')?.dataset.control === 'info.atom-positions'"
    )
    assert page.locator("[data-control='info.atom-positions']").is_visible()
    assert page.errors == []


def test_search_in_advanced_and_for_a_setting_in_use(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    _ledger(
        page,
        site,
        {"tab": "style", "repeatMatrix": [[2, 0, 0], [0, 1, 0], [0, 0, 1]]},
    )
    # In use: shown in simple already; choosing it keeps the "in use" mark.
    _search(page, "transformation matrix")
    page.locator("[data-search-result='cell.matrix']").click()
    _settled(page)
    assert page.locator(f"{MATRIX} .profile-mark").get_attribute("title") == (
        "Advanced setting, shown because it is in use"
    )
    # Advanced: no "adv." in the results, no mark after choosing.
    page.get_by_role("radio", name="Advanced").check()
    page.get_by_role("tab", name="Style").click()
    _settled(page)
    results = _search(page, "outline every copy")
    assert [r["adv"] for r in results] == [None]
    page.keyboard.press("Enter")
    _settled(page)
    assert _focused_control(page) == "cell.outline-every-copy"
    assert page.locator("[data-profile-mark]").count() == 0
    assert page.errors == []


def test_search_greyed_result_goes_to_the_setting_it_needs(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """A control that needs another setting stays greyed with its note;
    choosing it goes to that setting's control (shown, marked, focused),
    and changes no setting. Without that control shown, it cannot be
    chosen."""
    _ledger(page, site, {"tab": "style"})
    prefs = page.evaluate(PREFS)
    [opacity] = [
        r for r in _search(page, "ring opacity") if r["id"] == "rings.opacity"
    ]
    assert (
        opacity["note"]
        == "only with Show rings on: choose to go to Show rings"
    )
    assert opacity["via"] == "rings.show" and not opacity["available"]
    assert not opacity["disabled"] and opacity["adv"] is None
    page.locator("[data-search-result='rings.opacity']").click()
    _settled(page)
    # The Rings tab (hidden in simple: nothing in use) opens for it.
    assert page.evaluate("viewerPrefs.tab") == "rings"
    assert _focused_control(page) == "rings.show"
    show = page.locator("[data-control='rings.show']").first
    assert show.locator(".profile-mark").get_attribute("title") == SEARCH_TITLE
    assert page.locator("[data-control='rings.opacity']").first.is_hidden()
    assert page.evaluate(PREFS) == prefs
    # Keys: with nothing available, Enter takes the first that goes to a
    # setting; arrows stop on it too.
    page.locator(FIELD).fill("matrix preset")
    _settled(page)
    page.keyboard.press("ArrowDown")
    selected = page.locator(f"{LIST} [aria-selected=true]")
    assert selected.get_attribute("data-search-result") == "cell.matrix-preset"
    page.locator(FIELD).fill("matrix preset")
    _settled(page)
    page.keyboard.press("Enter")
    _settled(page)
    assert page.evaluate("viewerPrefs.tab") == "view"
    assert _focused_control(page) == "cell.matrix"
    # The custom palette needs the palette, which this page does not show
    # (colours by element): it cannot be chosen.
    [custom] = [
        r
        for r in _search(page, "custom palette colours")
        if r["id"] == "colour.custom-palette"
    ]
    assert custom["via"] is None and custom["disabled"]
    assert page.evaluate(PREFS) == prefs
    assert page.errors == []


def test_search_names_places_outside_the_tabs(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """Steps, Compare, Element bar, Footer (data-profile-place)."""
    _ledger(page, site, {"tab": "view"})
    places = {
        "step.previous-next": "Steps",
        "movie.play": "Steps",
        "compare.with": "Compare",
        "elements.bar": "Element bar",
        "footer.clear-all": "Footer",
        "footer.save-svg": "Footer",
    }
    for control, place in places.items():
        label = page.evaluate(f"CONTROLS[{control!r}].label")
        found = {r["id"]: r for r in _search(page, label)}
        assert found[control]["place"] == place, control
    # The count's list takes its places from the same code (controlPlace).
    assert page.evaluate(
        "controlPlace(document.querySelector(\"[data-control='footer.clear-all']\"), currentPage.profileView.root)"
    ) == ["Footer"]
    assert page.errors == []


class _Places:
    """Each hand-written place of CONTROL_NEEDS next to the real place of
    its control, on every page state where the control is there."""

    def __init__(self) -> None:
        self.seen: dict[str, set[tuple[str, str]]] = {}
        self.placed: set[str] = set()

    def collect(self, page: Any) -> None:
        for control, written, real in page.evaluate(PLACES):
            self.seen.setdefault(control, set()).add((written, real))
        self.placed = set(page.evaluate(PLACED))


PLACES = """() => { const root = document.querySelector('#main');
  return Object.values(CONTROL_NEEDS).filter((n) => n.place).flatMap((n) => n.controls.map((id) => {
    const nodes = [...root.querySelectorAll(`[data-control="${CSS.escape(id)}"]`)];
    const node = nodes.find((x) => !hiddenByHost(x, root)) ?? nodes[0];
    return node ? [id, controlNeedPlace(n, currentPage.controlContext()).join(' › '), controlPlace(node, root).join(' › ')] : null;
  })).filter(Boolean); }"""
PLACED = "Object.values(CONTROL_NEEDS).filter((n) => n.place).flatMap((n) => n.controls)"


def _info_page(browser: Any, tmp_path: Path, places: _Places) -> None:  # noqa: F811
    """A structure with stored info and provenance metadata, on Info."""
    ledger = AtomsLedger(tmp_path / "info.ledger")
    atoms = Atoms("H2O", positions=[[0, 0, 0], [0.96, 0, 0], [-0.24, 0.93, 0]])
    atoms.info["note"] = "relaxed"
    structure_id = ledger.add_structure(
        atoms,
        StructureSourceSpec(kind="generated", name="test"),
        Provenance(created_by="t", purpose="viewer", metadata={"run": 1}),
    )
    server = create_server(
        ledger, "info", port=0, access=AccessOptions(token=TEST_TOKEN)
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000}, bypass_csp=True
    )
    page = context.new_page()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        page.goto(f"{base}/?token={TEST_TOKEN}")
        page.evaluate(
            "localStorage.setItem('stoms.viewer', JSON.stringify({ tab: 'info' }))"
        )
        page.goto(f"{base}/#/structures/{structure_id}")
        page.reload()
        page.wait_for_selector(
            "[data-control='info.provenance']", state="attached"
        )
        places.collect(page)
    finally:
        context.close()
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def hand_written_places(
    browser: Any,  # noqa: F811
    site: dict[str, Any],  # noqa: F811
    rutiles: dict[str, Any],  # noqa: F811
    tmp_path_factory: pytest.TempPathFactory,
) -> _Places:
    """The pages of the registry coverage test (rings, planes, measurements,
    polyhedra, highlights, a comparison, a step list, symmetry, phonons) and
    one with stored info."""
    places = _Places()
    _structure_page(browser, site, places)
    if HAS_SPGLIB:
        _symmetry_page(browser, rutiles, places)
    if HAS_PHONOPY:
        _phonon_page(browser, tmp_path_factory.mktemp("phonons"), places)
    _info_page(browser, tmp_path_factory.mktemp("info"), places)
    return places


def test_search_hand_written_places_match_the_page(
    hand_written_places: _Places,
) -> None:
    """CONTROL_NEEDS places (shown while a control is missing) are where
    the control sits once it is there."""
    wrong = {
        control: pairs
        for control, pairs in hand_written_places.seen.items()
        if any(written != real for written, real in pairs)
    }
    assert wrong == {}
    missing = hand_written_places.placed - set(hand_written_places.seen)
    if not (HAS_SPGLIB and HAS_PHONOPY):
        pytest.skip(f"needs spglib and phonopy for: {sorted(missing)}")
    assert missing == set()
