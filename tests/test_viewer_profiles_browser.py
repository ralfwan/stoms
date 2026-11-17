"""GUI profiles (simple / advanced) in a real browser, on both hosts.

A profile only chooses which controls are shown (applyProfile in viewer.js):
simple hides the advanced controls that are not in use, and the sections and
tabs left empty; advanced shows everything. Switching never changes a setting
or the picture. The structure page keeps the profile in the browser
(localStorage), the notebook viewer in its state and saved HTML.

The other browser tests show every control (profile "advanced"); these open
the pages as a new user sees them. Skipped unless the ``browser`` dependency
group and Chromium are installed (see test_viewer_browser.py).
"""

import json
import re
from pathlib import Path
from typing import Any

import pytest
from web_access_helpers import TEST_TOKEN

from stoms.viewer import view

pytest.importorskip("playwright.sync_api")

from test_jupyter_viewer_browser import (  # noqa: E402
    SETUP,
    WIDGET_JS,
    needs_anywidget,
    open_document,
)
from test_viewer_browser import _open, browser, site  # noqa: E402,F401
from test_viewer_controls_browser import _slab_frames  # noqa: E402

# Tagged elements whose shown state differs from controlShown under the
# page's profile (empty when applyProfile did its job), on `root`.
MISMATCHES = """([root, context]) => {
  const ctx = eval(context), view = %s;
  return [...document.querySelector(root).querySelectorAll('[data-control]')]
    .filter((n) => n.hasAttribute('data-profile-hidden') === controlShown(n.dataset.control, view.profile, ctx, viewerPrefs)
      && !view.keep.has(n.dataset.control))
    .map((n) => n.dataset.control);
}"""
# Containers on screen whose tagged controls are all hidden (empty strips).
EMPTY_CONTAINERS = """(root) => [...document.querySelector(root).querySelectorAll(
    'section, details, fieldset, .check-row, .button-row, .button-grid, .inline-fields, .field-stack, .ring-step')]
  .filter((n) => n.offsetParent !== null && n.querySelector('[data-control]')
    && ![...n.querySelectorAll('[data-control]')].some((c) => c.offsetParent !== null)
    && !n.querySelector('[data-profile-content]'))
  .map((n) => n.className || n.tagName)"""
HIDDEN_IDS = """(root) => [...new Set([...document.querySelector(root).querySelectorAll('[data-control]')]
  .filter((n) => n.hasAttribute('data-profile-hidden')).map((n) => n.dataset.control))].sort()"""
# What the page draws: every canvas as an image.
SCENE = "[...document.querySelectorAll('canvas')].map((c) => c.toDataURL())"


@pytest.fixture
def page(browser: Any) -> Any:  # noqa: F811
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


def _ledger(page: Any, site: dict[str, Any], prefs: dict[str, Any]) -> None:  # noqa: F811
    """The structure page as a new user sees it (no stored profile)."""
    page.goto(f"{site['base']}/?token={TEST_TOKEN}")
    _open(page, site, prefs, profile=None)
    page.wait_for_timeout(200)


def _ledger_mismatches(page: Any) -> list[str]:
    return page.evaluate(
        MISMATCHES % "currentPage.profileView",
        ["#main", "currentPage.controlContext()"],
    )


