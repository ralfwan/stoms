"""Parse VASP calculation directories into AtomsLedger-compatible values."""

from __future__ import annotations

import hashlib
import inspect
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version as package_version
from pathlib import Path
from types import MappingProxyType
from typing import Any

from stoms.atomsledger import MethodSpec, Provenance

try:
    from pymatgen.io.vasp import Vasprun
    from pymatgen.io.vasp.inputs import Incar, Kpoints
except ImportError as error:  # pragma: no cover - exercised in a subprocess
    raise ModuleNotFoundError(
        "VASP parsing requires the optional 'pymatgen' dependency. Install "
        "it with `uv sync --extra vasp` or `pip install pymatgen`."
    ) from error


DEFAULT_HASH_FILES = (
    "INCAR",
    "KPOINTS",
    "POTCAR",
)

DEFAULT_METHOD_INCAR_KEYS = (
    "ENCUT",
    "PREC",
    "METAGGA",
    "GGA",
    "LASPH",
    "LMIXTAU",
    "LDAU",
    "LDAUTYPE",
    "LDAUL",
    "LDAUU",
    "LDAUJ",
    "LHFCALC",
    "HFSCREEN",
    "AEXX",
    "ISMEAR",
    "SIGMA",
    "ISPIN",
    "MAGMOM",
    "NUPDOWN",
    "LSORBIT",
    "LNONCOLLINEAR",
    "EDIFF",
    "NELM",
    "NELMIN",
    "NELMDL",
    "ALGO",
    "IALGO",
    "LREAL",
    "IBRION",
    "NSW",
    "ISIF",
    "EDIFFG",
    "POTIM",
    "ISYM",
    "SYMPREC",
    "LDIPOL",
    "IDIPOL",
    "DIPOL",
    "EFIELD",
    "ICHARG",
    "ISTART",
)

_KNOWN_SOURCE_FILES = (
    "INCAR",
    "KPOINTS",
    "POTCAR",
    "POSCAR",
    "CONTCAR",
    "vasprun.xml",
    "OUTCAR",
)
_POTCAR_SEPARATOR = re.compile(r"^\s*End of Dataset\s*$", re.MULTILINE)
_TITEL = re.compile(r"^\s*TITEL\s*=\s*(.*?)\s*$", re.MULTILINE)
_VRHFIN = re.compile(r"^\s*VRHFIN\s*=\s*([^:]+)", re.MULTILINE)
_SHA256 = re.compile(r"^\s*SHA256\s*=\s*([0-9a-fA-F]{64})\s*$", re.MULTILINE)


class VaspParseError(Exception):
    """Raised when a VASP directory cannot provide a usable evaluation."""


@dataclass(frozen=True, slots=True)
class PotcarDataset:
    """Identity metadata for one ordered POTCAR dataset."""

    index: int
    title: str | None
    symbol: str | None
    embedded_sha256: str | None


