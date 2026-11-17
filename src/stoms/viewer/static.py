"""A viewer without a link back to Python (no anywidget needed)."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from .base import DEFAULT_PROFILE, ViewerBase, check_measurements
from .document import DEFAULT_HEIGHT, iframe_html
from .frames import as_images, frame_payload


class StaticView(ViewerBase):
    """The viewer as HTML output: interactive in the browser, but what you
    change there does not come back to Python.

    Its ``settings``, ``camera``, ``frame`` and ``profile`` are what it was created with
    (or set afterwards, before it is displayed again). SVG images are saved
    with the viewer's "Save SVG" button; ``save()`` writes HTML only.
    """

    def __init__(
        self,
        images: Any,
        *,
        frame: int = 0,
        settings: dict[str, Any] | None = None,
        camera: dict[str, Any] | None = None,
        measurements: list[dict[str, Any]] | None = None,
        height: int = DEFAULT_HEIGHT,
        title: str = "STOMS viewer",
        profile: str = DEFAULT_PROFILE,
    ) -> None:
        self._images = as_images(images)
        self._frames = [
            frame_payload(atoms, i) for i, atoms in enumerate(self._images)
        ]
        self._height = height
        self._title = title
        self.settings = copy.deepcopy(settings or {})
        self.camera = copy.deepcopy(camera or {})
        self._measurements = check_measurements(measurements or [])
        self.frame = frame
        self.profile = profile

    @property
    def frame(self) -> int:
        """The index of the shown frame (negative counts from the end)."""
        return self._frame

    @frame.setter
    def frame(self, value: int) -> None:
        self._frame = _frame_index(value, len(self._images))

    def _measurement_items(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._measurements)

    def _repr_html_(self) -> str:
        height = (self.panel_size[1] or self._height) + 60
        return iframe_html(self.to_html(), height)

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Write the viewer as a standalone ``.html`` file."""
        target = Path(path)
        if target.suffix.lower() in (".html", ".htm"):
            return self._save_html(target)
        if target.suffix.lower() == ".svg":
            raise ValueError(
                "a StaticView cannot save SVG from Python: the browser draws "
                "it. Use the viewer's Save SVG button, or install "
                "anywidget (pip install 'stoms[jupyter]') for viewer.save()."
            )
        raise ValueError(f"save() writes .html files, not {target.suffix!r}")


def _frame_index(value: Any, count: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"frame is a whole number, not {value!r}")
    if not -count <= value < count:
        raise IndexError(
            f"there is no frame {value}: "
            f"{count} frame{'s' if count != 1 else ''}"
        )
    return value % count