def _settled(page: Any) -> None:
    """Wait for the profile's pass after a change (once per frame)."""
    page.evaluate(
        "() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )


# ------------------------------------------------------------ structure page


def test_ledger_default_is_simple(page: Any, site: dict[str, Any]) -> None:  # noqa: F811
    _ledger(page, site, {"tab": "view"})
    assert page.evaluate("currentPage.profileView.profile") == "simple"
    assert page.get_by_role("radio", name="Simple").is_checked()
    assert _ledger_mismatches(page) == []
    hidden = page.evaluate(HIDDEN_IDS, "#main")
    # Advanced controls without use are hidden: the transformation matrix,
    # the ring analysis (no rings), the bond cutoffs table.
    assert {"cell.matrix", "rings.method", "bonds.cutoffs"} <= set(hidden)
    assert all(
        not page.evaluate(
            f"controlIsSimple({json.dumps(i)}, currentPage.controlContext())"
        )
        for i in hidden
    )
    # Hidden controls leave the tab order (display: none).
    assert page.locator("[data-control='cell.matrix']").first.is_hidden()
    # The Rings tab has nothing to show without rings.
    assert page.locator("#tab-rings").is_hidden()
    assert page.locator("#tab-view").is_visible()
    # No empty sections or rows on any shown tab.
    for tab in page.locator("[role=tab]:visible").all():
        tab.click()
        _settled(page)
        assert page.evaluate(EMPTY_CONTAINERS, "#main") == [], tab.inner_text()
    assert page.errors == []


def test_ledger_switch_keeps_settings_and_scene(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    _ledger(page, site, {"tab": "style"})
    settings = page.evaluate("localStorage.getItem('stoms.viewer')")
    prefs = page.evaluate("JSON.stringify(viewerPrefs)")
    scene = page.evaluate(SCENE)
    page.get_by_role("radio", name="Advanced").check()
    _settled(page)
    assert (
        page.evaluate(
            "document.querySelectorAll('[data-profile-hidden]').length"
        )
        == 0
    )
    assert page.locator("#tab-rings").is_visible()
    assert (
        page.evaluate("localStorage.getItem('stoms.viewer.profile')")
        == "advanced"
    )
    page.get_by_role("radio", name="Simple").check()
    _settled(page)
    assert page.evaluate(HIDDEN_IDS, "#main") != []
    # Neither the settings (stored or live) nor the picture changed.
    assert page.evaluate("localStorage.getItem('stoms.viewer')") == settings
    assert page.evaluate("JSON.stringify(viewerPrefs)") == prefs
    assert page.evaluate(SCENE) == scene
    assert "profile" not in page.evaluate("Object.keys(viewerPrefs)")
    assert page.errors == []


def test_ledger_profile_persists(page: Any, site: dict[str, Any]) -> None:  # noqa: F811
    _ledger(page, site, {"tab": "view"})
    page.get_by_role("radio", name="Advanced").check()
    page.reload()
    page.wait_for_function(
        "currentPage && currentPage.panels.every((p) => p.scene)"
    )
    assert page.evaluate("currentPage.profileView.profile") == "advanced"
    assert page.get_by_role("radio", name="Advanced").is_checked()
    assert (
        page.evaluate(
            "document.querySelectorAll('[data-profile-hidden]').length"
        )
        == 0
    )
    # Kept apart from the settings, also in the exported settings file.
    assert "advanced" not in page.evaluate(
        "localStorage.getItem('stoms.viewer')"
    )
    with page.expect_download() as download:
        page.get_by_role("button", name="Export").click()
    exported = json.loads(Path(download.value.path()).read_text())
    assert "profile" not in exported and "profile" not in exported["settings"]
    assert page.errors == []


def test_ledger_open_tab_stays_until_left(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    _ledger(page, site, {"tab": "rings"})
    # Rings is open: it stays whole, although simple shows nothing on it.
    assert page.locator("#tab-rings").is_visible()
    assert page.locator("[data-control='rings.show']").is_visible()
    assert page.locator("[data-control='rings.method']").count() > 0
    assert _ledger_mismatches(page) == []
    page.get_by_role("tab", name="View").click()
    _settled(page)
    assert page.locator("#tab-rings").is_hidden()
    assert page.locator("[data-control='rings.show']").is_hidden()
    # Arrow keys step over the hidden tab.
    page.locator("#tab-planes").click()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("viewerPrefs.tab") != "rings"
    assert page.errors == []


def test_ledger_settings_in_use_stay_shown(
    page: Any,
    site: dict[str, Any],  # noqa: F811
) -> None:
    """Simple never hides a setting that changes the picture (issue 03 adds
    the "adv." mark and the count)."""
    _ledger(
        page,
        site,
        {"tab": "view", "repeatMatrix": [[2, 0, 0], [0, 1, 0], [0, 0, 1]]},
    )
    assert page.locator("label[data-control='cell.matrix']").is_visible()
    assert _ledger_mismatches(page) == []
    # Set back to the default: it stays shown until the tab is left.
    page.locator("label[data-control='cell.matrix'] input").uncheck()
    _settled(page)
    assert page.evaluate("viewerPrefs.repeatMatrix") is None
    assert page.locator("label[data-control='cell.matrix']").is_visible()
    page.get_by_role("tab", name="Style").click()
    page.get_by_role("tab", name="View").click()
    _settled(page)
    assert page.locator("label[data-control='cell.matrix']").is_hidden()
    assert page.errors == []


# ------------------------------------------------------------ notebook viewer


def _notebook(page: Any, tmp_path: Path, **kwargs: Any) -> Any:
    viewer = view(_slab_frames(), static=True, **kwargs)
    open_document(page, viewer, tmp_path)
    page.wait_for_timeout(200)
    return viewer


NOTEBOOK_MISMATCHES = """() => {
  const ctx = embedControlContext();
  const profile = document.querySelector('.profile-switch input:checked').value;
  return [...document.querySelectorAll('#stoms-root [data-control]')]
    .filter((n) => n.hasAttribute('data-profile-hidden') === controlShown(n.dataset.control, profile, ctx, viewerPrefs))
    .map((n) => n.dataset.control);
}"""


def test_notebook_default_is_simple(page: Any, tmp_path: Path) -> None:
    _notebook(page, tmp_path)
    settings = page.locator("[data-control='embed.settings-toggle']")
    settings.click()
    # The switch sits at the top of ⚙ (not in the toolbar).
    assert page.locator(".embed-settings > .profile-row").is_visible()
    assert page.locator(".embed-bar .profile-switch").count() == 0
    assert page.get_by_role("radio", name="Simple").is_checked()
    assert page.evaluate(NOTEBOOK_MISMATCHES) == []
    hidden = page.evaluate(HIDDEN_IDS, "#stoms-root")
    assert {"cell.matrix", "bonds.cutoffs", "embed.panel-size"} <= set(hidden)
    assert page.evaluate(EMPTY_CONTAINERS, "#stoms-root") == []
    assert page.errors == []


def test_notebook_settings_button_is_never_hidden(
    page: Any, tmp_path: Path
) -> None:
    """The profile switch lives in ⚙: no profile may hide its button, even
    a level that would (as a profile file might, issue 05)."""
    _notebook(page, tmp_path)
    page.evaluate(
        """() => {
          CONTROLS['embed.settings-toggle'].level = 'advanced';
          document.querySelector('.embed-status').click();
        }"""
    )
    _settled(page)
    button = page.locator("[data-control='embed.settings-toggle']")
    assert not page.evaluate(
        "controlIsSimple('embed.settings-toggle', embedControlContext())"
    )
    assert button.is_visible()
    assert button.get_attribute("data-profile-hidden") is None
    assert page.errors == []


def test_notebook_switch_keeps_settings_and_scene(
    page: Any, tmp_path: Path
) -> None:
    _notebook(page, tmp_path)
    page.locator("[data-control='embed.settings-toggle']").click()
    prefs = page.evaluate("JSON.stringify(viewerPrefs)")
    scene = page.evaluate(SCENE)
    page.get_by_role("radio", name="Advanced").check()
    _settled(page)
    assert (
        page.evaluate(
            "document.querySelectorAll('[data-profile-hidden]').length"
        )
        == 0
    )
    page.get_by_role("radio", name="Simple").check()
    _settled(page)
    page.get_by_role("radio", name="Advanced").check()
    _settled(page)
    assert page.evaluate("JSON.stringify(viewerPrefs)") == prefs
    assert page.evaluate(SCENE) == scene
    # Settings files never hold it.
    with page.expect_download() as download:
        page.locator("button", has_text="Export").click()
    exported = json.loads(Path(download.value.path()).read_text())
    assert "profile" not in exported and "profile" not in exported["settings"]
    assert page.errors == []


def test_notebook_saved_html_keeps_the_profile(
    page: Any, tmp_path: Path
) -> None:
    _notebook(page, tmp_path)
    page.locator("[data-control='embed.settings-toggle']").click()
    page.get_by_role("radio", name="Advanced").check()
    with page.expect_download() as download:
        page.locator("button", has_text="Save HTML").click()
    saved = tmp_path / "saved.html"
    download.value.save_as(saved)
    data = json.loads(
        re.search(
            r'<script type="application/json" id="stoms-data">(.*?)</script>',
            saved.read_text(),
            re.S,
        ).group(1)
    )
    assert data["profile"] == "advanced"
    assert "profile" not in data["settings"]
    page.goto(saved.as_uri())
    page.wait_for_function("document.querySelector('canvas')?.width > 0")
    page.locator("[data-control='embed.settings-toggle']").click()
    assert page.get_by_role("radio", name="Advanced").is_checked()
    assert (
        page.evaluate(
            "document.querySelectorAll('[data-profile-hidden]').length"
        )
        == 0
    )
    assert page.errors == []


def test_notebook_profile_from_python(page: Any, tmp_path: Path) -> None:
    _notebook(page, tmp_path, profile="advanced")
    page.locator("[data-control='embed.settings-toggle']").click()
    assert page.get_by_role("radio", name="Advanced").is_checked()
    assert (
        page.evaluate(
            "document.querySelectorAll('[data-profile-hidden]').length"
        )
        == 0
    )
    assert page.errors == []


@needs_anywidget
def test_widget_profile_round_trips(page: Any) -> None:
    viewer = view(_slab_frames())
    assert viewer.profile == "simple"
    page.set_content('<div id="host"></div>')
    state = viewer.get_state()
    values = {
        k: state[k]
        for k in (
            "_document",
            "frame",
            "settings",
            "camera",
            "_snapshot",
            "_profile",
        )
    }
    page.evaluate(SETUP, {"source": WIDGET_JS, "values": values})
    inner = page.frame_locator("iframe")
    page.wait_for_function("window.saved.length > 0")
    inner.locator("[data-control='embed.settings-toggle']").click()
    assert inner.get_by_role("radio", name="Simple").is_checked()
    page.wait_for_timeout(500)  # the snapshot after ⚙ opened, if any
    settings = page.evaluate("JSON.stringify(window.model.get('settings'))")
    drawn = page.evaluate("window.saved.at(-1)._snapshot")
    # Page -> Python: the switch in ⚙.
    inner.get_by_role("radio", name="Advanced").check()
    page.wait_for_function("window.model.get('_profile') === 'advanced'")
    viewer.set_state(
        {"_profile": page.evaluate("window.model.get('_profile')")}
    )
    assert viewer.profile == "advanced"
    # Python -> page.
    viewer.profile = "simple"
    page.evaluate("p => window.model.set('_profile', p)", viewer.profile)
    page.wait_for_timeout(200)
    assert inner.get_by_role("radio", name="Simple").is_checked()
    # No setting changed and the drawing is the same.
    page.wait_for_timeout(300)
    assert (
        page.evaluate("JSON.stringify(window.model.get('settings'))")
        == settings
    )
    assert page.evaluate("window.saved.at(-1)._snapshot") == drawn
    assert "profile" not in viewer.settings
