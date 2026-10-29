"""Phonons from phonopy force constants: modes at any q, bands and DOS.

Two inputs:

- ``stoms --file phonopy_params.yaml serve`` loads the yaml with phonopy
  (force constants, or forces to compute them from; a FORCE_CONSTANTS,
  force_constants.hdf5 or FORCE_SETS file next to the yaml is used too).
- ``stoms --file POSCAR serve --force-constants FILE --dim DIM`` (or
  ``--force-sets FILE``) builds it from a structure file, the supercell
  matrix DIM and the force constants of that supercell. The structure is
  read by phonopy as a POSCAR, or in another code's format with
  ``--calculator`` (then force constants and BORN are in that code's
  units, as in phonopy), or by ASE (cif, extxyz, ...; VASP units).

A BORN file (``--born``, else one next to the input) turns on the
non-analytical term correction (NAC) for polar crystals; so do NAC
parameters in the yaml.

The primitive cell becomes one ledger structure; the phonopy object stays
with the server, which computes what the viewer asks for. Nothing about the
phonons is stored in the ledger.

Conventions, as in phonopy: q in reduced coordinates of the primitive
reciprocal lattice, frequencies in THz (negative = imaginary), and
displacements eigenvector / sqrt(mass). A copy of atom j at fractional
position r = n + x_j moves with exp(2 pi i q.r). With NAC, the modes at
q = 0 depend on the direction q approaches Γ from (LO-TO splitting); without
a direction phonopy leaves the NAC term out there.
"""

from __future__ import annotations

import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms

from ..atomsledger import (
    Aggregation,
    AggregationMemberInput,
    AtomsLedger,
    Provenance,
    StructureSourceSpec,
)

CREATED_BY = "stoms serve"
SUFFIXES = (".yaml", ".yml")
# Files phonopy can take the force constants or forces from, next to the yaml.
FORCE_FILES = ("FORCE_CONSTANTS", "force_constants.hdf5", "FORCE_SETS")
# Born charges and dielectric tensor, used for NAC when found next to the input.
BORN_FILE = "BORN"
# Points per band segment, as phonopy's default, and the default DOS mesh
# (a length: about DOS_MESH * |b_i| points along each reciprocal axis).
BAND_POINTS = 51
DOS_MESH = 50.0
# Seekpath's labels as shown.
LABELS = {"GAMMA": "Γ"}


class PhononInputError(ValueError):
    """The input cannot be loaded or a band path cannot be read."""


def is_phonopy(path: Path) -> bool:
    """Whether ``--file`` names phonopy input (a yaml file)."""
    return path.is_file() and path.suffix.lower() in SUFFIXES


def parse_dim(text: str) -> list[list[int]]:
    """The supercell matrix of phonopy's DIM: 1, 3 or 9 integers.

    One number n means n n n, three the diagonal, nine the matrix row by
    row (as phonopy's DIM tag).
    """
    try:
        values = [int(value) for value in text.replace(",", " ").split()]
    except ValueError:
        raise PhononInputError(f"DIM: {text!r} must hold integers") from None
    if len(values) == 1:
        matrix = np.diag(values * 3)
    elif len(values) == 3:
        matrix = np.diag(values)
    elif len(values) == 9:
        matrix = np.array(values).reshape(3, 3)
    else:
        raise PhononInputError(
            f"DIM: {text!r} must hold 1, 3 or 9 integers, not {len(values)}"
        )
    if round(np.linalg.det(matrix)) <= 0:
        raise PhononInputError(
            f"DIM: {text!r} gives no supercell (determinant must be positive)"
        )
    return matrix.tolist()


@dataclass(frozen=True)
class BandPath:
    """A band path given by hand: continuous parts of q-points and labels.

    ``parts`` holds lists of reduced q-points; each part is drawn as one
    line, and parts are not connected. ``labels`` (or None) names every
    point, in order.
    """

    parts: tuple[tuple[tuple[float, float, float], ...], ...]
    labels: tuple[str, ...] | None = None


