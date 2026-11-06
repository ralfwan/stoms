"""Load phonopy v_sim mode files into a ledger so the viewer can animate them.

The structure becomes one ledger structure, in an aggregation named after
the file or directory. Its modes are not stored in the ledger: they stay
with the server, keyed by structure ID, and the viewer reads them from
``/api/structures/<id>/modes``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..atomsledger import (
    Aggregation,
    AggregationMemberInput,
    AtomsLedger,
    Provenance,
    StructureSourceSpec,
)
from ..parsers.v_sim import Modes, VSimParseError, read_many
from .access import AccessOptions

CREATED_BY = "stoms serve"
SUFFIX = ".ascii"


def is_v_sim(path: Path) -> bool:
    """Whether ``--file`` names v_sim input: an .ascii file or a directory."""
    return path.is_dir() or path.suffix.lower() == SUFFIX


def v_sim_files(path: Path) -> list[Path]:
    """The file itself, or a directory's .ascii files sorted by name."""
    if not path.is_dir():
        return [path]
    files = sorted(
        p for p in path.iterdir() if p.is_file() and p.suffix.lower() == SUFFIX
    )
    if not files:
        raise VSimParseError(f"{path} contains no {SUFFIX} files")
    return files


def load_v_sim(
    ledger: AtomsLedger, path: Path
) -> tuple[Aggregation, dict[str, tuple[Modes, ...]]]:
    """Add the structure of ``path`` to ``ledger``; return it with its modes."""
    files = v_sim_files(path)
    atoms, modes = read_many(files)
    source = StructureSourceSpec(kind="file", name=path.name, tool="v_sim")
    [structure_id] = ledger.add_structures(
        [
            {
                "atoms": atoms,
                "provenance": Provenance(
                    created_by=CREATED_BY,
                    purpose=f"structure of {path.name}",
                    metadata={"file": str(path), "files": len(files)},
                ),
            }
        ],
        source_spec=source,
        allow_equivalent_atoms=True,
    )
    aggregation = ledger.create_aggregation(
        name=path.name,
        description=f"Vibrational modes from {path}",
        members=[AggregationMemberInput(structure_id, None)],
        metadata={"file": str(path), "qpoints": len(modes)},
    )
    return aggregation, {structure_id: tuple(modes)}


def serve_v_sim(
    path: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    access: AccessOptions | None = None,
) -> None:
    """Serve the viewer for one v_sim file or a directory of them."""
    from .server import create_server, run

    with tempfile.TemporaryDirectory(prefix="stoms-v_sim-") as directory:
        ledger = AtomsLedger(Path(directory) / "view.ledger")
        aggregation, modes = load_v_sim(ledger, path)
        [structure_id] = modes
        server = create_server(
            ledger,
            str(path),
            host=host,
            port=port,
            modes=modes,
            access=access,
        )
        run(
            server,
            path,
            open_browser=open_browser,
            page=f"#/structures/{structure_id}?from={aggregation.id}",
        )
