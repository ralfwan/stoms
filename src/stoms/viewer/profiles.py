"""Profile files of the viewer's GUI profiles (format version 1).

A GUI profile chooses which of the viewer's controls are shown; it never
changes a setting. Built in are ``"simple"`` and ``"advanced"``
(``viewer.profile``); a profile file describes one in JSON::

    {"stomsProfile": 1, "name": "my profile",
     "controls": {"cell.matrix": true, "cell.repeat": false}}

``controls`` maps control IDs (``CONTROLS`` in ``stoms/web/static/viewer.js``)
to ``true`` (shown) or ``false`` (hidden). A control not listed follows its
built-in level and data rule, as in simple, so controls added after a file
was saved fall back to their level. An ID this version does not know is
ignored, so a file from a newer STOMS loads here; an old ID (renamed control,
``CONTROL_ALIASES``) counts as its new one unless the file names the new one
too. No profile hides a control marked ``neverHide`` (the notebook's
settings button, where the profile switch is): ``false`` for it is ignored.
A setting in use (differing from its default) is shown under every profile.
Simple is ``{"controls": {}}``, advanced lists every control as ``true``.

``check_profile_file`` mirrors ``checkProfileFile`` in viewer.js: the same
documents give the same profile, warnings and error messages
(``tests/data/profile_files.json`` runs through both). The control IDs come
from ``controls.json`` next to this module, generated from the registry in
viewer.js (a test keeps it equal; see ``tests/test_viewer_profile_file.py``).
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

PROFILE_FORMAT = 1
_REGISTRY = Path(__file__).with_name("controls.json")


@cache
def _registry() -> dict[str, Any]:
    data = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    return {key: data[key] for key in ("ids", "aliases", "neverHide")}


def control_registry() -> dict[str, Any]:
    """The viewer's control IDs, old IDs (old -> new) and the IDs no profile
    hides: ``{"ids": [...], "aliases": {...}, "neverHide": [...]}``."""
    registry = _registry()
    return {
        "ids": list(registry["ids"]),
        "aliases": dict(registry["aliases"]),
        "neverHide": list(registry["neverHide"]),
    }


def builtin_profile(name: str) -> dict[str, Any]:
    """The built-in profile ``name`` ("simple" or "advanced") in the file
    format."""
    if name == "simple":
        controls: dict[str, bool] = {}
    elif name == "advanced":
        controls = dict.fromkeys(_registry()["ids"], True)
    else:
        raise ValueError(f'profile is "simple" or "advanced", not {name!r}')
    return {"stomsProfile": PROFILE_FORMAT, "name": name, "controls": controls}


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, (list, tuple)):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def _fail(message: str) -> None:
    raise ValueError(f"Invalid STOMS profile: {message}")


def check_profile_file(
    doc: Any, registry: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[str]]:
    """The profile in the file ``doc`` (parsed JSON) and what was ignored.

    Returns ``(profile, warnings)``: ``profile`` is
    ``{"stomsProfile": 1, "name": ..., "controls": {...}}`` with only known
    current IDs (old ones renamed; unknown ones and ``false`` for a control
    no profile hides dropped); ``warnings`` says what was ignored, in the
    file's order. Raises ValueError saying what is wrong for a wrong type, a
    missing field or another format version. ``registry`` as
    ``control_registry()`` (tests use their own).
    """
    if registry is None:
        registry = _registry()
    if not isinstance(doc, dict):
        _fail(f"expected a JSON object, got {_kind(doc)}.")
    if "stomsProfile" not in doc:
        _fail('"stomsProfile" (the format version) is missing.')
    version = doc["stomsProfile"]
    if isinstance(version, bool) or not isinstance(version, (int, float)):
        _fail(
            f'"stomsProfile" must be the number {PROFILE_FORMAT}, '
            f"got {_kind(version)}."
        )
    if version != PROFILE_FORMAT:
        _fail(
            f"this STOMS reads format version {PROFILE_FORMAT} only "
            f'("stomsProfile": {PROFILE_FORMAT}).'
        )
    if "name" not in doc:
        _fail('"name" is missing.')
    name = doc["name"]
    if not isinstance(name, str):
        _fail(f'"name" must be a string, got {_kind(name)}.')
    if not name:
        _fail('"name" is empty.')
    if "controls" not in doc:
        _fail('"controls" is missing.')
    listed = doc["controls"]
    if not isinstance(listed, dict):
        _fail(
            f'"controls" must be an object of control IDs, got {_kind(listed)}.'
        )
    for key, value in listed.items():
        if not isinstance(value, bool):
            _fail(
                f'control "{key}" must be true or false, got {_kind(value)}.'
            )
    ids, never_hide = set(registry["ids"]), set(registry["neverHide"])
    aliases = registry["aliases"]
    controls: dict[str, bool] = {}
    warnings: list[str] = []
    for key, value in listed.items():
        current = aliases.get(key, key)
        if current not in ids:
            warnings.append(
                f'Unknown control "{key}" ignored (from a newer STOMS, or a typo).'
            )
            continue
        # The new ID wins over its old one.
        if current != key and current in listed:
            continue
        if not value and current in never_hide:
            warnings.append(
                f'Control "{key}" cannot be hidden by a profile; false ignored.'
            )
            continue
        controls[current] = value
    profile = {
        "stomsProfile": PROFILE_FORMAT,
        "name": name,
        "controls": controls,
    }
    return profile, warnings