def parse_band(text: str, labels: str | None = None) -> BandPath:
    """Read a path in phonopy's BAND syntax: ``0 0 0  0.5 0 0.5, 0 0 0 ...``.

    Three numbers make a q-point; commas break the path. BAND_LABELS-style
    ``labels`` name each point, separated by spaces.
    """
    parts = []
    for chunk in text.split(","):
        try:
            values = [float(value) for value in chunk.split()]
        except ValueError:
            raise PhononInputError(
                f"band path: {chunk.strip()!r} holds a non-number"
            ) from None
        if len(values) % 3 or len(values) < 6:
            raise PhononInputError(
                f"band path: {chunk.strip()!r} must hold at least two "
                "q-points of three numbers each"
            )
        parts.append(
            tuple(
                (values[k], values[k + 1], values[k + 2])
                for k in range(0, len(values), 3)
            )
        )
    names = tuple(labels.split()) if labels else None
    count = sum(len(part) for part in parts)
    if names is not None and len(names) != count:
        raise PhononInputError(
            f"band labels: {len(names)} labels for {count} q-points"
        )
    return BandPath(tuple(parts), names)


def parse_dos_mesh(text: str) -> float | list[int]:
    """The DOS mesh as phonopy takes it: one number is a length (points
    along b_i about length * |b_i|), three integers the points per axis."""
    try:
        values = [float(value) for value in text.replace(",", " ").split()]
    except ValueError:
        values = []
    if len(values) == 1 and values[0] > 0:
        return values[0]
    if len(values) == 3 and all(
        value.is_integer() and value > 0 for value in values
    ):
        return [int(value) for value in values]
    raise PhononInputError(
        f"DOS mesh: {text!r} must be one positive length or three positive "
        "integers"
    )


