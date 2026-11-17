"""GUI profiles: auto-reveal, the count and its list, data rules (browser).

In simple, an advanced control whose setting is in use is shown anyway with
a grey "adv." after its label (applyProfile in viewer.js), also when a lock
overrides it (shown greyed with the lock's tooltip). The count beside the
switch says how many advanced settings are active; its list jumps to one.
Data rules make a control simple for data with the feature. Both hosts.

Skipped unless the ``browser`` dependency group and Chromium are installed
(see test_viewer_browser.py).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from ase import Atoms
from ase.build import molecule
from web_access_helpers import TEST_TOKEN

from stoms.viewer import view

pytest.importorskip("playwright.sync_api")

from test_jupyter_viewer_browser import open_document  # noqa: E402
from test_viewer_browser import (  # noqa: E402,F401  (fixtures)
    _open,
    browser,
    site,
    trajectory,
)
from test_viewer_controls_browser import _slab_frames  # noqa: E402
from test_viewer_profiles_browser import (  # noqa: E402
    NOTEBOOK_MISMATCHES,
    _ledger,
    _ledger_mismatches,
    _settled,
)


@pytest.fixture
def page(browser: Any) -> Any:  # noqa: F811
    """A fresh page; errors and console errors are kept in page.errors."""
    context = browser.new_context(
        viewport={"width": 1400, "height": 1000},
        accept_downloads=True,
        bypass_csp=True,
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


MARK_TITLE = "Advanced setting, shown because it is in use"
MATRIX = [[2, 0, 0], [0, 1, 0], [0, 0, 1]]
# IDs of the controls that carry a mark, and of the settings counted.
MARKED = """(root) => [...new Set([...document.querySelector(root).querySelectorAll('[data-profile-mark]')]
  .map((m) => m.closest('[data-control]')?.dataset.control
    ?? m.previousElementSibling?.closest('[data-control]')?.dataset.control
    ?? m.nextElementSibling?.dataset.control))].sort()"""
COUNT = "(root) => document.querySelector(root + ' .profile-count')"
# The settings without the open tab (a jump may switch it).
PREFS = "JSON.stringify({ ...viewerPrefs, tab: null })"


def _count(page: Any, root: str) -> str | None:
    """The count's text, None while it is hidden."""
    button = page.locator(f"{root} .profile-count")
    return button.inner_text() if button.is_visible() else None


def _active(page: Any, view_expr: str) -> list[str]:
    return page.evaluate(f"{view_expr}.active.map((a) => a.id)")


def _mark_of(page: Any, selector: str) -> Any:
    """The mark next to or inside the first element matching `selector`."""
    return page.evaluate(
        """(selector) => {
          const node = document.querySelector(selector);
          const mark = node.querySelector('[data-profile-mark]')
            ?? (node.nextElementSibling?.matches('[data-profile-mark]') ? node.nextElementSibling : null)
            ?? (node.previousElementSibling?.matches('[data-profile-mark]') ? node.previousElementSibling : null);
          return mark && { text: mark.textContent, title: mark.title, visible: mark.offsetParent !== null };
        }""",
        selector,
    )


# ------------------------------------------------------------ structure page


