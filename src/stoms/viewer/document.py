"""The viewer as one self-contained HTML document.

The document inlines the viewer's own stylesheet and scripts (``app.css``,
``dom.js``, ``viewer.js``) with ``embed.js``, a compact host page, and the
frames as JSON. It needs no server: the same document is shown in a notebook
(in an iframe), opened in a browser tab, or saved as a file.
"""

from __future__ import annotations

import html
import json
import uuid
from functools import cache
from importlib import resources
from typing import Any

# Embedded in this order; embed.js runs last and builds the page.
STYLES = ("app.css", "embed.css")
SCRIPTS = ("dom.js", "viewer.js", "embed.js")
DEFAULT_HEIGHT = 440


@cache
def _static(name: str) -> str:
    # Not resources.files("stoms.web"): importing that package loads the
    # ledger server.
    return (
        resources.files("stoms")
        .joinpath("web", "static", name)
        .read_text(encoding="utf-8")
    )


def _script_json(value: Any) -> str:
    """JSON that is safe inside a <script> element."""
    text = json.dumps(value, separators=(",", ":"), allow_nan=False)
    return (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def _script_text(source: str) -> str:
    # A script element ends at the first "</script"; the sources have none,
    # but a future edit must not end it early.
    return source.replace("</script", "<\\/script")


def embed_data(
    frames: list[dict[str, Any]],
    *,
    frame: int = 0,
    settings: dict[str, Any] | None = None,
    camera: dict[str, Any] | None = None,
    profile: str = "simple",
    title: str = "STOMS viewer",
    bridge: bool = False,
    height: int = DEFAULT_HEIGHT,
    api: dict[str, Any] | None = None,
    measurements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """What embed.js reads (``STOMS_EMBED``). ``bridge`` links the page to a
    notebook widget through messages to its parent window. ``api`` holds
    replies to requests the page would send its kernel (by request path);
    ``measurements`` the measurements to show (see embed.js); ``profile``
    the controls shown ("simple" or "advanced"; not a setting)."""
    return {
        "frames": frames,
        "frame": frame,
        "settings": settings or {},
        "camera": camera or {},
        "profile": profile,
        "title": title,
        "bridge": bridge,
        "height": height,
        "api": api or {},
        "measurements": measurements or [],
    }


def document(data: dict[str, Any]) -> str:
    """The HTML document for ``data`` (see embed_data)."""
    styles = "\n".join(_static(name) for name in STYLES)
    scripts = "\n".join(
        f"<script>\n{_script_text(_static(name))}\n</script>"
        for name in SCRIPTS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(data.get("title") or "STOMS viewer")}</title>
<style>
{styles}
</style>
</head>
<body class="embed-page">
<div id="stoms-root"></div>
<script type="application/json" id="stoms-data">{_script_json(data)}</script>
<script>var STOMS_EMBED = JSON.parse(document.getElementById("stoms-data").textContent);</script>
{scripts}
</body>
</html>
"""


def iframe_html(document_text: str, height: int) -> str:
    """``document_text`` in an iframe, for a notebook's HTML output.

    The script sizes the iframe to its page, which posts its height.
    """
    frame_id = f"stoms-{uuid.uuid4().hex[:12]}"
    return (
        f'<iframe id="{frame_id}" title="STOMS viewer" '
        f'style="width:100%;height:{int(height) + 60}px;border:0;display:block" '
        f'srcdoc="{html.escape(document_text, quote=True)}"></iframe>\n'
        "<script>(() => {\n"
        f'  const frame = document.getElementById("{frame_id}");\n'
        '  window.addEventListener("message", (event) => {\n'
        "    const m = event.data;\n"
        "    if (frame && event.source === frame.contentWindow && m && m.stoms"
        ' && m.type === "size") frame.style.height = `${m.height}px`;\n'
        "  });\n"
        "})();</script>"
    )