class PhononModel:
    """A loaded phonopy calculation; thread-safe, results cached.

    ``dos_mesh`` is a length or three numbers of points (see
    :func:`parse_dos_mesh`). With Born charges, every result can be asked
    for with or without NAC (``nac``); the default is with.
    """

    def __init__(
        self,
        phonon: Any,
        band: BandPath | None = None,
        dos_mesh: float | list[int] = DOS_MESH,
    ) -> None:
        self.phonon = phonon
        self.band = band
        self.dos_mesh = dos_mesh
        self._lock = threading.Lock()
        # Kept to switch NAC on and off; results cached per setting.
        self._nac_params = phonon.nac_params
        self._bands: dict[bool, dict[str, Any]] = {}
        self._dos: dict[bool, dict[str, Any]] = {}

    @property
    def nac(self) -> bool:
        """Whether NAC can be applied (Born charges were given)."""
        return self._nac_params is not None

    def _use_nac(self, nac: bool) -> bool:
        """Set NAC on phonopy (lock held); whether it is applied."""
        applied = nac and self.nac
        if (self.phonon.nac_params is not None) != applied:
            self.phonon.nac_params = self._nac_params if applied else None
        return applied

    @property
    def atoms(self) -> Atoms:
        """The primitive cell in Angstrom (phonopy keeps the code's unit)."""
        from phonopy.interface.calculator import get_calculator_physical_units

        primitive = self.phonon.primitive
        units = get_calculator_physical_units(self.phonon.calculator or "vasp")
        return Atoms(
            symbols=list(primitive.symbols),
            cell=np.array(primitive.cell) * units.distance_to_A,
            scaled_positions=primitive.scaled_positions,
            pbc=True,
        )

    def modes(
        self,
        q: tuple[float, float, float],
        direction: tuple[float, float, float] | None = None,
        nac: bool = True,
    ) -> dict[str, Any]:
        """All modes at ``q``, in the layout of a v_sim q-point.

        With NAC, ``direction`` (reduced, like q) is where q = 0 is
        approached from; elsewhere it does not matter and is not used.
        """
        at_gamma = not any(q)
        with self._lock:
            nac = self._use_nac(nac)
            if not (
                nac and at_gamma and direction is not None and any(direction)
            ):
                direction = None
            result = self.phonon.run_qpoints(
                [q], with_eigenvectors=True, nac_q_direction=direction
            )
            frequencies, vectors = (
                result.frequencies[0],
                result.eigenvectors[0],
            )
        masses = np.sqrt(self.phonon.primitive.masses)
        natoms = len(masses)
        displacements = (
            vectors.T.reshape(len(frequencies), natoms, 3)
            / masses[None, :, None]
        )
        return {
            "q": [float(x) for x in q],
            "nac": nac,
            "has_nac": self.nac,
            "direction": None
            if direction is None
            else [float(x) for x in direction],
            "frequencies": np.round(frequencies, 6).tolist(),
            "displacements": np.round(
                np.concatenate(
                    [displacements.real, displacements.imag], axis=2
                ),
                6,
            ).tolist(),
        }

    def bands(self, nac: bool = True) -> dict[str, Any]:
        """The band structure along the path, with bands connected.

        Segments run between two labelled q-points; ``distances`` share one
        axis (Cartesian, 1/Angstrom without 2 pi) over the whole path.
        """
        with self._lock:
            nac = self._use_nac(nac)
            if nac not in self._bands:
                self._bands[nac] = self._compute_bands()
            return self._bands[nac]

    def dos(self, nac: bool = True) -> dict[str, Any]:
        """Total DOS and the DOS projected on each element."""
        with self._lock:
            nac = self._use_nac(nac)
            if nac not in self._dos:
                self._dos[nac] = self._compute_dos()
            return self._dos[nac]

    def _path(
        self,
    ) -> tuple[list[list[np.ndarray]], list[tuple[str, str]], list[bool]]:
        """End points of each segment, their labels and connections."""
        if self.band is not None:
            ends, labels, connections = [], [], []
            names = iter(self.band.labels) if self.band.labels else None
            for part in self.band.parts:
                part_names = (
                    [next(names) for _ in part] if names else [""] * len(part)
                )
                for k in range(len(part) - 1):
                    ends.append([np.array(part[k]), np.array(part[k + 1])])
                    labels.append((part_names[k], part_names[k + 1]))
                    connections.append(k < len(part) - 2)
            return ends, labels, connections
        return _seekpath(self.phonon.primitive)

    def _compute_bands(self) -> dict[str, Any]:
        from phonopy.phonon.band_structure import get_band_qpoints

        ends, labels, connections = self._path()
        primitive = self.phonon.primitive
        paths = get_band_qpoints(
            [[start, end] for start, end in ends],
            BAND_POINTS,
            rec_lattice=np.linalg.inv(primitive.cell),
        )
        self.phonon.run_band_structure(
            paths,
            is_band_connection=True,
            path_connections=connections,
            labels=None,
        )
        result = self.phonon.band_structure
        segments = []
        for k, (start, end) in enumerate(ends):
            segments.append(
                {
                    "start": np.round(start, 6).tolist(),
                    "end": np.round(end, 6).tolist(),
                    "labels": [_label(name) for name in labels[k]],
                    "connected": bool(connections[k]),
                    "distances": np.round(result.distances[k], 6).tolist(),
                    "frequencies": np.round(result.frequencies[k], 5).tolist(),
                }
            )
        return {
            "unit": "THz",
            "nac": self.phonon.nac_params is not None,
            "has_nac": self.nac,
            "segments": segments,
        }

    def _compute_dos(self) -> dict[str, Any]:
        phonon = self.phonon
        phonon.run_mesh(
            self.dos_mesh, with_eigenvectors=True, is_mesh_symmetry=False
        )
        # Tetrahedron method: no smearing width to choose.
        phonon.run_projected_dos(sigma=None, use_tetrahedron_method=True)
        result = phonon.projected_dos
        projected = np.asarray(result.projected_dos)
        symbols = list(phonon.primitive.symbols)
        elements = {}
        for symbol in dict.fromkeys(symbols):
            rows = [k for k, s in enumerate(symbols) if s == symbol]
            elements[symbol] = np.round(
                projected[rows].sum(axis=0), 6
            ).tolist()
        return {
            "unit": "THz",
            "frequencies": np.round(result.frequency_points, 5).tolist(),
            "total": np.round(projected.sum(axis=0), 6).tolist(),
            "elements": elements,
            "mesh": [int(n) for n in phonon.mesh_numbers],
            "method": "tetrahedron",
        }


