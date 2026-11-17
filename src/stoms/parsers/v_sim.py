"""Read and write phonopy's v_sim mode files (``anime.ascii``).

phonopy writes them with ``ANIME_TYPE = V_SIM`` (``Animation.write_v_sim``):

```
# Phonopy generated file for v_sim 3.6
   dxx   dyx   dyy                       lower-triangular cell, Angstrom
   dzx   dzy   dzz
   x  y  z  Sym                          one line per atom, Cartesian
#metaData: qpt=[qx;qy;qz;omega \\         one block per mode
#; Re(ux); Re(uy); Re(uz); Im(ux); Im(uy); Im(uz) \\    one line per atom
# ]
```

The q-point is in reduced coordinates of the file's cell and ``omega`` is in
THz, negative for imaginary modes. The displacements are eigenvector / sqrt(mass)
as phonopy computes them: a copy of atom j at fractional position
r = n + x_j (lattice vector n) moves with exp(2 pi i q.r).

Only this phonopy subset of the v_sim format is read; other ``#keyword:``
lines are rejected.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ase import Atoms

HEADER = "# Phonopy generated file for v_sim 3.6"


class VSimParseError(ValueError):
    """The file is not a phonopy v_sim file."""


@dataclass(frozen=True)
class Modes:
    """All modes at one q-point.

    ``qpoint`` has shape (3,), ``frequencies`` (nmodes,) in THz, and
    ``displacements`` is complex with shape (nmodes, natoms, 3).
    """

    qpoint: np.ndarray
    frequencies: np.ndarray
    displacements: np.ndarray


def read(path: Path | str) -> tuple[Atoms, list[Modes]]:
    """The structure of a v_sim file and its modes, grouped by q-point."""
    path = Path(path)
    try:
        lines = path.read_text().splitlines()
    except UnicodeDecodeError as error:
        raise VSimParseError(f"{path} is not a text file") from error
    body = [
        (number, line.strip())
        for number, line in enumerate(lines, start=1)
        if line.strip()
    ]
    if not body or not body[0][1].startswith("#"):
        raise VSimParseError(
            f"{path}: line 1: expected a '#' comment line (v_sim header)"
        )
    body = body[1:]

    def numbers(number: int, line: str, count: int, what: str) -> list[float]:
        fields = line.split()
        try:
            return [float(value) for value in fields[:count]]
        except ValueError:
            raise VSimParseError(
                f"{path}: line {number}: expected {what}, got {line!r}"
            ) from None

    if len(body) < 2 or any(line.startswith("#") for _, line in body[:2]):
        raise VSimParseError(
            f"{path}: expected two cell lines after the header"
        )
    (n1, l1), (n2, l2) = body[:2]
    if len(l1.split()) != 3 or len(l2.split()) != 3:
        raise VSimParseError(
            f"{path}: line {n1}: expected two cell lines of three numbers"
        )
    dxx, dyx, dyy = numbers(n1, l1, 3, "dxx dyx dyy")
    dzx, dzy, dzz = numbers(n2, l2, 3, "dzx dzy dzz")
    cell = [[dxx, 0.0, 0.0], [dyx, dyy, 0.0], [dzx, dzy, dzz]]

    symbols: list[str] = []
    positions: list[list[float]] = []
    blocks: list[tuple[int, str]] = []
    block: list[str] | None = None
    start = 0
    for number, line in body[2:]:
        if block is not None:
            block.append(line.lstrip("#"))
            if "]" in line:
                blocks.append((start, " ".join(block)))
                block = None
        elif line.startswith("#metaData:"):
            start, block = number, [line.split(":", 1)[1]]
            if "]" in line:
                blocks.append((start, " ".join(block)))
                block = None
        elif line.startswith("#keyword:"):
            raise VSimParseError(
                f"{path}: line {number}: {line!r} is not supported; only "
                "phonopy's v_sim files (Cartesian, no keywords) can be read"
            )
        elif line.startswith("#"):
            continue
        elif blocks:
            raise VSimParseError(
                f"{path}: line {number}: atom line after the modes"
            )
        else:
            fields = line.split()
            if len(fields) != 4:
                raise VSimParseError(
                    f"{path}: line {number}: expected 'x y z symbol', "
                    f"got {line!r}"
                )
            positions.append(numbers(number, line, 3, "x y z symbol"))
            symbols.append(fields[3])
    if block is not None:
        raise VSimParseError(
            f"{path}: line {start}: mode block is not closed with '# ]'"
        )
    if not symbols:
        raise VSimParseError(f"{path}: no atom lines")
    try:
        atoms = Atoms(
            symbols=symbols, positions=positions, cell=cell, pbc=True
        )
    except (KeyError, ValueError) as error:
        raise VSimParseError(f"{path}: {error}") from error

    natoms = len(atoms)
    groups: dict[tuple[float, ...], list[tuple[float, np.ndarray]]] = {}
    for number, text in blocks:
        prefix, bracket, rest = text.partition("qpt=[")
        if not bracket or prefix.strip():
            raise VSimParseError(
                f"{path}: line {number}: expected '#metaData: qpt=[...'"
            )
        fields = [
            field.strip()
            for field in rest.split("]", 1)[0].replace("\\", " ").split(";")
        ]
        fields = [field for field in fields if field]
        if len(fields) != 4 + 6 * natoms:
            raise VSimParseError(
                f"{path}: line {number}: expected q, omega and 6 values for "
                f"each of {natoms} atoms ({4 + 6 * natoms} numbers), "
                f"got {len(fields)}"
            )
        try:
            values = np.array([float(field) for field in fields])
        except ValueError:
            raise VSimParseError(
                f"{path}: line {number}: mode block holds a non-number"
            ) from None
        parts = values[4:].reshape(natoms, 6)
        groups.setdefault(tuple(values[:3]), []).append(
            (float(values[3]), parts[:, :3] + 1j * parts[:, 3:])
        )
    if not groups:
        raise VSimParseError(f"{path}: no '#metaData: qpt=[' mode blocks")
    modes = [
        Modes(
            qpoint=np.array(q),
            frequencies=np.array([frequency for frequency, _ in group]),
            displacements=np.array([vector for _, vector in group]),
        )
        for q, group in groups.items()
    ]
    return atoms, modes


def read_many(paths: Sequence[Path | str]) -> tuple[Atoms, list[Modes]]:
    """One structure and the modes of every file, in file order.

    All files must hold the same structure (phonopy writes one file per
    q-point), else an error names the first file that differs.
    """
    if not paths:
        raise VSimParseError("no v_sim files given")
    atoms, modes = read(paths[0])
    for path in paths[1:]:
        other, more = read(path)
        if (
            other.get_chemical_symbols() != atoms.get_chemical_symbols()
            or not np.allclose(other.cell.array, atoms.cell.array, atol=1e-6)
            or not np.allclose(other.positions, atoms.positions, atol=1e-6)
        ):
            raise VSimParseError(
                f"{path} holds a different structure than {paths[0]}"
            )
        modes.extend(more)
    return atoms, modes


def write(path: Path | str, atoms: Atoms, modes: Sequence[Modes]) -> None:
    """Write ``atoms`` and ``modes`` in phonopy's v_sim layout.

    The cell must already be lower-triangular (a along x, b in the xy plane),
    as v_sim requires; positions are written as given.
    """
    cell = atoms.cell.array
    if (
        abs(cell[0, 1]) > 1e-8
        or abs(cell[0, 2]) > 1e-8
        or abs(cell[1, 2]) > 1e-8
    ):
        raise ValueError(
            "v_sim needs a lower-triangular cell (a along x, b in the xy plane)"
        )
    lines = [
        HEADER,
        f"{cell[0, 0]:15.9f}{cell[1, 0]:15.9f}{cell[1, 1]:15.9f}",
        f"{cell[2, 0]:15.9f}{cell[2, 1]:15.9f}{cell[2, 2]:15.9f}",
    ]
    for position, symbol in zip(
        atoms.positions, atoms.get_chemical_symbols(), strict=True
    ):
        lines.append(
            f"{position[0]:15.9f}{position[1]:15.9f}{position[2]:15.9f} "
            f"{symbol}"
        )
    for group in modes:
        q = group.qpoint
        for frequency, vectors in zip(
            group.frequencies, group.displacements, strict=True
        ):
            lines.append(
                f"#metaData: qpt=[{q[0]:f};{q[1]:f};{q[2]:f};{frequency:f} \\"
            )
            for vector in vectors:
                values = [*vector.real, *vector.imag]
                lines.append(
                    "#; " + "; ".join(f"{value:f}" for value in values) + " \\"
                )
            lines.append("# ]")
    Path(path).write_text("\n".join(lines) + "\n")