def test_ledger_in_use_advanced_setting_is_marked_and_counted(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    # Advanced and in use: the matrix (two controls: toggle and entries).
    # Simple and in use: the repeat. Simple by a data rule (forces on this
    # structure) and in use: arrows.
    _ledger(
        page,
        site,
        {
            "tab": "view",
            "repeatMatrix": MATRIX,
            "repeat": [2, 1, 1],
            "arrows": {"show": True},
        },
    )
    assert _ledger_mismatches(page) == []
    matrix = page.locator("label[data-control='cell.matrix']")
    assert matrix.is_visible()
    mark = matrix.locator(".profile-mark")
    assert mark.is_visible()
    assert mark.get_attribute("title") == MARK_TITLE
    # The text for screen readers says the same.
    assert MARK_TITLE in mark.text_content()
    assert mark.locator("[aria-hidden=true]").inner_text() == "adv."
    active = _active(page, "currentPage.profileView")
    # The entries count with the matrix (countsWith): one setting.
    assert active == ["cell.matrix"]
    assert _count(page, "#main") == "1 advanced setting active"
    # No mark on simple controls, nor on one a data rule makes simple.
    marked = page.evaluate(MARKED, "#main")
    assert marked == ["cell.matrix", "cell.matrix-entries"]
    assert page.evaluate(
        "controlIsSimple('arrows.show', currentPage.controlContext())"
        " && controlInUse('arrows.show', viewerPrefs, currentPage.controlContext())"
    )
    assert "arrows.show" not in active and "cell.repeat" not in active
    # Advanced: no marks, no count.
    page.get_by_role("radio", name="Advanced").check()
    _settled(page)
    assert page.locator("#main [data-profile-mark]").count() == 0
    assert _count(page, "#main") is None
    page.get_by_role("radio", name="Simple").check()
    _settled(page)
    assert page.evaluate(MARKED, "#main") == marked
    # Set back to its default: still shown (with the mark) until the tab is
    # left; the count follows the setting at once.
    matrix.locator("input").uncheck()
    _settled(page)
    assert page.evaluate("viewerPrefs.repeatMatrix") is None
    assert matrix.is_visible() and mark.is_visible()
    assert _count(page, "#main") is None
    page.get_by_role("tab", name="Style").click()
    page.get_by_role("tab", name="View").click()
    _settled(page)
    assert matrix.is_hidden()
    assert page.locator("#main [data-profile-mark]").count() == 0
    assert page.errors == []


def test_ledger_locked_setting_is_revealed_greyed_and_counted(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """Decision 11: a matrix while single cell only is on is overridden but
    kept; simple shows it greyed with the lock's tooltip, and counts it."""
    _ledger(
        page, site, {"tab": "view", "singleCell": True, "repeatMatrix": MATRIX}
    )
    matrix = page.locator("label[data-control='cell.matrix']")
    assert matrix.is_visible()
    assert matrix.locator("input").is_disabled()
    assert "muted" in matrix.get_attribute("class")
    assert matrix.get_attribute("title") == page.evaluate("SINGLE_CELL_LOCK")
    assert matrix.locator(".profile-mark").is_visible()
    # The entries are hidden by the page itself while locked: only the
    # toggle counts.
    assert _active(page, "currentPage.profileView") == ["cell.matrix"]
    assert _count(page, "#main") == "1 advanced setting active"
    assert _ledger_mismatches(page) == []
    assert page.errors == []


def test_ledger_count_list_jumps_to_the_setting(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """The list names tab › section and label; choosing one opens its tab and
    closed section, shows it there and focuses it; no setting changes."""
    _ledger(
        page,
        site,
        {
            "tab": "view",
            "repeatMatrix": MATRIX,
            "hbonds": {"angle": 100},
        },
    )
    stored = json.loads(page.evaluate("localStorage.getItem('stoms.viewer')"))
    prefs = page.evaluate(PREFS)
    assert _count(page, "#main") == "2 advanced settings active"
    page.locator("#main .profile-count").click()
    items = page.locator("#main .profile-count-list button")
    texts = [t.replace("\xa0", " ") for t in items.all_inner_texts()]
    # (The text for screen readers follows on a line of its own.)
    assert [t.split("\n")[0].strip() for t in texts] == [
        "View › Cell › Transformation matrix adv.",
        "Style › Bond search › D–H···A angle adv.",
    ]
    assert page.locator("#main .profile-count").get_attribute(
        "aria-expanded"
    ) == ("true")
    page.locator(
        "#main .profile-count-list [data-profile-target='hbonds.angle']"
    ).click()
    _settled(page)
    assert page.evaluate("viewerPrefs.tab") == "style"
    assert page.locator("#main .profile-count-list").is_hidden()
    angle = page.locator("[data-control='hbonds.angle']")
    assert angle.is_visible()
    assert page.evaluate(
        "document.querySelector(\"[data-control='hbonds.angle']\").closest('details').open"
    )
    assert page.evaluate(
        "document.querySelector(\"[data-control='hbonds.angle']\").contains(document.activeElement)"
    )
    assert _mark_of(page, "[data-control='hbonds.angle']")["visible"]
    # Scrolled to the middle of the settings box (unless at its end).
    placed = page.evaluate(
        """() => { const node = document.querySelector("[data-control='hbonds.angle']");
          const box = node.closest('.viewer-controls'), r = node.getBoundingClientRect(), b = box.getBoundingClientRect();
          return { offset: (r.top + r.bottom) / 2 - (b.top + b.bottom) / 2, scrollable: box.scrollHeight > box.clientHeight,
            atEnd: box.scrollTop + box.clientHeight >= box.scrollHeight - 1, atStart: box.scrollTop === 0 }; }"""
    )
    assert placed["scrollable"]
    assert (
        abs(placed["offset"]) < 30 or placed["atEnd"] or placed["atStart"]
    ), placed
    # Settings untouched (only the open tab, remembered UI state, changed).
    assert page.evaluate(PREFS) == prefs
    after = json.loads(page.evaluate("localStorage.getItem('stoms.viewer')"))
    assert {**after, "tab": None} == {**stored, "tab": None}
    assert _ledger_mismatches(page) == []
    assert page.errors == []


def test_ledger_matrix_counts_through_its_entries_alone(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """Were the toggle hidden by the page, the entries would stand in for
    it: the matrix still counts once, and its list line jumps to them."""
    _ledger(page, site, {"tab": "style", "repeatMatrix": MATRIX})
    page.wait_for_selector(".related-chips")
    _settled(page)
    assert page.locator("[data-control='cell.matrix']").count() == 1
    page.evaluate(
        "document.querySelector(\"label[data-control='cell.matrix']\").hidden = true"
    )
    page.evaluate("currentPage.profileView.apply()")
    _settled(page)
    active = page.evaluate(
        "currentPage.profileView.active.map((a) => [a.id, a.node.dataset.control])"
    )
    assert active == [["cell.matrix", "cell.matrix-entries"]]
    assert _count(page, "#main") == "1 advanced setting active"
    page.locator("#main .profile-count").click()
    page.locator(
        "#main .profile-count-list [data-profile-target='cell.matrix']"
    ).click()
    _settled(page)
    assert page.evaluate("viewerPrefs.tab") == "view"
    assert page.locator("[data-control='cell.matrix-entries']").is_visible()
    assert page.errors == []


def test_ledger_count_list_reveals_a_setting_back_at_default(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """A jump reveals the control until the tab is left, also once it is set
    back to its default from there."""
    _ledger(page, site, {"tab": "view", "hbonds": {"angle": 100}})
    page.locator("#main .profile-count").click()
    page.locator(
        "#main .profile-count-list [data-profile-target='hbonds.angle']"
    ).click()
    _settled(page)
    angle = page.locator("[data-control='hbonds.angle'] input")
    angle.fill("120")
    angle.dispatch_event("change")
    _settled(page)
    assert page.evaluate("viewerPrefs.hbonds.angle") == 120
    assert angle.is_visible()
    assert _count(page, "#main") is None
    page.get_by_role("tab", name="View").click()
    page.get_by_role("tab", name="Style").click()
    _settled(page)
    assert page.locator("[data-control='hbonds.angle']").is_hidden()
    assert page.errors == []


def test_ledger_data_rule_follows_the_structure(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """Polyhedron centres are simple for a structure with metals (the Cu
    overlayer) and hidden without (graphene); no mark either way."""
    hidden = "(sel) => document.querySelector(sel).hasAttribute('data-profile-hidden')"
    centres = "[data-control='polyhedra.centres']"
    _ledger(page, site, {"tab": "style"})
    assert page.evaluate("currentPage.controlContext().hasMetal")
    assert not page.evaluate(hidden, centres)
    assert page.evaluate(MARKED, "#main") == []
    _open(page, site, {"tab": "style"}, index=1, profile=None)
    assert not page.evaluate("currentPage.controlContext().hasMetal")
    assert page.evaluate(hidden, centres)
    assert _ledger_mismatches(page) == []
    assert page.errors == []


def test_ledger_reapplies_when_the_data_changes(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """The step list arrives after the page is drawn, a comparison adds a
    structure: the data rules follow (step controls, Close comparison)."""
    _ledger(page, site, {"tab": "view"})
    page.wait_for_selector(".related-chips")
    _settled(page)
    assert page.evaluate("currentPage.controlContext().stepCount") == 3
    for id_ in ["step.picker", "step.previous-next", "compare.with"]:
        assert page.locator(f"[data-control='{id_}']").first.is_visible(), id_
    assert _ledger_mismatches(page) == []
    page.locator("select[data-control='compare.with']").select_option(
        site["ids"][1]
    )
    page.wait_for_function(
        "currentPage && currentPage.panels.length === 2"
        " && currentPage.panels.every((p) => p.scene)"
    )
    page.wait_for_selector(".related-chips")
    _settled(page)
    assert page.locator("[data-control='compare.close']").first.is_visible()
    assert _ledger_mismatches(page) == []
    assert page.errors == []


def test_ledger_movie_frames_keep_the_profile(
    page: Any,
    trajectory: dict[str, Any],  # noqa: F811
) -> None:
    page.goto(f"{trajectory['base']}/?token={TEST_TOKEN}")
    _open(
        page,
        trajectory,
        {"tab": "view", "repeatMatrix": MATRIX},
        index=2,
        profile=None,
    )
    page.wait_for_selector(".player input[type=range]", state="attached")
    _settled(page)
    before = _active(page, "currentPage.profileView")
    page.evaluate(
        "(() => { const slider = document.querySelector('.player input[type=range]');"
        " slider.value = 1; slider.dispatchEvent(new Event('input')); })()"
    )
    page.wait_for_function(
        "currentPage.movie && currentPage.movie.index === 1"
    )
    _settled(page)
    assert _active(page, "currentPage.profileView") == before
    assert "cell.matrix" in before
    assert _ledger_mismatches(page) == []
    assert page.errors == []


@pytest.mark.parametrize(
    ("prefs", "counted", "not_counted"),
    [
        # Property settings count only in property mode (owner review of
        # issue 01, decision 9).
        (
            {"colour": "property", "property": {"min": -0.5}},
            ["colour.range"],
            [],
        ),
        (
            {"colour": "element", "property": {"min": -0.5}},
            [],
            ["colour.range"],
        ),
        # Per-acceptor ranges count while Per acceptor is off (decision 11).
        (
            {"hbonds": {"perAcceptor": False, "ranges": {"O": [1.5, 2.4]}}},
            ["hbonds.per-acceptor"],
            [],
        ),
    ],
)
def test_ledger_count_follows_the_in_use_tests(
    page: Any,
    site: dict[str, Any],  # noqa: F811
    prefs: dict[str, Any],
    counted: list[str],
    not_counted: list[str],
) -> None:
    _ledger(page, site, {"tab": "colour", **prefs})
    active = _active(page, "currentPage.profileView")
    assert set(counted) <= set(active)
    assert not set(not_counted) & set(active)
    # Exactly the advanced controls on the page whose setting is in use.
    expected = page.evaluate(
        """() => { const ctx = currentPage.controlContext();
          return [...new Set([...document.querySelectorAll('#main [data-control]')]
            .filter((n) => !hiddenByHost(n, document.querySelector('#main')))
            .map((n) => n.dataset.control))]
            .filter((id) => controlAdvanced(id, ctx) && controlInUse(id, viewerPrefs, ctx)); }"""
    )
    assert sorted(active) == sorted(expected)
    assert _count(page, "#main") == (
        f"{len(active)} advanced setting{'' if len(active) == 1 else 's'} active"
        if active
        else None
    )
    assert page.errors == []


def test_ledger_profile_settles(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """Marks and the count change the page only when they change: the
    profile is not applied again and again."""
    _ledger(page, site, {"tab": "view", "repeatMatrix": MATRIX})
    page.locator("#main .profile-count").click()
    _settled(page)
    passes = page.evaluate(
        """() => new Promise((resolve) => {
          let n = 0;
          currentPage.profileView.applied.add(() => { n += 1; });
          setTimeout(() => resolve(n), 500);
        })"""
    )
    assert passes == 0
    assert page.errors == []


def test_ledger_profile_object_from_a_file(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """A profile read from a file (checkProfileFile) applies like a built-in:
    it shows the advanced matrix it lists, hides the simple outline it lists,
    and the repeat it lists as hidden is shown with "adv." because it is in
    use. (Loading such a file in the page is for later; set directly here.)"""
    _ledger(page, site, {"tab": "view", "repeat": [2, 1, 1]})
    page.evaluate(
        """() => {
          const view = currentPage.profileView;
          view.profile = checkProfileFile({ stomsProfile: 1, name: 'custom', controls: {
            'cell.matrix': true, 'cell.outline': false, 'cell.repeat': false, 'future.control': true } }).profile;
          view.keep.clear();
          view.apply();
        }"""
    )
    _settled(page)
    assert _ledger_mismatches(page) == []
    assert page.locator("label[data-control='cell.matrix']").is_visible()
    assert (
        page.locator("[data-control='cell.matrix'] .profile-mark").count() == 0
    )
    assert page.locator("[data-control='cell.outline']").first.is_hidden()
    repeat = page.locator("[data-control='cell.repeat']").first
    assert repeat.is_visible()
    mark = _mark_of(page, "[data-control='cell.repeat']")
    assert mark == {"text": mark["text"], "title": MARK_TITLE, "visible": True}
    assert page.errors == []


# ------------------------------------------------------------ notebook viewer


def _notebook(page: Any, tmp_path: Path, frames: Any, **kwargs: Any) -> Any:
    viewer = view(frames, static=True, **kwargs)
    open_document(page, viewer, tmp_path)
    page.wait_for_timeout(200)
    return viewer


def _water() -> Atoms:
    atoms = molecule("H2O")
    atoms.center(vacuum=4.0)
    atoms.pbc = True
    return atoms


NB_ACTIVE = "(() => [...document.querySelectorAll('.profile-count-list [data-profile-target]')].map((b) => b.dataset.profileTarget))()"


def test_notebook_in_use_advanced_setting_is_marked_and_counted(
    page: Any, tmp_path: Path
) -> None:
    _notebook(
        page,
        tmp_path,
        _slab_frames(),
        settings={
            "repeatMatrix": MATRIX,
            "repeat": [2, 1, 1],
            "arrows": {"show": True, "source": "displacement"},
            "displacement": {"reference": "previous"},
        },
    )
    page.locator("[data-control='embed.settings-toggle']").click()
    _settled(page)
    assert page.evaluate(NOTEBOOK_MISMATCHES) == []
    matrix = page.locator("label[data-control='cell.matrix']")
    assert matrix.is_visible()
    assert matrix.locator(".profile-mark").get_attribute("title") == MARK_TITLE
    # The displacement reference is one control in two places (Arrows and
    # Colour atoms): counted once.
    count = page.evaluate(
        "document.querySelectorAll(\"[data-control='arrows.displacement-reference']\").length"
    )
    assert count >= 1
    page.locator("#stoms-root .profile-count").click()
    assert sorted(page.evaluate(NB_ACTIVE)) == sorted(
        [
            "arrows.displacement-reference",
            "arrows.vectors",
            "cell.matrix",
        ]
    )
    assert _count(page, "#stoms-root") == "3 advanced settings active"
    # The list says where: ⚙ › section.
    texts = page.locator(
        "#stoms-root .profile-count-list button"
    ).all_inner_texts()
    assert any(
        t.startswith("⚙ › ") and "Transformation matrix" in t for t in texts
    )
    # No mark on simple or data-rule controls.
    assert "cell.repeat" not in page.evaluate(MARKED, "#stoms-root")
    assert "arrows.show" not in page.evaluate(MARKED, "#stoms-root")
    page.get_by_role("radio", name="Advanced").check()
    _settled(page)
    assert page.locator("#stoms-root [data-profile-mark]").count() == 0
    assert _count(page, "#stoms-root") is None
    assert page.errors == []


def test_notebook_locked_setting_is_revealed_greyed_and_counted(
    page: Any, tmp_path: Path
) -> None:
    _notebook(
        page,
        tmp_path,
        _slab_frames(),
        settings={"singleCell": True, "repeatMatrix": MATRIX},
    )
    page.locator("[data-control='embed.settings-toggle']").click()
    _settled(page)
    matrix = page.locator("label[data-control='cell.matrix']")
    assert matrix.is_visible()
    assert matrix.locator("input").is_disabled()
    assert matrix.get_attribute("title") == page.evaluate("SINGLE_CELL_LOCK")
    assert matrix.locator(".profile-mark").is_visible()
    assert _count(page, "#stoms-root") == "1 advanced setting active"
    assert page.errors == []


def test_notebook_back_to_default_stays_until_settings_close(
    page: Any, tmp_path: Path
) -> None:
    _notebook(
        page, tmp_path, _slab_frames(), settings={"repeatMatrix": MATRIX}
    )
    toggle = page.locator("[data-control='embed.settings-toggle']")
    toggle.click()
    matrix = page.locator("label[data-control='cell.matrix']")
    matrix.locator("input").uncheck()
    _settled(page)
    assert page.evaluate("viewerPrefs.repeatMatrix") is None
    assert matrix.is_visible()
    assert _count(page, "#stoms-root") is None
    toggle.click()
    toggle.click()
    _settled(page)
    assert matrix.is_hidden()
    assert page.errors == []


def test_notebook_count_list_jumps_within_settings(
    page: Any, tmp_path: Path
) -> None:
    _notebook(page, tmp_path, [_water()], settings={"hbonds": {"angle": 100}})
    page.locator("[data-control='embed.settings-toggle']").click()
    prefs = page.evaluate(PREFS)
    page.locator("#stoms-root .profile-count").click()
    page.locator(
        "#stoms-root .profile-count-list [data-profile-target='hbonds.angle']"
    ).click()
    _settled(page)
    angle = page.locator("[data-control='hbonds.angle']")
    assert angle.is_visible()
    assert page.evaluate(
        "document.querySelector(\"[data-control='hbonds.angle']\").contains(document.activeElement)"
    )
    assert page.evaluate(PREFS) == prefs
    # Programmatic jump with ⚙ closed opens it.
    page.locator("[data-control='embed.settings-toggle']").click()
    assert page.locator(".embed-settings").is_hidden()
    assert page.evaluate(
        "document.querySelector('#stoms-root .profile-count-list [data-profile-target]').click() ?? true"
    )
    _settled(page)
    assert page.locator(".embed-settings").is_visible()
    assert angle.is_visible()
    assert page.evaluate(PREFS) == prefs
    assert page.errors == []


def test_notebook_data_rule_follows_the_frames(
    page: Any, tmp_path: Path
) -> None:
    """Hydrogen bonds are simple with H and O, N or F (water) and hidden
    without (a Pt slab); the frame controls need several frames."""
    hidden = "(sel) => document.querySelector(sel)?.hasAttribute('data-profile-hidden') ?? null"
    _notebook(page, tmp_path, [_water()])
    page.locator("[data-control='embed.settings-toggle']").click()
    _settled(page)
    assert page.evaluate(hidden, "[data-control='hbonds.show']") is False
    assert page.evaluate(MARKED, "#stoms-root") == []
    assert page.evaluate(NOTEBOOK_MISMATCHES) == []
    page.goto("about:blank")
    _notebook(page, tmp_path, _slab_frames())
    page.locator("[data-control='embed.settings-toggle']").click()
    _settled(page)
    assert page.evaluate(hidden, "[data-control='hbonds.show']") is True
    assert page.evaluate(hidden, "[data-control='frames.slider']") is False
    # Stepping through the frames keeps the profile as it is.
    page.locator("[data-control='frames.step']").last.click()
    _settled(page)
    assert page.evaluate(NOTEBOOK_MISMATCHES) == []
    assert page.errors == []