def _label(name: str) -> str:
    """Seekpath's label as shown: GAMMA as Γ, X_1 as X₁."""
    base, _, index = name.partition("_")
    subscript = index.translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))
    return LABELS.get(base, base) + subscript


def _seekpath(
    primitive: Any,
) -> tuple[list[list[np.ndarray]], list[tuple[str, str]], list[bool]]:
    """The high-symmetry path of seekpath, in the basis of ``primitive``.

    Seekpath gives q-points for its standardized primitive cell, which may
    be rotated and have other axes: A_s = T (A R^T), with A our lattice
    (rows), R seekpath's rotation and T integer. Then q = T^-1 k.
    """
    try:
        import seekpath  # type: ignore[import-untyped]
    except ImportError as error:  # pragma: no cover - optional dependency
        raise ModuleNotFoundError(
            "Band paths need the optional 'seekpath' dependency. Install it "
            "with `uv sync --extra phonopy` or `pip install seekpath`."
        ) from error
    cell = np.array(primitive.cell)
    found = seekpath.get_path(
        (cell, primitive.scaled_positions, primitive.numbers)
    )
    rotated = cell @ np.array(found["rotation_matrix"]).T
    transform = np.array(found["primitive_lattice"]) @ np.linalg.inv(rotated)
    if not np.allclose(transform, np.round(transform), atol=1e-4):
        raise PhononInputError(
            "cannot relate seekpath's cell to the primitive cell; give the "
            "band path with --band"
        )
    back = np.linalg.inv(np.round(transform))
    coords = {
        name: back @ np.array(point)
        for name, point in found["point_coords"].items()
    }
    ends, labels, connections = [], [], []
    path = found["path"]
    for k, (start, end) in enumerate(path):
        ends.append([coords[start], coords[end]])
        labels.append((start, end))
        connections.append(k + 1 < len(path) and path[k + 1][0] == end)
    return ends, labels, connections


def refuse_unsafe_yaml(path: Path) -> None:
    """Refuse a yaml file that PyYAML's safe loader cannot read.

    phonopy reads yaml with PyYAML's full loader, which calls the Python
    functions that tags such as ``!!python/object/apply`` name: such a file,
    received from someone else, could run any code. Plain phonopy files
    hold no such tags.
    """
    import yaml  # type: ignore[import-untyped]

    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    try:
        with path.open("rb") as stream:
            yaml.load(stream, Loader=loader)
    except yaml.constructor.ConstructorError as error:
        raise PhononInputError(
            f"{path} contains Python tags ({error.problem}) that phonopy "
            "would run as code; STOMS does not open it"
        ) from error
    except yaml.YAMLError as error:
        raise PhononInputError(f"{path} is not valid yaml: {error}") from error


