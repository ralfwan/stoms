"""Phonons in the notebook viewer: the browser asks, phonopy answers.

The viewer's vibration panel and band plot (viewer.js) ask for modes at a
q-point, the band structure and the DOS, as they ask ``stoms serve``. In a
notebook these requests travel over the widget's link to the kernel, and
:func:`answer` computes them with the same :class:`PhononModel` the server
uses. No ledger is created.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from ..web.phonons import PhononModel

# The one structure of a phonon view (frame 0).
STRUCTURE_ID = "frame-0"


def phonon_model(
    source: Any,
    *,
    band: str | None = None,
    band_labels: str | None = None,
    **inputs: Any,
) -> PhononModel:
    """A PhononModel from a phonopy yaml (or structure file with ``inputs``
    such as ``dim`` and ``force_constants``), a ``phonopy.Phonopy`` object, or
    a PhononModel.

    ``band`` is a band path in phonopy's BAND syntax (default: seekpath's),
    ``band_labels`` names its points. ``inputs`` are the keyword arguments of
    :func:`stoms.web.phonons.load_phonopy` (``dim``, ``force_constants``,
    ``force_sets``, ``born``, ``dos_mesh``, ``calculator``).
    """
    from ..web.phonons import PhononModel, load_phonopy, parse_band

    path = parse_band(band, band_labels) if band is not None else None
    if isinstance(source, PhononModel):
        if band is not None or inputs:
            raise TypeError("a PhononModel takes no band or loading options")
        return source
    if isinstance(source, str | os.PathLike):
        for key in ("force_constants", "force_sets", "born"):
            if inputs.get(key) is not None:
                inputs[key] = Path(inputs[key])
        if "dim" in inputs and not isinstance(inputs["dim"], str | None):
            inputs["dim"] = " ".join(str(n) for n in _flat(inputs["dim"]))
        if "dos_mesh" in inputs and not isinstance(
            inputs["dos_mesh"], str | None
        ):
            inputs["dos_mesh"] = " ".join(
                str(n) for n in _flat(inputs["dos_mesh"])
            )
        return load_phonopy(Path(source), path, **inputs)
    if type(source).__name__ == "Phonopy":
        if inputs:
            raise TypeError(
                "a Phonopy object takes no loading options: "
                f"{', '.join(inputs)}"
            )
        if source.force_constants is None:
            source.produce_force_constants()
        return PhononModel(source, path)
    raise TypeError(
        "view_phonons() takes a phonopy yaml or structure file, a "
        f"phonopy.Phonopy object or a PhononModel, not {type(source).__name__}"
    )


def _flat(value: Any) -> list[Any]:
    if isinstance(value, int | float):
        return [value]
    return [x for item in value for x in _flat(item)]


def _vector(text: str, name: str) -> tuple[float, float, float]:
    try:
        values = tuple(float(x) for x in text.split(","))
    except ValueError:
        values = ()
    if len(values) != 3 or not all(map(math.isfinite, values)):
        raise ValueError(f"expected {name} as three numbers, got {text!r}")
    return values  # type: ignore[return-value]


def _nac(text: str | None) -> bool:
    if text in (None, "1"):
        return True
    if text == "0":
        return False
    raise ValueError(f"expected nac as 0 or 1, got {text!r}")


def answer(model: PhononModel, request: str) -> dict[str, Any]:
    """The reply to one request of the viewer page, as ``stoms serve``
    would send it (``structures/frame-0/modes?q=…``, ``…/phonons/bands``,
    ``…/phonons/dos``)."""
    url = urlsplit(request)
    query = parse_qs(url.query)

    def one(name: str) -> str | None:
        return query.get(name, [None])[0]

    match url.path.strip("/").split("/"):
        case ["structures", structure_id, "modes"] if (
            structure_id == STRUCTURE_ID
        ):
            q = _vector(one("q") or "0,0,0", "q")
            direction = one("direction")
            towards = (
                None if direction is None else _vector(direction, "direction")
            )
            return {
                "structure_id": STRUCTURE_ID,
                "unit": "THz",
                "any_q": True,
                "qpoints": [model.modes(q, towards, _nac(one("nac")))],
            }
        case ["structures", structure_id, "phonons", "bands"] if (
            structure_id == STRUCTURE_ID
        ):
            return model.bands(_nac(one("nac")))
        case ["structures", structure_id, "phonons", "dos"] if (
            structure_id == STRUCTURE_ID
        ):
            return model.dos(_nac(one("nac")))
    raise LookupError(f"the notebook viewer cannot answer {request!r}")


def initial_answers(model: PhononModel) -> dict[str, dict[str, Any]]:
    """Replies the page asks for first (modes at Γ, bands, DOS), stored in
    saved HTML files, which have no kernel to ask."""
    replies = {}
    base = f"structures/{STRUCTURE_ID}"
    for request in (
        f"{base}/modes",
        f"{base}/phonons/bands",
        f"{base}/phonons/dos",
    ):
        try:
            replies[request] = answer(model, request)
        except Exception:  # the page reports what is missing
            continue
    return replies
