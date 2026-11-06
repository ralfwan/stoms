"""The notebook viewer as a widget (anywidget), linked to Python."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anywidget
import traitlets

from .base import ViewerBase, check_measurements, check_view
from .document import DEFAULT_HEIGHT, document
from .frames import as_images, frame_payload
from .static import _frame_index

if TYPE_CHECKING:
    from ..web.phonons import PhononModel


class StaleViewError(RuntimeError):
    """The browser has not drawn the viewer's current state yet."""


class Viewer(ViewerBase, anywidget.AnyWidget):
    """STOMS viewer in a notebook, linked to Python.

    ``frame``, ``settings`` and ``camera`` are synced both ways: what you
    change in the viewer is seen here once the cell has finished, and what
    you set here is shown at once. The browser draws, so SVG images come from
    the browser too: after every change it sends the SVG of what it shows,
    which ``save()`` writes.
    """

    _esm = Path(__file__).with_name("widget.js")
    _document = traitlets.Unicode("").tag(sync=True)
    frame = traitlets.Int(0).tag(sync=True)
    settings = traitlets.Dict().tag(sync=True)
    camera = traitlets.Dict().tag(sync=True)
    # The browser's last drawing: {"state": {frame, settings, camera}, "svg"}.
    _snapshot = traitlets.Dict().tag(sync=True)
    # Measurements made in the browser (📏), with their values; see measurements.
    _measurements: traitlets.List[dict[str, Any]] = traitlets.List().tag(
        sync=True
    )

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
        phonons: PhononModel | None = None,
    ) -> None:
        self._images = as_images(images)
        self._frames = [
            frame_payload(atoms, i) for i, atoms in enumerate(self._images)
        ]
        self._phonons = phonons
        if phonons is not None:
            if len(self._frames) != 1:
                raise ValueError("phonons belong to one structure")
            # The page then shows the vibration panel and the band plot.
            self._frames[0].update(has_modes=True, has_phonons=True)
        self._height = height
        self._title = title
        super().__init__(
            frame=_frame_index(frame, len(self._images)),
            settings=copy.deepcopy(settings or {}),
            camera=copy.deepcopy(camera or {}),
            # Values follow from the page's first snapshot.
            _measurements=check_measurements(measurements or []),
        )
        self._document = document(self._data(bridge=True))
        self.on_msg(self._on_message)

    @property
    def phonons(self) -> PhononModel | None:
        """The phonon calculation behind the vibration panel, if any."""
        return self._phonons

    def _on_message(self, _: Any, content: Any, buffers: Any) -> None:
        """Requests of the page: what ``stoms serve`` computes on request
        (phonons). Replies carry the request's ``id``."""
        if not isinstance(content, dict) or content.get("type") != "api":
            return
        reply: dict[str, Any] = {"type": "api", "id": content.get("id")}
        try:
            if self._phonons is None:
                raise LookupError("this viewer has no phonon calculation")
            from .phonons import answer

            reply["data"] = answer(self._phonons, str(content.get("path")))
        except Exception as error:  # reported in the viewer
            reply["error"] = str(error) or type(error).__name__
        self.send(reply)

    @property
    def measurements(self) -> list[dict[str, Any]]:
        result = []
        for item in self._measurements:
            atoms = item.get("atoms") or []
            entry = {
                "kind": item.get("kind"),
                "atoms": [ref.get("index") for ref in atoms],
                "images": [
                    tuple(ref.get("image") or (0, 0, 0)) for ref in atoms
                ],
                "value": item.get("value"),
                "unit": "Å" if item.get("kind") == "distance" else "°",
            }
            if item.get("kind") == "distance":
                entry["nearest"] = item.get("nearest")
            result.append(entry)
        return result

    def _measurement_items(self) -> list[dict[str, Any]]:
        return [
            {"kind": item.get("kind"), "atoms": item.get("atoms")}
            for item in self._measurements
        ]

    def _api_cache(self) -> dict[str, Any]:
        if self._phonons is None:
            return {}
        from .phonons import initial_answers

        return initial_answers(self._phonons)

    @traitlets.validate("frame")
    def _valid_frame(self, proposal: Any) -> int:
        try:
            return _frame_index(proposal["value"], len(self._images))
        except (TypeError, IndexError) as error:
            raise traitlets.TraitError(str(error)) from None

    def set_images(self, images: Any) -> None:
        """Show other frames, keeping the settings and the view."""
        found = as_images(images)
        frames = [frame_payload(atoms, i) for i, atoms in enumerate(found)]
        self._images, self._frames = found, frames
        self._phonons = None  # they belonged to the old structure
        with self.hold_sync():
            self.frame = min(self.frame, len(found) - 1)
            self._measurements = []
            self._snapshot = {}
            self._document = document(self._data(bridge=True))

    def set_view(self, name: str) -> None:
        """Turn the view: "top", "side-a", "side-b", or along an axis ("a",
        "b", "c", "x", "y", "z"; "-c" from the other side).

        The browser turns it, so the viewer must be displayed; ``camera``
        holds the new view once the cell has finished.
        """
        self.send({"type": "view", "name": check_view(name)})

    def _state(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "settings": self.settings,
            "camera": self.camera,
        }

    def to_svg(self) -> str:
        """The SVG image the browser drew for the current state.

        Raises StaleViewError when nothing was drawn yet, or the state was
        changed from Python in the running cell (the browser's drawing of it
        arrives once the cell has finished).
        """
        snapshot = self._snapshot
        if not snapshot or "svg" not in snapshot:
            raise StaleViewError(
                "no SVG has been drawn yet: the browser draws it. Display "
                "the viewer (end a cell with it), then save in a later cell."
            )
        if snapshot.get("state") != self._state():
            raise StaleViewError(
                "the browser has not drawn the latest changes yet (made in "
                "this cell?); Jupyter delivers its drawing when the cell has "
                "finished: call save() in the next cell"
            )
        return str(snapshot["svg"])

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Write the view as an ``.svg`` image (vector graphics, as shown)
        or as a standalone, interactive ``.html`` file."""
        target = Path(path)
        suffix = target.suffix.lower()
        if suffix == ".svg":
            target.write_text(self.to_svg(), encoding="utf-8")
            return target
        if suffix in (".html", ".htm"):
            return self._save_html(target)
        raise ValueError(
            f"save() writes .svg or .html files, not {target.suffix!r}"
        )