def load_phonopy(
    path: Path,
    band: BandPath | None = None,
    *,
    dim: str | None = None,
    force_constants: Path | None = None,
    force_sets: Path | None = None,
    born: Path | None = None,
    dos_mesh: str | None = None,
    calculator: str | None = None,
) -> PhononModel:
    """Load ``path`` with phonopy.

    A yaml brings its own supercell; force files next to it are used unless
    one is given. Any other ``path`` is a structure file and needs ``dim``
    and ``force_constants`` or ``force_sets``; see :func:`_read_cell` for
    the formats and ``calculator``. ``born``, or a BORN file next to
    ``path``, turns NAC on. ``dos_mesh`` is read by :func:`parse_dos_mesh`
    (default: length 50).
    """
    mesh = DOS_MESH if dos_mesh is None else parse_dos_mesh(dos_mesh)
    try:
        import phonopy
    except ImportError as error:
        raise PhononInputError(
            "phonopy input needs the optional 'phonopy' dependency. Install "
            "it with `uv sync --extra phonopy` or `pip install phonopy seekpath`."
        ) from error
    if force_constants is not None and force_sets is not None:
        raise PhononInputError(
            "give either --force-constants or --force-sets, not both"
        )
    for given in (force_constants, force_sets, born):
        if given is not None and not given.is_file():
            raise PhononInputError(f"{given} is not a readable file")
    options: dict[str, Any] = {}
    if force_constants is not None:
        options["force_constants_filename"] = str(force_constants)
    elif force_sets is not None:
        options["force_sets_filename"] = str(force_sets)
    if born is None and (path.parent / BORN_FILE).is_file():
        born = path.parent / BORN_FILE
    if born is not None:
        options["born_filename"] = str(born)
    try:
        if is_phonopy(path):
            if dim is not None or calculator is not None:
                raise PhononInputError(
                    f"{path} holds its supercell matrix and calculator; "
                    "--dim and --calculator are only for structure files"
                )
            if not options.keys() & {
                "force_constants_filename",
                "force_sets_filename",
            }:
                options.update(_force_files(path.parent))
            refuse_unsafe_yaml(path)
            phonon = phonopy.load(
                str(path), produce_fc=True, log_level=0, **options
            )
        else:
            if dim is None or (force_constants is None and force_sets is None):
                raise PhononInputError(
                    f"{path} is a structure file: give the supercell with "
                    "--dim and its force constants with --force-constants "
                    "(or forces with --force-sets)"
                )
            matrix = parse_dim(dim)
            unitcell = _read_cell(path, calculator)
            try:
                phonon = phonopy.load(
                    supercell_matrix=matrix,
                    unitcell=unitcell,
                    calculator=calculator,
                    primitive_matrix=_primitive_matrix(unitcell),
                    produce_fc=True,
                    log_level=0,
                    **options,
                )
            except Exception as error:  # most often a DIM that does not fit
                size = round(abs(np.linalg.det(matrix))) * len(unitcell)
                raise PhononInputError(
                    f"cannot load {path} with phonopy: {error} (the DIM "
                    f"supercell has {size} atoms; check --dim)"
                ) from error
    except PhononInputError:
        raise
    except Exception as error:  # phonopy raises many types for bad input
        raise PhononInputError(
            f"cannot load {path} with phonopy: {error}"
        ) from error
    if phonon.force_constants is None:
        raise PhononInputError(
            f"{path} has no force constants or forces, and no "
            f"{', '.join(FORCE_FILES)} next to it"
        )
    # phonopy reads force constants of another supercell without complaint.
    if phonon.force_constants.shape[1] != len(phonon.supercell):
        raise PhononInputError(
            f"the force constants are for a supercell of "
            f"{phonon.force_constants.shape[1]} atoms, but the supercell "
            f"(DIM) has {len(phonon.supercell)}; check --dim"
        )
    return PhononModel(phonon, band, mesh)


def _force_files(directory: Path) -> dict[str, str]:
    """phonopy.load options for the first force file in ``directory``."""
    for name in FORCE_FILES:
        if (directory / name).is_file():
            key = (
                "force_sets_filename"
                if name == "FORCE_SETS"
                else "force_constants_filename"
            )
            return {key: str(directory / name)}
    return {}


def calculators() -> list[str]:
    """The codes phonopy reads structures of (``--calculator`` values)."""
    from phonopy.interface.calculator import calculator_info

    return sorted(calculator_info)


