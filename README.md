[![Documentation](https://img.shields.io/badge/docs-online-blue.svg)](https://ralfwan.github.io/stoms/)

# STOMS

STOMS (Storage Tool Of Minor Significance) has two parts:

- **A structure viewer in your browser** for atomistic data: STOMS ledgers, extxyz and other structure files, and vibrational modes and phonons from phonopy. It runs on your own computer, with nothing to set up but [uv](https://docs.astral.sh/uv/).
- **An immutable, provenance-first ledger** (`stoms.atomsledger`): a Python library that stores ASE structures and their numerical evaluations (energies, forces, …) with required provenance, in SQLite or PostgreSQL.

## View structures

Start the viewer with `uvx`, which runs STOMS in its own environment:

```bash
# a STOMS ledger
uvx stoms --ledger data.ledger serve --open

# an extxyz file (each frame with its energies and forces)
uvx stoms --file frames.extxyz serve --open

# vibrational modes and phonons from phonopy
uvx --from "stoms[phonopy]" stoms --file phonopy_params.yaml serve --open
```

The terminal prints the viewer's address, for example `http://127.0.0.1:8765/`, and `--open` opens it in your browser. Where no browser opens (for example under WSL), copy that address into a browser window yourself.

- **Ledgers:** aggregations with property histograms and member tables; export as extxyz, VASP POSCAR or CIF.
- **Structures:** rotate, zoom and repeat the cell; bonds and coordination polyhedra; slicing and Miller planes; distances, angles and dihedrals; atoms coloured by element, height, forces or any per-atom property; ring analysis of networks; step through a series, compare two structures side by side, or play them as a movie.
- **Vibrations and phonons:** animate modes from phonopy v_sim files or a phonopy calculation, at any q, with the band structure, DOS and LO-TO splitting; record a video.
- **Your own files:** add extxyz, POSCAR, CIF, OUTCAR, … files in the browser to view and compare them next to a ledger.

The viewer only reads: the ledger file is never changed. See [Viewing a ledger](https://ralfwan.github.io/stoms/viewing-a-ledger/) for the full guide, including its Security section.

## Store structures and evaluations

Add STOMS to a project:

```bash
uv add stoms
# or
pip install stoms
```

Optional extras: `stoms[vasp]` (a `vasprun.xml` parser), `stoms[postgres]` (the PostgreSQL backend) and `stoms[phonopy]` (phonopy input for the viewer).

```python
import numpy as np
from ase import Atoms
from stoms.atomsledger import AtomsLedger, MethodSpec, Provenance, StructureSourceSpec

ledger = AtomsLedger("study.ledger")
structure_id = ledger.add_structure(
    Atoms("H2", positions=[(0, 0, 0), (0, 0, 0.74)]),
    StructureSourceSpec(kind="direct", name="manual-build"),
    Provenance(created_by="researcher", purpose="reference structure"),
)
ledger.add_evaluation(
    structure_id,
    method=MethodSpec(method_identifier="vasp-r2scan", family="DFT", name="VASP-r2SCAN"),
    properties={"energy": -1.0, "forces": np.zeros((2, 3))},
    provenance=Provenance(created_by="researcher", purpose="reference label"),
)
```

Structures and evaluations are immutable records; tags added later are append-only annotations. One structure can carry evaluations from several methods. Queries select training sets with exactly one evaluation per structure, aggregations freeze them in a fixed order, and extxyz exports keep the structure and evaluation IDs. SQLite is the portable archive format; PostgreSQL 16 or newer is an operational backend for shared projects.

## Documentation

- [Overview](https://ralfwan.github.io/stoms/)
- [Viewing a ledger](https://ralfwan.github.io/stoms/viewing-a-ledger/)
- [Researcher quick start](https://ralfwan.github.io/stoms/researcher-guide/)
- [Getting started](https://ralfwan.github.io/stoms/getting-started/)
- [PostgreSQL operational ledger](https://ralfwan.github.io/stoms/postgres/)
- [Use cases and boundaries](https://ralfwan.github.io/stoms/use-cases/)
- [Public API](https://ralfwan.github.io/stoms/api/)
- [VASP parser](https://ralfwan.github.io/stoms/vasp-parser/)
- [Limitations](https://ralfwan.github.io/stoms/limitations/)

## Development

To work on STOMS itself:

```bash
uv sync --dev
uv run pytest
```

Optional parts have their own extras and groups:

```bash
uv sync --dev --extra vasp --extra phonopy   # VASP parser, phonopy input
uv sync --group docs                         # documentation
uv run --group docs mkdocs serve
```

The structure viewer's browser tests are skipped unless Playwright and Chromium are installed:

```bash
uv sync --dev --group browser
uv run playwright install chromium
uv run pytest tests/test_viewer_browser.py
```

The PostgreSQL tests read `STOMS_POSTGRES_TEST_DSN`, which must name a disposable database (each test creates and drops its own schema). Start the local PostgreSQL 16 test service with Docker (Engine and the Compose plugin):

```bash
uv sync --dev --extra postgres
docker compose up -d postgres
export STOMS_POSTGRES_TEST_DSN='postgresql://stoms:stoms@localhost:54329/stoms_test'
uv run pytest tests/postgres
```

If that fails with a permission error on the Docker socket, add yourself to the `docker` group (`sudo usermod -aG docker $USER`, then log out and in again), or run `sudo docker compose up -d postgres`. The Compose database keeps its data in memory and uses test-only credentials; stop it with `docker compose down`.

## License

Copyright 2026 Ralf Wanzenböck.

STOMS is licensed under the Apache License 2.0; see [LICENSE](https://github.com/ralfwan/stoms/blob/main/LICENSE).

The structure viewer of `stoms serve` uses the
[Jmol element colours](https://jmol.sourceforge.net/jscolors/#Atoms) and the
covalent radii of B. Cordero et al., "Covalent radii revisited",
*Dalton Trans.* (2008) 2832–2838,
[doi:10.1039/B801115J](https://doi.org/10.1039/B801115J).
