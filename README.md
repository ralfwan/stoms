[![Documentation](https://img.shields.io/badge/docs-online-blue.svg)](https://ralfwan.github.io/stoms/)

# STOMS

STOMS (Storage Tool Of Minor Significance) has two parts:

- **A structure viewer** for atomistic data: STOMS ledgers, extxyz and other structure files, and vibrational modes and phonons from phonopy. It runs in your browser on your own computer, with nothing to set up but [uv](https://docs.astral.sh/uv/), or inline in Jupyter, where a Python interface (`stoms.viewer`) controls it: every setting is a property, and figures are saved from code.
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

The terminal prints the viewer's address with its access token, for example `http://127.0.0.1:8765/?token=…`, and `--open` opens it in your browser. Where no browser opens (for example under WSL), copy that whole address into a browser window yourself.

- **Ledgers:** aggregations with property histograms and member tables; export as extxyz, VASP POSCAR or CIF.
- **Structures:** rotate, zoom and repeat the cell; bonds and coordination polyhedra; slicing and Miller planes; distances, angles and dihedrals; atoms coloured by element, height, forces or any per-atom property; ring analysis of networks; step through a series, compare two structures side by side, or play them as a movie.
- **Vibrations and phonons:** animate modes from phonopy v_sim files or a phonopy calculation, at any q, with the band structure, DOS and LO-TO splitting; show the wave vector (in the first Brillouin zone) and the mode's group velocity on the axes; record a video.
- **Your own files:** add extxyz, POSCAR, CIF, OUTCAR, … files in the browser to view and compare them next to a ledger.

### In Jupyter

`pip install "stoms[jupyter]"`, then view any ASE `Atoms`, list of them or trajectory inline, with no ledger:

```python
from ase.build import bulk
from stoms.viewer import view

viewer = view(bulk("Si", "diamond", a=5.43))
viewer                        # rotate, set cell, bonds, size, view; ⧉ opens a browser tab
```

The viewer is linked to Python both ways: a change in the viewer shows up in its properties, and setting a property redraws the viewer.

```python
viewer.show_bonds = True      # settings from Python, synced with the viewer
viewer.repeat = (2, 2, 1)
viewer.cell_style = "dashed"  # also cell_width, cell_colour, atom_scale, bond_radius, …
viewer.element_colours = {"Si": "#3a6ea5"}
viewer.add_plane(1, 1, 1)     # Miller planes; also slice, hidden_elements, bond_cutoffs
viewer.colour_by("charges")   # colour by a per-atom property (calculator results, arrays, …)
viewer.set_view("side-a")     # or "top", or along an axis: "a", "-c", "x", …
viewer.frame = -1             # the shown frame of a trajectory
viewer.measurements           # distances, angles and dihedrals measured in the viewer
viewer.save("si.svg")         # in a later cell: the view as vector graphics (or .html)
view([a1, a2, a3], settings=viewer.get_settings())   # the same look for other structures

from stoms.viewer import view_phonons     # with stoms[jupyter,phonopy]
view_phonons("phonopy_params.yaml")       # modes at any q, band structure and DOS, computed by phonopy in the kernel
```

See [Viewing ASE structures in Jupyter](https://ralfwan.github.io/stoms/jupyter/).

The viewer only reads: the ledger file is never changed. See [Viewing a ledger](https://ralfwan.github.io/stoms/viewing-a-ledger/) for the full guide, including its Security section.

## Store structures and evaluations

Add STOMS to a project:

```bash
uv add stoms
# or
pip install stoms
```

Optional extras: `stoms[jupyter]` (the notebook viewer, linked to Python), `stoms[vasp]` (a `vasprun.xml` parser), `stoms[postgres]` (the PostgreSQL backend), `stoms[symmetry]` (spglib: space groups, Wyckoff letters and equivalent sites in the viewers) and `stoms[phonopy]` (phonopy input for the viewer; needs phonopy 4.7 or newer). If your environment has to stay at phonopy 4.0–4.6, use `stoms[phonopy-legacy]` instead: it also pins `phonors<0.5`, which those phonopy releases need but do not declare.

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
- [Viewing ASE structures in Jupyter](https://ralfwan.github.io/stoms/jupyter/)
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