def _read_cell(path: Path, calculator: str | None = None) -> Any:
    """The unit cell of a structure file, as a phonopy cell.

    With ``calculator``, phonopy reads it in that code's format (and
    length unit). Otherwise a VASP POSCAR is read by phonopy, and any
    other format ASE recognises (cif, extxyz, ...) by ASE, in Angstrom.
    """
    from phonopy.interface.calculator import read_crystal_structure

    if calculator is not None:
        if calculator not in calculators():
            raise PhononInputError(
                f"unknown calculator {calculator!r}; phonopy knows "
                f"{', '.join(calculators())}"
            )
        what = f"a {calculator} structure"
    else:
        from ase.io.formats import filetype

        try:
            kind = filetype(str(path), guess=True)
        except Exception:  # ASE raises several types for unknown files
            kind = "vasp"
        if kind != "vasp":
            return _ase_cell(path, kind)
        calculator, what = "vasp", "a VASP POSCAR"
    try:
        unitcell, _ = read_crystal_structure(
            str(path), interface_mode=calculator
        )
    except Exception as error:  # phonopy's readers raise many types
        raise PhononInputError(
            f"{path}: cannot read it as {what}: {error}"
        ) from error
    if unitcell is None:
        raise PhononInputError(f"{path}: cannot read it as {what}")
    return unitcell


def _ase_cell(path: Path, kind: str) -> Any:
    """A periodic structure read by ASE, as a phonopy cell."""
    from ase.io import read
    from phonopy.structure.atoms import PhonopyAtoms

    try:
        frames = read(str(path), index=":", format=kind)
    except Exception as error:  # ASE's readers raise many types
        raise PhononInputError(
            f"{path}: cannot read it as {kind}: {error}"
        ) from error
    if not isinstance(frames, list):
        frames = [frames]
    if len(frames) != 1:
        raise PhononInputError(
            f"{path} holds {len(frames)} structures; give a file with one"
        )
    [atoms] = frames
    if atoms.cell.rank < 3:
        raise PhononInputError(f"{path}: the structure has no 3D cell")
    return PhonopyAtoms(
        symbols=atoms.get_chemical_symbols(),
        cell=atoms.cell.array,
        scaled_positions=atoms.get_scaled_positions(wrap=False),
    )


def _primitive_matrix(unitcell: Any) -> Any:
    """The primitive cell phonopy finds by symmetry, but the unit cell
    itself (its axes kept) when that is already primitive."""
    from phonopy.structure.cells import guess_primitive_matrix

    matrix = guess_primitive_matrix(unitcell)
    return "P" if abs(np.linalg.det(matrix) - 1) < 1e-6 else matrix


def load_phonons(
    ledger: AtomsLedger,
    path: Path,
    band: BandPath | None = None,
    **inputs: Any,
) -> tuple[Aggregation, dict[str, PhononModel]]:
    """Add the primitive cell of ``path`` to ``ledger``; return it and its model.

    ``inputs`` are the keyword arguments of :func:`load_phonopy`.
    """
    model = load_phonopy(path, band, **inputs)
    source = StructureSourceSpec(kind="file", name=path.name, tool="phonopy")
    [structure_id] = ledger.add_structures(
        [
            {
                "atoms": model.atoms,
                "provenance": Provenance(
                    created_by=CREATED_BY,
                    purpose=f"primitive cell of {path.name}",
                    metadata={"file": str(path)},
                ),
            }
        ],
        source_spec=source,
        allow_equivalent_atoms=True,
    )
    aggregation = ledger.create_aggregation(
        name=path.name,
        description=f"Phonons from {path}",
        members=[AggregationMemberInput(structure_id, None)],
        metadata={"file": str(path)},
    )
    return aggregation, {structure_id: model}


def serve_phonopy(
    path: Path,
    *,
    band: BandPath | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    **inputs: Any,
) -> None:
    """Serve the viewer for one phonopy calculation.

    ``inputs`` are the keyword arguments of :func:`load_phonopy`.
    """
    from .server import create_server, run

    with tempfile.TemporaryDirectory(prefix="stoms-phonopy-") as directory:
        ledger = AtomsLedger(Path(directory) / "view.ledger")
        aggregation, phonons = load_phonons(ledger, path, band, **inputs)
        [structure_id] = phonons
        server = create_server(
            ledger, str(path), host=host, port=port, phonons=phonons
        )
        run(
            server,
            path,
            open_browser=open_browser,
            page=f"#/structures/{structure_id}?from={aggregation.id}",
        )
