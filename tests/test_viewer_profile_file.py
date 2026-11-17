"""GUI profile files: the format, its checkers in viewer.js and Python, and
the built-in profiles written in it.

checkProfileFile (viewer.js) and check_profile_file (stoms.viewer.profiles)
must agree: every case of tests/data/profile_files.json runs through both.
Python learns the control IDs from stoms/viewer/controls.json, generated from
the registry in viewer.js; when a control is added or renamed, regenerate it:

    STOMS_WRITE_CONTROLS=1 uv run --no-sync python -m pytest \\
        tests/test_viewer_profile_file.py -k controls_json

The browser test that a profile object hides and reveals controls on the
structure page is in test_viewer_profile_reveal_browser.py.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from test_viewer_controls import _node

from stoms.viewer import profiles
from stoms.viewer.profiles import builtin_profile, check_profile_file

ROOT = Path(__file__).parents[1]
CASES_FILE = ROOT / "tests" / "data" / "profile_files.json"
CONTROLS_JSON = ROOT / "src" / "stoms" / "viewer" / "controls.json"
CASES = json.loads(CASES_FILE.read_text(encoding="utf-8"))

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="needs node"
)


def _python(
    doc: Any, registry: dict[str, Any] | None = None
) -> dict[str, Any]:
    try:
        profile, warnings = check_profile_file(doc, registry)
    except ValueError as error:
        return {"error": str(error)}
    return {"profile": profile, "warnings": warnings}


# What checkProfileFile makes of `docs` (a JS expression for a list), in the
# same shape as _python.
_JS_CHECK = """(() => {
  const registry = %s;
  return %s.map((doc) => {
    try { return checkProfileFile(doc, ...(registry ? [registry] : [])); }
    catch (error) { return { error: error.message }; }
  });
})()"""


def _js(docs: list[Any], registry: dict[str, Any] | None = None) -> list[Any]:
    # Parsed in Node from the JSON text, so "__proto__" is a plain key.
    source = f"JSON.parse({json.dumps(json.dumps(docs))})"
    return _node(_JS_CHECK % (json.dumps(registry), source))


@pytest.fixture(scope="module")
def js_results() -> list[Any]:
    if shutil.which("node") is None:
        pytest.skip("needs node")
    return _js([case["doc"] for case in CASES["cases"]], CASES["registry"])


def _expected(case: dict[str, Any]) -> dict[str, Any]:
    if "error" in case:
        return {"error": case["error"]}
    return {"profile": case["profile"], "warnings": case["warnings"]}


@pytest.mark.parametrize(
    "index",
    range(len(CASES["cases"])),
    ids=[c["title"] for c in CASES["cases"]],
)
def test_python_checks_the_shared_cases(index: int) -> None:
    case = CASES["cases"][index]
    assert _python(case["doc"], CASES["registry"]) == _expected(case)


@needs_node
@pytest.mark.parametrize(
    "index",
    range(len(CASES["cases"])),
    ids=[c["title"] for c in CASES["cases"]],
)
def test_js_checks_the_shared_cases(index: int, js_results: list[Any]) -> None:
    assert js_results[index] == _expected(CASES["cases"][index])


def test_the_cases_cover_valid_and_invalid_files() -> None:
    errors = [c for c in CASES["cases"] if "error" in c]
    valid = [c for c in CASES["cases"] if "error" not in c]
    assert len(errors) >= 10 and len(valid) >= 5
    assert any(c["warnings"] for c in valid)


@needs_node
def test_controls_json_is_the_viewer_registry() -> None:
    """controls.json (what Python knows of the controls) equals the
    registry in viewer.js; STOMS_WRITE_CONTROLS=1 writes it."""
    registry = _node("profileRegistry()")
    if os.environ.get("STOMS_WRITE_CONTROLS"):
        data = {
            "about": "Generated from CONTROLS and CONTROL_ALIASES in "
            "stoms/web/static/viewer.js (profileRegistry()) for "
            "stoms.viewer.profiles; regenerate with STOMS_WRITE_CONTROLS=1 "
            "(see tests/test_viewer_profile_file.py).",
            **registry,
        }
        CONTROLS_JSON.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        profiles._registry.cache_clear()
    assert profiles.control_registry() == registry, (
        "controls.json is out of date: regenerate it (see this module's docstring)"
    )
    assert registry["neverHide"] == ["embed.settings-toggle"]


@needs_node
def test_builtin_profiles_are_the_same_in_js_and_python() -> None:
    builtins = _node("BUILTIN_PROFILES")
    assert list(builtins) == ["simple", "advanced"]
    for name, profile in builtins.items():
        assert builtin_profile(name) == profile
    assert builtins["simple"]["controls"] == {}
    advanced = builtins["advanced"]["controls"]
    assert set(advanced.values()) == {True}
    assert list(advanced) == _node("Object.keys(CONTROLS)")


@needs_node
def test_builtin_profiles_round_trip() -> None:
    """Each built-in, written as a file and read back by either checker, is
    itself, with no warnings."""
    builtins = _node("BUILTIN_PROFILES")
    docs = [json.loads(json.dumps(p)) for p in builtins.values()]
    for doc, js in zip(docs, _js(docs), strict=True):
        assert js == {"profile": doc, "warnings": []}
        assert _python(doc) == {"profile": doc, "warnings": []}
    with pytest.raises(ValueError, match="simple"):
        builtin_profile("expert")


@needs_node
def test_real_registry_cases_agree() -> None:
    """With the real registry: the settings button cannot be hidden, an
    unknown ID is ignored, a wrong type is an error, in both checkers."""
    docs = [
        {
            "stomsProfile": 1,
            "name": "custom",
            "controls": {
                "cell.matrix": True,
                "cell.repeat": False,
                "embed.settings-toggle": False,
                "cell.hologram": True,
            },
        },
        {
            "stomsProfile": 1,
            "name": "custom",
            "controls": {"cell.matrix": "on"},
        },
    ]
    js = _js(docs)
    assert js == [_python(doc) for doc in docs]
    assert js[0]["profile"]["controls"] == {
        "cell.matrix": True,
        "cell.repeat": False,
    }
    assert js[0]["warnings"] == [
        'Control "embed.settings-toggle" cannot be hidden by a profile; '
        "false ignored.",
        'Unknown control "cell.hologram" ignored (from a newer STOMS, or a typo).',
    ]
    assert "error" in js[1]


# The shown controls of every ID under `profile` (a JS expression), for a few
# data and settings: default settings on water in a cell, a carbon crystal,
# and changed settings (matrix, repeat), and nothing shown at all.
_SHOWN = """(() => {
  const ids = Object.keys(CONTROLS);
  const water = controlContext([{ symbols: ['O', 'H', 'H'], pbc: [true, true, true], cell: [[5, 0, 0], [0, 5, 0], [0, 0, 5]] }]);
  const carbon = controlContext([{ symbols: ['C'], pbc: [true, true, true] }]);
  const none = controlContext([]);
  const plain = normalizePrefs({});
  const changed = normalizePrefs({ repeatMatrix: [[2, 0, 0], [0, 1, 0], [0, 0, 1]], repeat: [2, 2, 1] });
  const shown = (profile) => [water, carbon, none].flatMap((ctx) => [plain, changed].map((prefs) =>
    ids.filter((id) => controlShown(id, profile, ctx, prefs))));
  return %s;
})()"""


@needs_node
def test_builtin_objects_hide_exactly_as_their_names() -> None:
    """controlShown with the built-in profile objects (and a copy read back
    from a file) gives the same as with the names, and as before the format:
    advanced everything, simple the simple, never-hidden and in-use ones."""
    result = _node(
        _SHOWN
        % """{
        names: ['simple', 'advanced'].map(shown),
        objects: ['simple', 'advanced'].map((n) => shown(BUILTIN_PROFILES[n])),
        files: ['simple', 'advanced'].map((n) => shown(checkProfileFile(JSON.parse(JSON.stringify(BUILTIN_PROFILES[n]))).profile)),
        before: [water, carbon, none].flatMap((ctx) => [plain, changed].map((prefs) =>
          ids.filter((id) => controlNeverHidden(id) || controlIsSimple(id, ctx) || controlInUse(id, prefs, ctx)))),
        all: ids,
      }"""
    )
    assert result["objects"] == result["names"] == result["files"]
    simple, advanced = result["names"]
    assert simple == result["before"]
    assert all(shown == result["all"] for shown in advanced)


@needs_node
def test_a_custom_profile_shows_and_hides_what_it_lists() -> None:
    result = _node(
        """(() => {
      const water = controlContext([{ symbols: ['O', 'H', 'H'], pbc: [true, true, true] }]);
      const carbon = controlContext([{ symbols: ['C'], pbc: [true, true, true] }]);
      const plain = normalizePrefs({});
      const repeated = normalizePrefs({ repeat: [2, 2, 1] });
      const custom = checkProfileFile({ stomsProfile: 1, name: 'custom', controls: {
        'cell.matrix': true, 'cell.repeat': false, 'bonds.show': false } }).profile;
      // Not through the checker: false for the settings button anyway.
      const raw = { stomsProfile: 1, name: 'raw', controls: { 'embed.settings-toggle': false } };
      const shown = (id, ctx = water, prefs = plain, p = custom) => controlShown(id, p, ctx, prefs);
      return {
        matrix: shown('cell.matrix'), repeat: shown('cell.repeat'), bonds: shown('bonds.show'),
        repeatInUse: shown('cell.repeat', water, repeated),
        hbondsWater: shown('hbonds.show', water), hbondsCarbon: shown('hbonds.show', carbon),
        unlistedSimple: shown('cell.outline'), unlistedAdvanced: shown('rings.method'),
        settings: shown('embed.settings-toggle', water, plain, raw),
        unknown: shown('no.such-control'),
        hides: ['cell.matrix', 'cell.repeat', 'rings.method', 'embed.settings-toggle', 'no.such']
          .map((id) => profileHides(id, custom, water)),
      };
    })()"""
    )
    assert result == {
        # Listed: shown or hidden whatever the level.
        "matrix": True,
        "repeat": False,
        "bonds": False,
        # A setting in use is shown under every profile.
        "repeatInUse": True,
        # Not listed: the level and data rule, as in simple.
        "hbondsWater": True,
        "hbondsCarbon": False,
        "unlistedSimple": True,
        "unlistedAdvanced": False,
        # No profile hides the settings button; unknown IDs are shown.
        "settings": True,
        "unknown": True,
        "hides": [False, True, True, False, False],
    }


def test_profile_file_format_is_documented() -> None:
    doc = profiles.__doc__ or ""
    assert '"stomsProfile": 1' in doc and "neverHide" in doc