@dataclass(frozen=True, slots=True)
class ParsedVaspEvaluation:
    """Immutable, structure-free result of parsing one VASP calculation."""

    directory: str
    vasp_version: str | None
    pymatgen_version: str
    run_type: str | None
    explicit_incar: Mapping[str, Any]
    effective_incar: Mapping[str, Any]
    original_kpoints: Any
    actual_kpoints: tuple[tuple[float, float, float], ...]
    actual_kpoint_weights: tuple[float, ...]
    potcar_datasets: tuple[PotcarDataset, ...]
    properties: Mapping[str, Any]
    units: Mapping[str, str]
    energy_components: Mapping[str, float]
    electronic_converged: bool | None
    ionic_converged: bool | None
    converged: bool | None
    ionic_steps: int
    file_hashes: Mapping[str, str]
    source_files: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "explicit_incar",
            "effective_incar",
            "properties",
            "units",
            "energy_components",
            "file_hashes",
        ):
            object.__setattr__(
                self, name, _freeze_mapping(getattr(self, name))
            )
        object.__setattr__(
            self, "original_kpoints", _freeze(_plain(self.original_kpoints))
        )

    def to_method_spec(
        self,
        *,
        protocol: str | None = None,
        method_identifier: str | None = None,
        name: str | None = None,
        incar_keys: Sequence[str] = DEFAULT_METHOD_INCAR_KEYS,
        use_effective_incar: bool = True,
    ) -> MethodSpec:
        """Convert scientific method identity into an AtomsLedger value."""
        incar = (
            self.effective_incar
            if use_effective_incar
            else self.explicit_incar
        )
        selected_incar = {
            key.upper(): _plain(incar[key.upper()])
            for key in incar_keys
            if key.upper() in incar
        }
        parameters: dict[str, Any] = {
            "incar": selected_incar,
            "kpoints": {
                "actual_points": self.actual_kpoints,
                "actual_weights": self.actual_kpoint_weights,
            },
            "potcar": {
                "datasets": tuple(
                    _potcar_to_plain(item) for item in self.potcar_datasets
                ),
            },
        }
        if protocol is not None:
            parameters["protocol"] = protocol
        return MethodSpec(
            method_identifier=method_identifier or self._inferred_name(),
            family="dft",
            name=name or self._inferred_name(),
            version=self.vasp_version,
            code="vasp",
            parameters=parameters,
        )

    def to_provenance(
        self,
        *,
        created_by: str,
        purpose: str,
        tags: Sequence[str] = (),
        notes: str | None = None,
        calculation_id: str | None = None,
        execution: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Provenance:
        """Convert parser audit data into an AtomsLedger provenance value."""
        record_metadata: dict[str, Any] = {
            "convergence": {
                "electronic": self.electronic_converged,
                "ionic": self.ionic_converged,
                "overall": self.converged,
                "ionic_steps": self.ionic_steps,
            },
            "energy_components": _plain(self.energy_components),
            "source_files": list(self.source_files),
            "file_sha256": _plain(self.file_hashes),
            "parser_warnings": list(self.warnings),
        }
        if calculation_id is not None:
            record_metadata["calculation_id"] = calculation_id
        if execution is not None:
            record_metadata["execution"] = _plain(execution)
        if metadata is not None:
            record_metadata.update(_plain(metadata))
        return Provenance(
            created_by=created_by,
            purpose=purpose,
            tags=tuple(tags),
            notes=notes,
            metadata=record_metadata,
        )

    def _inferred_name(self) -> str:
        for key in ("METAGGA", "GGA"):
            value = self.effective_incar.get(key, self.explicit_incar.get(key))
            if value is not None:
                return _functional_name(value, key)
        if self.run_type:
            return self.run_type.strip().lower()
        return "unknown-dft"


class VaspParser:
    """Parse one VASP directory into a structure-free evaluation result.

    ``vasprun.xml`` is required. Present selected sidecar files are hashed and
    INCAR, KPOINTS, and POTCAR can enrich XML data. This adapter neither creates
    ASE structures nor ingests a ledger record. XML recovery depends on the
    installed pymatgen version.
    """

    def __init__(
        self,
        directory: str | Path,
        *,
        allow_incomplete_xml: bool = False,
        hash_files: Sequence[str] = DEFAULT_HASH_FILES,
    ) -> None:
        self.directory = Path(directory)
        self.allow_incomplete_xml = allow_incomplete_xml
        self.hash_files = tuple(str(name) for name in hash_files)

    def parse(self) -> ParsedVaspEvaluation:
        if not self.directory.is_dir():
            raise VaspParseError(
                f"VASP path is not a directory: {self.directory}"
            )
        xml_path = self.directory / "vasprun.xml"
        if not xml_path.is_file():
            raise VaspParseError(f"Missing vasprun.xml in {self.directory}")

        warnings: list[str] = []
        vasprun = self._parse_xml(xml_path, warnings)
        explicit_incar, effective_incar = self._parse_incar(vasprun, warnings)
        original_kpoints = self._parse_kpoints(warnings)
        actual_kpoints, actual_weights = _actual_kpoints(vasprun)
        potcar_datasets = self._parse_potcar(vasprun, warnings)
        properties, components = _evaluation_values(vasprun)
        file_hashes = self._hash_files()
        source_files = _source_files(self.directory)

        return ParsedVaspEvaluation(
            directory=str(self.directory.resolve()),
            vasp_version=_vasp_version(vasprun),
            pymatgen_version=package_version("pymatgen"),
            run_type=_run_type(vasprun),
            explicit_incar=explicit_incar,
            effective_incar=effective_incar,
            original_kpoints=original_kpoints,
            actual_kpoints=actual_kpoints,
            actual_kpoint_weights=actual_weights,
            potcar_datasets=potcar_datasets,
            properties=properties,
            units={
                **({"energy": "eV"} if "energy" in properties else {}),
                **(
                    {"forces": "eV/angstrom"} if "forces" in properties else {}
                ),
            },
            energy_components=components,
            electronic_converged=_optional_bool(
                vasprun, "converged_electronic"
            ),
            ionic_converged=_optional_bool(vasprun, "converged_ionic"),
            converged=_optional_bool(vasprun, "converged"),
            ionic_steps=_ionic_steps(vasprun),
            file_hashes=file_hashes,
            source_files=source_files,
            warnings=tuple(warnings),
        )

    def _parse_xml(self, path: Path, warnings: list[str]) -> Any:
        kwargs: dict[str, Any] = {
            "parse_dos": False,
            "parse_eigen": False,
            "parse_projected_eigen": False,
            "parse_potcar_file": False,
        }
        supported = inspect.signature(Vasprun).parameters
        kwargs = {
            key: value for key, value in kwargs.items() if key in supported
        }

        if "exception_on_bad_xml" not in supported:
            return self._parse_xml_without_recovery(path, warnings, kwargs)

        strict_kwargs = {**kwargs, "exception_on_bad_xml": True}
        try:
            return Vasprun(path, **strict_kwargs)
        except Exception as error:
            if not self.allow_incomplete_xml:
                raise VaspParseError(
                    f"Could not parse vasprun.xml: {error}"
                ) from error
            try:
                vasprun = Vasprun(
                    path, **{**kwargs, "exception_on_bad_xml": False}
                )
            except Exception as recovery_error:
                raise VaspParseError(
                    "Could not parse vasprun.xml with recovery enabled: "
                    f"{recovery_error}"
                ) from recovery_error
            warnings.append(
                "Incomplete XML recovery was used; parsed values may be incomplete."
            )
            return vasprun

    def _parse_xml_without_recovery(
        self, path: Path, warnings: list[str], kwargs: Mapping[str, Any]
    ) -> Any:
        try:
            return Vasprun(path, **kwargs)
        except Exception as error:
            if self.allow_incomplete_xml:
                try:
                    vasprun = Vasprun(path, **kwargs)
                except Exception as recovery_error:
                    raise VaspParseError(
                        "Could not parse vasprun.xml with recovery enabled: "
                        f"{recovery_error}"
                    ) from recovery_error
                warnings.append(
                    "Incomplete XML recovery was used; parsed values may be incomplete."
                )
                return vasprun
            mode = (
                " with recovery enabled" if self.allow_incomplete_xml else ""
            )
            raise VaspParseError(
                f"Could not parse vasprun.xml{mode}: {error}"
            ) from error

    def _parse_incar(
        self, vasprun: Any, warnings: list[str]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        explicit = _mapping(getattr(vasprun, "incar", {}))
        effective = _mapping(getattr(vasprun, "parameters", {}))
        path = self.directory / "INCAR"
        if path.is_file():
            try:
                explicit = _mapping(Incar.from_file(path))
            except Exception as error:
                warnings.append(
                    f"Could not parse INCAR; using vasprun.xml: {error}"
                )
        elif explicit:
            warnings.append(
                "INCAR is unavailable; using explicit values from vasprun.xml."
            )
        if not effective and explicit:
            warnings.append(
                "Effective INCAR values were unavailable in vasprun.xml."
            )
        return explicit, effective

    def _parse_kpoints(self, warnings: list[str]) -> Any:
        path = self.directory / "KPOINTS"
        if not path.is_file():
            warnings.append(
                "KPOINTS is unavailable; using actual k-points from vasprun.xml."
            )
            return None
        try:
            return _plain(Kpoints.from_file(path).as_dict())
        except Exception as error:
            warnings.append(
                f"Could not parse KPOINTS; using actual k-points from vasprun.xml: {error}"
            )
            return None

    def _parse_potcar(
        self, vasprun: Any, warnings: list[str]
    ) -> tuple[PotcarDataset, ...]:
        path = self.directory / "POTCAR"
        xml_titles = tuple(
            str(value)
            for value in (getattr(vasprun, "potcar_symbols", ()) or ())
        )
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                datasets = _potcar_blocks(text)
            except OSError as error:
                raise VaspParseError(
                    f"Could not read POTCAR: {error}"
                ) from error
            if not datasets:
                raise VaspParseError("POTCAR parsing produced no datasets")
            return tuple(
                PotcarDataset(
                    index=index,
                    title=title or _sequence_value(xml_titles, index),
                    symbol=symbol
                    or _symbol_from_title(title)
                    or _symbol_from_title(_sequence_value(xml_titles, index)),
                    embedded_sha256=embedded_sha256,
                )
                for index, (title, symbol, embedded_sha256) in enumerate(
                    datasets
                )
            )
        if xml_titles:
            warnings.append(
                "POTCAR is unavailable; using dataset titles from vasprun.xml."
            )
            return tuple(
                PotcarDataset(
                    index=index,
                    title=title,
                    symbol=_symbol_from_title(title),
                    embedded_sha256=None,
                )
                for index, title in enumerate(xml_titles)
            )
        warnings.append(
            "POTCAR is unavailable and vasprun.xml contains no dataset titles."
        )
        return ()

    def _hash_files(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in self.hash_files:
            path = self.directory / name
            if not path.is_file():
                continue
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[name] = digest.hexdigest()
        return result


def parse_vasp(
    directory: str | Path,
    *,
    allow_incomplete_xml: bool = False,
) -> ParsedVaspEvaluation:
    """Parse one VASP directory with default file hashing and XML policy."""
    return VaspParser(
        directory,
        allow_incomplete_xml=allow_incomplete_xml,
    ).parse()


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if hasattr(value, "as_dict") and callable(value.as_dict):
        return _plain(value.as_dict())
    if hasattr(value, "item") and callable(value.item):
        try:
            return _plain(value.item())
        except ValueError:
            pass
    if hasattr(value, "tolist") and callable(value.tolist):
        return _plain(value.tolist())
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(_plain(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_plain(item) for item in value), key=repr))
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _freeze(value: Any) -> Any:
    """Recursively copy parser values into immutable serializable values."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _freeze(_plain(value))
    if not isinstance(frozen, Mapping):
        raise TypeError("Expected a mapping")
    return frozen


def _mapping(value: Any) -> dict[str, Any]:
    if hasattr(value, "items"):
        return {str(key).upper(): _plain(item) for key, item in value.items()}
    return {}


def _actual_kpoints(
    vasprun: Any,
) -> tuple[
    tuple[tuple[float, float, float], ...],
    tuple[float, ...],
]:
    points = getattr(vasprun, "actual_kpoints", None)
    weights = getattr(vasprun, "actual_kpoints_weights", None)
    if points is None or weights is None:
        raise VaspParseError("vasprun.xml has no actual k-point data")
    try:
        point_values_list: list[tuple[float, float, float]] = []
        for point in points:
            coordinates = tuple(float(component) for component in point)
            if len(coordinates) != 3:
                raise ValueError("k-point coordinates must have length three")
            point_values_list.append(
                (coordinates[0], coordinates[1], coordinates[2])
            )
        point_values = tuple(point_values_list)
        weight_values = tuple(float(weight) for weight in weights)
    except (TypeError, ValueError) as error:
        raise VaspParseError("Malformed actual k-point data") from error
    if not point_values or len(point_values) != len(weight_values):
        raise VaspParseError("Malformed actual k-point data")
    if any(len(point) != 3 for point in point_values):
        raise VaspParseError("Malformed actual k-point coordinates")
    if any(
        not math.isfinite(value) for point in point_values for value in point
    ):
        raise VaspParseError("Malformed actual k-point coordinates")
    if any(not math.isfinite(value) for value in weight_values):
        raise VaspParseError("Malformed actual k-point weights")
    return point_values, weight_values


def _evaluation_values(
    vasprun: Any,
) -> tuple[dict[str, Any], dict[str, float]]:
    try:
        energy = getattr(vasprun, "final_energy", None)
    except Exception:
        energy = None
    try:
        steps = getattr(vasprun, "ionic_steps", ()) or ()
    except Exception:
        steps = ()
    final_step = steps[-1] if steps else {}
    if energy is None and isinstance(final_step, Mapping):
        energy = final_step.get("e_wo_entrp", final_step.get("e_fr_energy"))
    properties: dict[str, Any] = {}
    if energy is not None:
        try:
            properties["energy"] = float(energy)
        except (TypeError, ValueError) as error:
            raise VaspParseError("Final VASP energy is not numeric") from error
        if not math.isfinite(properties["energy"]):
            properties.pop("energy")

    forces = (
        final_step.get("forces") if isinstance(final_step, Mapping) else None
    )
    if forces is not None:
        try:
            force_values = tuple(
                tuple(float(component) for component in row) for row in forces
            )
        except (TypeError, ValueError) as error:
            raise VaspParseError("Final VASP forces are malformed") from error
        if any(len(row) != 3 for row in force_values):
            raise VaspParseError(
                "Final VASP forces must have shape (n_atoms, 3)"
            )
        atom_count = _final_structure_atom_count(vasprun)
        if atom_count is None or len(force_values) != atom_count:
            raise VaspParseError(
                "Final VASP forces must have shape (n_atoms, 3)"
            )
        properties["forces"] = force_values

    if not properties:
        raise VaspParseError("No usable VASP evaluation property is available")

    components: dict[str, float] = {}
    if isinstance(final_step, Mapping):
        for key, value in final_step.items():
            if key in {"forces", "stress", "structure", "electronic_steps"}:
                continue
            if isinstance(value, bool):
                continue
            try:
                components[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
    return properties, components


def _potcar_blocks(
    text: str,
) -> list[tuple[str | None, str | None, str | None]]:
    blocks = _POTCAR_SEPARATOR.split(text)
    datasets: list[tuple[str | None, str | None, str | None]] = []
    for block in blocks:
        if not block.strip():
            continue
        title_match = _TITEL.search(block)
        symbol_match = _VRHFIN.search(block)
        sha_match = _SHA256.search(block)
        if title_match or symbol_match or sha_match:
            datasets.append(
                (
                    title_match.group(1).strip() if title_match else None,
                    symbol_match.group(1).strip() if symbol_match else None,
                    sha_match.group(1).lower() if sha_match else None,
                )
            )
    return datasets


def _potcar_to_plain(dataset: PotcarDataset) -> dict[str, Any]:
    return {
        "index": dataset.index,
        "title": dataset.title,
        "symbol": dataset.symbol,
        "embedded_sha256": dataset.embedded_sha256,
    }


def _symbol_from_title(title: str | None) -> str | None:
    if not title:
        return None
    fields = title.split()
    return fields[1] if len(fields) > 1 else fields[0]


def _sequence_value(values: Sequence[str], index: int) -> str | None:
    return values[index] if index < len(values) else None


def _source_files(
    directory: Path,
) -> tuple[str, ...]:
    return tuple(
        name for name in _KNOWN_SOURCE_FILES if (directory / name).is_file()
    )


def _final_structure_atom_count(vasprun: Any) -> int | None:
    try:
        structure = getattr(vasprun, "final_structure", None)
    except Exception:
        return None
    if structure is None:
        return None
    try:
        return len(structure)
    except TypeError:
        sites = getattr(structure, "sites", None)
        if sites is None:
            return None
        try:
            return len(sites)
        except TypeError:
            return None


def _vasp_version(vasprun: Any) -> str | None:
    for value in (
        getattr(vasprun, "vasp_version", None),
        _mapping(getattr(vasprun, "generator", {})).get("VERSION"),
        _mapping(getattr(vasprun, "generator", {})).get("VERSION".lower()),
    ):
        if value is not None:
            return str(value)
    return None


def _run_type(vasprun: Any) -> str | None:
    try:
        value = getattr(vasprun, "run_type", None)
    except Exception:
        value = None
    return None if value is None else str(value)


def _optional_bool(vasprun: Any, name: str) -> bool | None:
    try:
        value = getattr(vasprun, name)
    except Exception:
        return None
    return None if value is None else bool(value)


def _ionic_steps(vasprun: Any) -> int:
    value = getattr(vasprun, "nionic_steps", None)
    if value is None:
        value = len(getattr(vasprun, "ionic_steps", ()) or ())
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise VaspParseError("Invalid ionic-step count") from error


def _functional_name(value: Any, key: str) -> str:
    name = str(value).strip().lower()
    if key == "GGA" and name == "pe":
        return "pbe"
    return name or "unknown-dft"


__all__ = [
    "DEFAULT_HASH_FILES",
    "DEFAULT_METHOD_INCAR_KEYS",
    "ParsedVaspEvaluation",
    "PotcarDataset",
    "VaspParseError",
    "VaspParser",
    "parse_vasp",
]
