"""View ASE structures with the STOMS viewer, in Jupyter or a browser.

    from stoms.viewer import view
    viewer = view(atoms)        # or a list of Atoms, a Trajectory, a file name
    viewer                      # shown inline in a notebook
    viewer.save("figure.svg")   # in a later cell: the view as vector graphics

No ledger is involved. The link back to Python (``Viewer``) needs anywidget
(``pip install 'stoms[jupyter]'``); without it, ``view`` returns a
``StaticView``, which is interactive in the browser but not linked.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .base import read_settings
from .document import DEFAULT_HEIGHT
from .frames import MAX_FRAMES
from .static import StaticView

if TYPE_CHECKING:
    from .widget import StaleViewError, Viewer

__all__ = [
    "MAX_FRAMES",
    "StaleViewError",
    "StaticView",
    "Viewer",
    "view",
    "view_phonons",
]


def _look(
    settings: Any, width: int | None, height: int | None
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Settings, camera and measurements from ``settings``, with the panel
    size given."""
    prefs, camera, measurements = read_settings(settings)
    if width is not None or height is not None:
        size = dict(prefs.get("panelSize") or {})
        if width is not None:
            size["width"] = width
        if height is not None:
            size["height"] = height
        prefs["panelSize"] = size
    return prefs, camera, measurements


def view(
    images: Any,
    *,
    settings: Any = None,
    frame: int = 0,
    width: int | None = None,
    height: int | None = None,
    static: bool = False,
    title: str = "STOMS viewer",
    profile: str = "simple",
) -> Viewer | StaticView:
    """Show ``images`` in the STOMS viewer.

    ``images`` is an ``ase.Atoms``, a list of them, an ASE Trajectory (or any
    iterable of Atoms), or a structure file ASE reads (all its frames). The
    Atoms are copied; they are not changed.

    ``settings`` is another viewer's ``get_settings()``, a viewer settings
    file (or its path) or a settings dictionary: the same look and, if
    included, the same view and measurements. ``width`` and ``height`` set the panel size in
    pixels, which is also the size of saved images. ``profile`` chooses the
    controls shown: ``"simple"`` (the default) or ``"advanced"`` (all); see
    ``viewer.profile``.

    Returns a ``Viewer`` (a widget linked to Python), or a ``StaticView``
    with ``static=True`` or when anywidget is not installed.
    """
    prefs, camera, measurements = _look(settings, width, height)
    if not static:
        try:
            from .widget import Viewer
        except ImportError:
            warnings.warn(
                "anywidget is not installed, so the viewer is not linked to "
                "Python (no viewer.save('x.svg'), frame or settings sync); "
                "install it with: pip install 'stoms[jupyter]'",
                stacklevel=2,
            )
        else:
            return Viewer(
                images,
                frame=frame,
                settings=prefs,
                camera=camera,
                measurements=measurements,
                height=DEFAULT_HEIGHT,
                title=title,
                profile=profile,
            )
    return StaticView(
        images,
        frame=frame,
        settings=prefs,
        camera=camera,
        measurements=measurements,
        height=DEFAULT_HEIGHT,
        title=title,
        profile=profile,
    )


def view_phonons(
    source: Any,
    *,
    band: str | None = None,
    band_labels: str | None = None,
    settings: Any = None,
    width: int | None = None,
    height: int | None = None,
    title: str | None = None,
    profile: str = "simple",
    **inputs: Any,
) -> Viewer:
    """Show a phonopy calculation: its primitive cell, vibrational modes at
    any q, the band structure and the DOS, as ``stoms --file ... serve``.

    ``source`` is a phonopy yaml (``phonopy_params.yaml``), a structure file
    with ``dim`` and ``force_constants`` (or ``force_sets``), a
    ``phonopy.Phonopy`` object, or a ``stoms.web.phonons.PhononModel``.
    ``inputs`` are the options of ``stoms.web.phonons.load_phonopy``:
    ``dim``, ``force_constants``, ``force_sets``, ``born``, ``dos_mesh`` and
    ``calculator``. ``band`` is a band path in phonopy's BAND syntax (default:
    seekpath's), ``band_labels`` names its points. The other arguments are
    those of :func:`view`.

    Python computes what the viewer asks for (phonopy), so the viewer needs
    its kernel; saved HTML files keep Γ, the bands and the DOS. Needs
    anywidget and phonopy: ``pip install 'stoms[jupyter,phonopy]'``.
    """
    try:
        from .widget import Viewer
    except ImportError as error:
        raise ImportError(
            "view_phonons() needs anywidget: pip install "
            "'stoms[jupyter,phonopy]'"
        ) from error
    from .phonons import phonon_model

    model = phonon_model(source, band=band, band_labels=band_labels, **inputs)
    prefs, camera, measurements = _look(settings, width, height)
    if title is None:
        title = (
            f"Phonons · {Path(source).name}"
            if isinstance(source, str | os.PathLike)
            else "Phonons"
        )
    return Viewer(
        model.atoms,
        settings=prefs,
        camera=camera,
        measurements=measurements,
        height=DEFAULT_HEIGHT,
        title=title,
        phonons=model,
        profile=profile,
    )


def __getattr__(name: str) -> Any:
    # The widget needs anywidget, an optional dependency.
    if name in ("Viewer", "StaleViewError"):
        from . import widget

        return getattr(widget, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
