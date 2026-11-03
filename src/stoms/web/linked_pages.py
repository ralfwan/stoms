"""Linked pages: static web pages about ledger structures, served beside the viewer.

A linked page is a directory produced outside STOMS (for example simulated STM
images) with a ``stoms-link.json`` manifest naming the structures it covers. It
is chosen when the server starts and is never stored in the ledger. The server
serves the directory read-only under ``/linked/<name>/`` so the viewer can link
to it over HTTP; browsers block links from an HTTP page to ``file://`` URLs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

MANIFEST = "stoms-link.json"
SCHEMA = 1
URL_PREFIX = "/linked/"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class LinkedPageError(ValueError):
    """A linked-page directory or its manifest cannot be used."""


@dataclass(frozen=True)
class LinkedPage:
    """One linked-page directory and the structures its manifest lists."""

    name: str
    title: str
    description: str
    directory: Path
    entry: str
    fragment: str
    structure_ids: frozenset[str]

    @property
    def url_template(self) -> str:
        """The page's address with ``{structure_id}`` still in its fragment.

        It is relative, like the viewer's API calls, so it also works when the
        server sits behind a proxy under a path prefix.
        """
        path = f"{URL_PREFIX}{self.name}/{quote(self.entry)}".lstrip("/")
        return f"{path}#{self.fragment}"

    def url(self, structure_id: str) -> str:
        """The address of this page for one structure."""
        # Only the ID is encoded: the fragment's own '=' or '&' stay readable
        # for the page.
        return self.url_template.replace(
            "{structure_id}", quote(structure_id, safe="")
        )

    def file(self, relative: str) -> Path | None:
        """The served file at ``relative``, or None outside the directory.

        Symbolic links are resolved first, so neither ``..`` nor a link can
        reach a file outside the directory. Hidden files and folders (``.git``,
        ``.env``) are never served.
        """
        try:
            path = (self.directory / relative).resolve()
            if not path.is_relative_to(self.directory) or not path.is_file():
                return None
            if any(
                part.startswith(".")
                for part in path.relative_to(self.directory).parts
            ):
                return None
        except (OSError, ValueError):  # unreadable, or a NUL byte in the path
            return None
        return path


def load_linked_page(directory: Path) -> LinkedPage:
    """Read the manifest in ``directory``."""
    if not directory.is_dir():
        raise LinkedPageError(f"linked page is not a directory: {directory}")
    root = directory.resolve()
    manifest_path = root / MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LinkedPageError(
            f"linked page has no {MANIFEST}: {directory}"
        ) from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LinkedPageError(
            f"cannot read {manifest_path}: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise LinkedPageError(f"{manifest_path}: expected a JSON object")

    def text(key: str, default: str | None = None) -> str:
        value = manifest.get(key, default)
        if not isinstance(value, str) or not value:
            raise LinkedPageError(
                f"{manifest_path}: {key!r} must be a non-empty string"
            )
        return value

    if manifest.get("schema") != SCHEMA:
        raise LinkedPageError(
            f"{manifest_path}: unsupported schema {manifest.get('schema')!r} "
            f"(expected {SCHEMA})"
        )
    name = text("name")
    if not _NAME.fullmatch(name):
        raise LinkedPageError(
            f"{manifest_path}: name {name!r} may use only letters, digits, "
            "'.', '_' and '-'"
        )
    fragment = text("fragment", "{structure_id}")
    if "{structure_id}" not in fragment:
        raise LinkedPageError(
            f"{manifest_path}: fragment must contain {{structure_id}}"
        )
    ids: Any = manifest.get("structure_ids")
    if not isinstance(ids, list) or not all(
        isinstance(item, str) and item for item in ids
    ):
        raise LinkedPageError(
            f"{manifest_path}: 'structure_ids' must be a list of strings"
        )
    description = manifest.get("description", "")
    if not isinstance(description, str):
        raise LinkedPageError(
            f"{manifest_path}: 'description' must be a string"
        )
    page = LinkedPage(
        name=name,
        title=text("title"),
        description=description,
        directory=root,
        entry=text("entry", "index.html"),
        fragment=fragment,
        structure_ids=frozenset(ids),
    )
    if page.file(page.entry) is None:
        raise LinkedPageError(
            f"{manifest_path}: entry {page.entry!r} is not a file in {directory}"
        )
    return page


def load_linked_pages(directories: list[Path]) -> tuple[LinkedPage, ...]:
    """Read every manifest; names must be unique, as they form the URLs."""
    pages = tuple(load_linked_page(directory) for directory in directories)
    seen: dict[str, Path] = {}
    for page in pages:
        if page.name in seen:
            raise LinkedPageError(
                f"two linked pages are named {page.name!r}: "
                f"{seen[page.name]} and {page.directory}"
            )
        seen[page.name] = page.directory
    return pages
