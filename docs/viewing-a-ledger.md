# Viewing a STOMS ledger

2026-10-08 · Ralf Wanzenböck

Install STOMS 0.11.0 from PyPI, then start its local web viewer on the ledger file you received. It takes about five minutes and runs only on your machine.

## What you need

- **The ledger file** you received, for example `data.ledger`. It is a single SQLite file; keep it in one piece and don't open it while it is still downloading.
- **Either uv or conda.** Both work on Linux, macOS and Windows. Use whichever you already have; if you have neither, uv is the quicker start.
- **A web browser.** The viewer runs locally at `http://127.0.0.1:8765/`; nothing is uploaded anywhere.

STOMS needs Python 3.11 or newer. uv fetches a suitable Python by itself; with conda you choose it when creating the environment.

In the commands below, replace `data.ledger` with the path to your file. Put the path in quotes if it contains spaces.

## Option A: uv

1. Install uv, if `uv --version` doesn't already work. Then open a new terminal.

    Linux or macOS:

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

    Windows (PowerShell):

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

2. Start the viewer. The first run downloads STOMS and its dependencies into uv's cache; later runs start in seconds.

    ```bash
    uvx stoms@0.11.0 --ledger data.ledger serve --open
    ```

Nothing else to set up: `uvx` keeps STOMS in its own environment, separate from any project. If you'd rather have a plain `stoms` command, install it once with `uv tool install stoms@0.11.0` and then run `stoms --ledger data.ledger serve --open`.

## Option B: conda

STOMS is on PyPI, not on conda-forge, so you create a conda environment and install STOMS into it with pip. This works the same with mamba or micromamba.

1. Create and activate an environment:

    ```bash
    conda create -n stoms -c conda-forge python=3.12 pip
    conda activate stoms
    ```

2. Install STOMS:

    ```bash
    pip install stoms==0.11.0
    ```

3. Start the viewer:

    ```bash
    stoms --ledger data.ledger serve --open
    ```

Next time, only `conda activate stoms` and step 3 are needed.

## Browse the data

The terminal prints `Serving data.ledger at http://127.0.0.1:8765/?token=… (Ctrl+C to stop)`, and `--open` opens that page in your browser. If no browser opens, copy the whole address, including the token, into one yourself. The token lets the browser in (see [Security](#security)); afterwards the address bar shows the address without it.

On Linux inside Windows (WSL) there is usually no Linux browser, so `--open` cannot start one. Open the address in your Windows browser; it reaches the viewer running in WSL. To make `--open` use the Windows browser, install `wslu` (`sudo apt install wslu`) and add `export BROWSER=wslview` to your `~/.bashrc`.

- **Homepage:** lists the aggregations in the ledger, the named sets of structures.
- **An aggregation:** shows a summary (evaluation coverage and a histogram per property), the member table, and an "Export" panel (extxyz, VASP POSCAR or CIF).
  - **extxyz** keeps everything an export needs to be traced back: the structure and evaluation IDs, tags, the evaluator label and units.
  - **VASP POSCAR and CIF** hold the geometry only: element symbols, positions and the cell. They carry no IDs, tags, evaluations or units, so a file cannot be traced back to the ledger. POSCAR holds one structure, so several members download as a zip of files named by member number and formula. Both formats treat every structure as periodic in all three directions, so a slab's vacuum becomes part of its cell. CIF stores only the cell lengths and angles, so reading it back puts a along x. Structures without a 3D cell (molecules) can only be exported as extxyz.
- **A structure:** click the eye icon next to a member, or "View" above the table to step through all (or only the selected) members in the structure viewer.
- **Simple or Advanced controls:** the switch "Controls: Simple | Advanced" above the structure viewer's tabs chooses which controls are shown. *Simple*, the default (new in this release, also for existing users), shows the controls most pictures need, and every control whose setting differs from its default, so nothing that changes the picture is hidden. *Advanced* shows all of them, as before. Sections and tabs with nothing to show disappear in Simple (such as the Rings tab, unless rings are shown); the open tab stays until you leave it. Some controls count as simple only when the data has the feature, such as hydrogen bonds for structures with H and O, N or F. An advanced control whose setting is in use carries a small grey *adv.* after its label ("Advanced setting, shown because it is in use"); one that a lock overrides, such as a transformation matrix while *Single cell only* is on, is shown greyed with the lock's tooltip. Set back to its default, it stays until you leave the tab. Beside the switch, *3 advanced settings active* counts them (each control once; nothing while there are none, and nothing in Advanced); click it for the list (tab › section and the control), and choose one to go there: its tab opens, a closed section unfolds, and the control is shown and focused until you leave the tab. The list never changes a setting. Switching only shows or hides controls: it never changes a setting or the picture, and hidden settings keep working. The choice is kept in this browser for all ledgers; it is not part of the viewer settings or settings files.
- **Find a control:** the field *Find a control* in the same row (press `/` to go there) finds a control of the structure viewer by its name, a keyword ("supercell" finds *Repeat* and the *Transformation matrix*) or the name of its tab or section, also one that Simple hides. It searches the controls, not this documentation. Each result shows the control, where it sits (tab › section, or *Steps*, *Compare*, *Element bar* or *Footer* outside the tabs) and *adv.* when Simple hides it now. Choose one (click it, or ↓/↑ and Enter; Enter alone takes the first) to go there, as from the list of advanced settings: its tab opens, a closed section unfolds, and the control is shown and focused until you leave the tab (an advanced one with *adv.*, "Advanced setting, shown because you searched for it"). Esc clears the field. Controls the viewer does not have for this structure are listed greyed with what they need. One that needs data the structure lacks, such as *needs vibrational modes*, *needs phonon data (phonopy)* or *only while comparing*, cannot be chosen. One that needs another setting, such as *only with Show rings on* or *only with Transformation matrix on*, takes you to that setting instead (*Show rings*, *Transformation matrix*), without changing it. Searching never changes a setting.
- **Your own files:** "+ Add structures" in the sidebar opens structure files (extxyz, POSCAR/CONTCAR, CIF, OUTCAR, …) next to the ledger's data, to view and compare them. They are kept only while the viewer runs and are not written to the ledger.
- **Wrap atoms into cell:** a setting in the View tab of the structure viewer (off by default). It draws every atom inside the cell, as ASE's `Atoms.wrap` does: along each periodic direction, an atom is moved by a cell vector so it lies in the cell. With a repeat, each copy fills its own cell. Bonds, measurements, height colouring and ring height windows use the drawn positions; the Info tab and exported files keep the stored ones. In a trajectory, an atom that crosses a cell face jumps to the other side.
- **Transformation matrix:** in the View tab's Cell section, "Transformation matrix" shows a cell given by a 3×3 integer matrix instead of the repeat a × b × c: its rows are the new a, b and c in units of the stored ones, such as 2 1 0 / −1 1 0 / 0 0 1 for (√3×√3)R30° of a hexagonal a-b lattice with γ = 120°. Presets: (√3×√3)R30° (rows for the structure's angle between a and b, 60° or 120°), c(2×2) (its primitive cell, (√2×√2)R45°), p(2×1) and c(4×2) (its primitive cell). Entries are whole numbers from −12 to 12, and the determinant (the number of cell copies) from 1 to 12³; other entries are marked and the last valid matrix stays shown. Along a non-periodic axis it keeps one copy, as the repeat does. Each atom is drawn once per new cell, none twice at its faces: where its position in the stored cell plus a lattice vector lies in the new cell. Atoms stored outside the cell stay outside as with the repeat; "Wrap atoms into cell" puts every atom inside the new cell. The new outline is drawn ("Stored cell outline too" adds the stored one, dotted; "Outline every copy", beside "Cell outline", adds the stored-cell grid inside the new cell, dotted: the stored cells' edges cut to the new cell, without those on its outline, which includes the stored cell, so "Stored cell outline too" is locked meanwhile; without a matrix it draws the outline at every copy of the repeat, in its own style, each shared edge once). Slice bounds and Miller planes keep referring to the stored cell, so they mean the same with and without a matrix; planes are cut to the new cell. Bonds, polyhedra, bonded atoms outside, rings, arrows and labels follow the new cell, and measurements keep their atoms (index and periodic image of the stored cell). It is display only: the Info tab says that a transformation is shown and keeps the stored cell's numbers, and saved structures keep the stored cell. A diagonal matrix draws exactly what the same repeat draws, apart from the outline. Clear all goes back to the repeat.
- **Single cell only:** at the top of the View tab's Cell section (periodic structures; off by default). It shows only the stored cell: each atom once, wrapped into the cell, and nothing from periodic images. While it is on, the repeat counts as 1 × 1 × 1 and a transformation matrix is not applied, atoms are wrapped as with "Wrap atoms into cell", bonded atoms outside are hidden, and bonds and hydrogen bonds run only between atoms of the cell. Polyhedra are drawn only when the centre and all ligands lie in the cell itself (a polyhedron at the cell edge, with a ligand in a neighbouring copy, is left out and its centre drawn as an atom); rings likewise. Miller planes and planes through atoms are clipped to the cell; a patch around atoms is cut at the cell's faces, and its "Extend ×" still extends it up to them (for planes across the cell "Extend ×" is locked, as they fill the cell already). Labels, arrows and measurements are unchanged: a measurement to a periodic image keeps its value (as with "Wrap atoms into cell") and its mark may reach outside the cell. The settings it overrides (the repeat, the transformation matrix, Wrap, "Outline every copy", "Stored cell outline too", "Bonded atoms outside") are disabled with the tooltip "Single cell only is on" and show what is in effect (repeat 1 × 1 × 1, Wrap ticked, "hide", no transformation matrix, "Outline every copy" unticked); their stored values are kept and show again when it is off, which brings the previous view back. The Vibrations tab's "Apply" (a repeat for a q ≠ 0) is disabled meanwhile, too. The Info tab says when a transformation matrix is not applied for this reason.
- **Displacements:** in the Forces tab, "Arrows of" › "Displacements from a reference" draws an arrow from each atom to where it moved since the reference: the structure in the other panel ("The compared structure"), or the first, the previous or a numbered frame of the step list below the structure. Along periodic axes the arrow takes the shortest way, so an atom that crossed a cell face gets a short arrow. Both structures need the same atoms in the same order; otherwise a note says why there are no arrows. If the cells differ (a cell relaxation), the reference is stretched with the cell, so the arrows show only how atoms moved within it. The Info tab then lists the RMSD and the largest displacement. In the Colour tab, "Displacement from the reference" under an atomic property colours atoms by the same displacement (its size or one component).
- **Symmetry:** with the optional `symmetry` extra (spglib; `pip install "stoms[symmetry]"`, or `uvx --from "stoms[symmetry]" stoms …`), the Info tab lists the space group (symbol and number) and the crystal system of each shown structure, computed by the server and kept per structure. The tolerance below the table (default 0.01 Å, spglib's `symprec`) is a setting; changing it computes again. "Inequivalent sites" lists each symmetry-distinct site with its Wyckoff letter, site symmetry and atoms. Hovering an atom shows its Wyckoff letter and site symmetry (for structures up to 1000 atoms at once; larger ones once the Info tab has been shown). In the Colour tab, "Equivalent site (symmetry)" under an atomic property gives each inequivalent site its own colour, named like "O2 (f)": the element, a number per element and the Wyckoff letter. Only structures periodic along a, b and c have a space group; molecules and slabs with a non-periodic axis show "not applicable" (layer groups are not computed). A slab stored with vacuum but periodic along c gets the space group of that 3D cell. Without spglib on the server, the Info tab shows one line naming the extra, and Wyckoff letters and equivalent-site colours are not offered. `stoms.analysis.symmetry(atoms, tolerance=0.01)` computes the same in Python.
- **Polyhedra:** in the Measure tab, choose "Polyhedron (click a centre)" and click an atom. Its coordination polyhedron joins the list "Polyhedra": the ligands are the bonded non-metals within the bond cutoffs (the rule of drawn polyhedra; they need not be drawn, and any atom can be the centre), with the coordination number, the sorted bond lengths and their mean, the volume of the ligands' convex hull, the distortion index (Baur), the quadratic elongation and bond-angle variance (Robinson et al.; 4 and 6 ligands only) and the effective coordination number (Hoppe, as in VESTA). An entry names its centre by atom number, like a measurement: it follows the step list and the movie, shows one column per panel when the compared structure has the same atoms, and is left out, with a note, for a structure with other atoms. "Copy as CSV" copies all shown entries. `stoms.analysis.polyhedron(atoms, index)` computes the same numbers in Python.
- **Planes through atoms:** in the Planes tab, "Plane through atoms" turns clicks into picks: click 3 atoms (more give the least-squares plane; a second click drops an atom), then "Make plane". The plane names its atoms by number and periodic image, like a measurement: it follows the step list, the movie and a compared structure with the same atoms; on a structure with other atoms it is not drawn and its row says so. The row gives the fit ("Through 3 atoms", or the RMS and largest deviation of a best-fit plane). It is drawn where it cuts the shown region, the repeat or the cell of a transformation matrix, exactly as Miller planes are (its atoms keep referring to the stored cell, so a matrix does not move it); "Patch around the atoms" draws a patch around its atoms instead, 1 Å wider, as does a structure without a cell. "Extend ×" (1 to 10, on Miller planes too) enlarges a drawn plane by that factor in all in-plane directions about its centre, so a plane can reach beyond the cell outline or the patch. Colour, opacity and visibility work as for Miller planes, in every style and in saved SVG, PNG and video, and each Miller plane's row lists its spacing d. The Measure tab adds "Plane angle" (the angle between two planes, Miller or through atoms, 0 to 90°) and "Distance to a plane" (the signed distance of each clicked atom along the plane normal, drawn as a dashed line to the plane). A plane through atoms has its normal on the side the surface normal points to, so for a slab the distance is the height above the plane, the Info heights less the plane's height. A plane measurement keeps the planes as they were when measured; like any measurement, it shows "–" on a structure whose atoms do not fit and its value again on one they fit. Planes through atoms are saved with the viewer settings (settings files load in both viewers; older files load unchanged).
- **Bond search:** in the Style tab, "Bond cutoffs" has a Min and a Max length per element pair: bonds from Min up to Max are drawn (Min defaults to 0; it can separate, say, covalent O–H bonds from hydrogen bonds), and polyhedra, coordination numbers and the Measure tab's polyhedra use the same range. Bonds are found across as many cell copies as the cutoff reaches, so small cells get all their bonds. "Bond search" adds hydrogen bonds D–H···A, drawn as dashed lines in their own colour (in saved images too): the acceptor A and the donor D (the atom bonded to the H) are of the listed elements (default O, N, F), H···A is 1.5–2.5 Å and the D–H···A angle at least 120° by default. "Per acceptor" gives each acceptor element an H···A range of its own: one row per listed element, each starting from the single range (so switching it on changes nothing until a row is edited); elements without an edited row keep following the single range (↺ beside an edited row makes it follow the single range again), and switching it off uses the single range again (the rows are kept for next time). "Bonded atoms outside" decides what happens to atoms bonded to shown ones but outside the repeat or the slice: *hide* (the default), *show partners* (drawn with their bonds, one step only) or *show polyhedron ligands* (only the ligands of shown polyhedra, such as the O of octahedra cut by a slice). Such atoms can be hovered, labelled and clicked, but the slice line counts them apart ("… and 5 bonded outside"). Hidden elements stay hidden.
- **Polyhedra without centres:** in the Style tab, "Show centre atoms" (beside Polyhedra; off while polyhedra are off or in space-filling) can be cleared to draw the polyhedra without the atoms at their centres: an atom that is the centre of a drawn polyhedron loses its sphere, label and bonds, while atoms of the same element with fewer than 4 ligands stay; hidden centres still count as shown atoms and can be hovered and clicked inside their polyhedron (for the Measure tab's polyhedra).
- **Drawing styles:** in the Style tab, "Model" chooses *ball and stick* (the default: spheres at a third of the radius with bonds or polyhedra, at half without), *space-filling* (spheres at the radius type's radii exactly; no bonds or polyhedra), *stick* (bonds as cylinders, atoms as spheres of the bond radius) and *wireframe* (bonds as thin lines in the atoms' colours, atoms without bonds as small dots). Stick and wireframe always draw bonds, so the Bonds box is off for them. The radius type sets the automatic radii: *covalent* (Cordero et al. 2008, the default), *van der Waals* (Alvarez 2013) or *ionic* (Shannon 1976: one ion per element, its usual charge in oxides, halides and chalcogenides, at coordination 6, such as O²⁻ 1.40 Å, Ti⁴⁺ 0.605 Å, Na⁺ 1.02 Å; N³⁻ at coordination 4; H and the noble gases keep their covalent radius). The atom size factor scales them only in ball and stick: space-filling always shows the table's radii, and stick and wireframe atoms take the bond radius, so the size control is off in those styles. A radius set for an element (Elements, radius in Å) wins in every style except space-filling: that element is drawn as a sphere of that radius, also in stick and wireframe. Space-filling ignores it and its radius fields are off; the stored radii and size factor come back with another style. Nothing switches style by itself: above 3000 atoms the note under the structure suggests wireframe, which draws fastest (on screen its lines are one device pixel wide, saved images draw them 1 px wide, and they lie beneath spheres and polyhedra). Saved SVG and PNG images and videos draw every style with the same circles and lines. Settings files without a style keep today's look.
- **Rings:** the Rings tab of the structure viewer finds the rings (closed loops of bonds) of a network of atoms and colours them by size, for example the hexagons and 5–7 defects of graphene, the 4- and 8-rings of a Cu-O overlayer, or the rings of silica. Set it up in four steps: the kind of network, the atoms that form it (by element, optionally within a height window to keep one layer), its bonds, and how a ring's size is counted (atom pairs, all atoms, or one element). A *flat* network (surface, overlayer, 2D material) is looked at from above: every enclosed face in the a-b plane is a ring. When network atoms lie on top of each other in that plane (as the two S layers of MoS2), it warns that the rings may be wrong; keep one layer with the height windows, or choose a *3D* network, which finds shortest-path (Guttman) rings in any structure.

The viewer is read-only and never changes the ledger file. Leave the terminal open while you browse, and press Ctrl+C there to stop it.

If the terminal reports that the address is already in use, add `--port 0` after `serve`. STOMS then picks a free port and prints the new address.

## Linking to other pages

Pages made elsewhere about some of the structures, such as simulated STM images, can be linked from the structure viewer. Pass the page's directory with `--link-page`, once per page:

```bash
stoms --ledger data.ledger serve --link-page results/stm-viewer
```

The directory must contain a `stoms-link.json` manifest:

```json
{
  "schema": 1,
  "name": "stm",
  "title": "STM images",
  "description": "Simulated constant-height STM images",
  "entry": "index.html",
  "fragment": "{structure_id}",
  "structure_ids": ["str_034de2bbb5f34d7abdb8113006169dde"]
}
```

- `name` forms the address: the directory is served read-only under `/linked/<key>/stm/`, where the key comes from the viewer's token. Names must be unique.
- A structure listed in `structure_ids` gets a "STM images ↗" link under "Linked pages" on its viewer page. The link opens `entry` in a new tab, with `fragment` (after `#`, `{structure_id}` replaced) telling the page which structure to show.
- In an aggregation's member table, those members carry a small badge with the page's `name` (for example `stm`) that opens the page directly. A chip above the table, such as "STM images (10)", shows only those members, so you can select, view or export just them.
- `entry` defaults to `index.html` and `fragment` to `{structure_id}`; `description` is optional and shown when you hover over the link.
- At startup the terminal reports how many listed structures the ledger does not contain. They get no link, but serving goes on.
- Within its own files, the page can link back with `../../#/structures/<id>`. That address leads to the viewer, so the page needs no change for the key.

Several pages can be linked at the same time, each from its own directory and manifest:

```bash
stoms --ledger data.ledger serve --link-page results/stm-viewer --link-page results/phonons
```

A structure listed in both manifests then shows both links and both badges, and each page gets its own chip above the member table. The chips filter one page at a time.

Linked pages run in a browser sandbox. Their scripts work, but they cannot call the viewer's data API or read what the viewer stores in the browser, so a page that needs browser storage (`localStorage`) or cookies will not work as a linked page. They cannot show dialogs (`alert`, `confirm`) or start downloads either. Links that open a new tab work, and a link back to the viewer (such as `../../#/structures/<id>`) opens a working viewer. Hidden files and folders, such as `.git` or `.env`, are never served. A sandboxed page's own requests carry no session, so the key in its address lets its files in: anyone with a linked page's address can open that page (not the viewer or its data) until the token changes. Linked pages work only with `--ledger`, not with `--file`.

## Viewing an extxyz file

The same viewer also opens a single extxyz file instead of a ledger. Use `--file` in place of `--ledger`:

```bash
uvx stoms@0.11.0 --file frames.extxyz serve --open
```

Every frame appears in file order, as one aggregation named after the file. Energies and forces stored in the file (for example `REF_energy` and `REF_forces`, or plain `energy` and `forces`) are shown as the frame's evaluation. Other structure files ASE reads, such as an ASE `.traj` trajectory, POSCAR or CIF, open the same way. The file is only read; exports from an extxyz file copy the chosen frames unchanged.

A long trajectory can be opened in part with `--frames`, in ASE's index syntax:

```bash
stoms --file md.traj serve --frames ::100     # every 100th frame
stoms --file md.traj serve --frames :1000     # the first 1000
stoms --file md.traj serve --frames -500:     # the last 500
stoms --file md.traj serve --frames 20000:21000:5
```

Only the chosen frames of an ASE trajectory or an extxyz file are read, so even a file of several GB opens in seconds. Each frame is labelled with its number in the file ("frame 12300") when stepping through. A file of more than 10,000 frames needs `--frames`: every frame is copied into a temporary ledger first (about 1.5 ms each), and the pages list them all. "+ Add structures" in the browser takes files of up to about 145 MB; open larger ones from a terminal this way.

## Viewing vibrations and phonons

`--file` also takes phonopy output, and the structure page then gets a **Vibrations** section that animates the modes. A phonopy calculation (the yaml, or a structure with its force constants) needs the `phonopy` extra: run the commands below as `uvx --from "stoms[phonopy]==0.11.0" stoms …`, or install it with `uv tool install "stoms[phonopy]==0.11.0"` or `pip install "stoms[phonopy]==0.11.0"`. The `phonopy` extra needs phonopy 4.7 or newer. If your environment has to stay at phonopy 4.0–4.6, use the `phonopy-legacy` extra instead (`stoms[phonopy-legacy]`): it also pins `phonors<0.5`, which those phonopy releases need but do not declare. v_sim files need no extra.

```bash
# v_sim files written by phonopy (ANIME_TYPE = V_SIM): one file, or a directory with one per q-point
stoms --file anime.ascii serve --open
stoms --file v_sim_files/ serve --open

# a phonopy calculation: modes at any q, band structure and DOS (needs the phonopy extra)
stoms --file phonopy_params.yaml serve --open

# the same from a structure, the supercell (DIM) and its force constants
stoms --file POSCAR serve --dim 5 --force-constants FORCE_CONSTANTS --open
```

The yaml may hold the force constants or the forces of the displaced supercells; a `FORCE_CONSTANTS`, `force_constants.hdf5` or `FORCE_SETS` file next to it (for example with `phonopy_disp.yaml`) is used too. The viewer shows the primitive cell. Type q in reduced coordinates of its reciprocal lattice, or click on the band structure to pick q and the closest mode there. A click on a high-symmetry label (Γ, X, …) selects exactly that point, and the slider under the bands moves q along the path; both keep the selected branch. The band path is seekpath's high-symmetry path; give your own in phonopy's `BAND` syntax with `--band '0 0 0  0.5 0 0.5, 0.5 0.5 0.5  0 0 0' --band-labels 'G X L G'`.

With a structure file (VASP POSCAR), `--dim` is phonopy's `DIM`: one number (`5` = `5 5 5`), three for the diagonal, or nine for the full matrix, row by row. The force constants (`--force-constants`, `FORCE_CONSTANTS` or `force_constants.hdf5`, full or compact) must belong to that supercell; or give `--force-sets FORCE_SETS` instead. A primitive POSCAR keeps its axes; a conventional one is reduced to the primitive cell phonopy finds.

Other structure formats work too. `--calculator qe` (or `abinit`, `castep`, `aims`, `crystal`, `siesta`, … any code phonopy supports) reads the file as phonopy does for that code, and then the force constants and BORN are taken in that code's units (for QE, Ry/bohr²). Without `--calculator`, a file that is not a POSCAR is read by ASE (cif, extxyz, …), and the force constants are taken in VASP units (eV/Å²). The structure must match the calculation of the force constants: the same atom order and the same Cartesian orientation, since force constants are Cartesian tensors. A CIF stores only cell lengths and angles, so ASE puts a along x; use it only if the calculation used that orientation.

For polar crystals, a phonopy `BORN` file (Born charges and dielectric tensor) adds the non-analytical term correction (NAC): `--born BORN`, or a `BORN` next to `--file` is picked up, as are NAC parameters in a yaml. The bands then split LO from TO where they meet Γ. At exactly q = 0 that splitting depends on the direction q approaches Γ from, so a **→Γ** row (reduced coordinates, like q) appears there; without a direction the NAC term is left out (LO = TO). Clicking on Γ in the band structure fills in the direction of that segment. The **NAC** checkbox in the plot header switches the correction off and on, for the bands, the DOS and the modes, to compare.

The band structure and DOS sit below the structure; "Beside the structure" in the plot's header puts them side by side, for wide screens. Drag the plot's bottom-right corner to resize it (double-click for the automatic size), and save it with "Save bands & DOS (SVG)". The structure itself is saved with "Save SVG" next to "Clear all" (PNG under the Save tab). The settings beside the structure scroll on their own and stay in view while you look at the plot.

The DOS uses the tetrahedron method on a q-point mesh. `--dos-mesh` sets the mesh as phonopy's `MESH` does: three integers (`--dos-mesh '24 24 24'`), or one length that gives about length × |bᵢ| points along each reciprocal axis (default 50, which is 16×16×16 for Si). The mesh is shown under the DOS. Denser meshes resolve finer features; the work grows with the number of points.

At q ≠ 0, neighbouring cells move with different phases; the hint under the mode list suggests a repeat that holds a whole wavelength. Bonds can stay fixed at equilibrium (the default) or be recomputed every frame. **Record** saves the vibration as a video (WebM, or MP4 in Safari) that loops.

## Security

The viewer is a small web server on your computer. By default it is for you alone.

- **The link is the key:** every viewer has a secret token, and the address it prints carries it (`…/?token=…`). Opening that address lets the browser in; the browser then keeps a session (a cookie) until the viewer stops, and the address bar no longer shows the token. Without the token or a session, the viewer shows only a page that asks for the link, and its data API refuses (HTTP 401). Anyone who has the link, and may connect (see `--allow`), gets in until the token changes. Share it only with the people who should see the data.
- **Only on your computer:** by default it listens on 127.0.0.1, an address other computers cannot reach. Other users of the same computer (a shared workstation, a JupyterHub or a cluster login node) can reach that address, but they need the link. The viewer also answers only requests addressed to it by its own name or address, so a web page you visit at the same time cannot read your ledger through it.
- **Read-only:** the ledger is opened so that the file cannot be changed. Files you add with "+ Add structures" stay in a temporary ledger that is deleted when the viewer stops. Exports, from the viewer or with `stoms aggregations`, never overwrite a ledger.

### Reaching your own computer from elsewhere

Keep the default `--host 127.0.0.1` and use an SSH tunnel. For example, from your laptop (over the VPN):

```bash
ssh -L 8765:localhost:8765 office-pc
```

Then start the viewer on `office-pc` and open the printed address in your laptop's browser. The tunnel encrypts the traffic, and nobody else can reach the viewer.

### Sharing a viewer with others

`--host` chooses the network interface. `serve --host 0.0.0.0` makes the viewer reachable by anyone who can reach this computer's address. Depending on the network, that is the subnet, everyone on the VPN, often the whole institution, or the whole internet when the computer has a public address and nothing filters incoming connections. A specific address, such as only the VPN interface's, is narrower. The viewer prints a warning when it is reachable from other computers, and the addresses others can use instead of `0.0.0.0`. Send the people you share with the printed link.

- **`--allow`:** accept connections only from the address ranges you list, for example your institution's and the VPN's: `--allow 10.0.0.0/8,192.168.10.0/24` (ask your IT department for the actual ranges). Connections from elsewhere are closed before anything is read. Without `--allow`, the token is the only protection, so set it whenever you share.
- **A stable link:** a new token is made each time the viewer starts, so a shared link stops working after a restart. To keep it, set the token yourself with the environment variable `STOMS_TOKEN`, or put it in a file and name that file with `STOMS_TOKEN_FILE` (this keeps it out of the environment of other programs). The token needs at least 32 characters; make one with `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`. Choose a new token to revoke a link you shared. The token is never a command-line option, since those end up in the shell history and in process lists that other users can see.
- **Uploads are off when shared:** everyone with the link would see the files others add with "+ Add structures", and could fill the temporary ledger. So, when the viewer is reachable from other computers, the button is hidden and the server refuses added files. `--allow-uploads` turns them on again.
- **Slow and many connections:** a client has 15 seconds to send its request, and then 30 seconds for each further read or write; slower ones are closed. At most 128 connections are open at once, 32 of them from one address; further ones are closed unread. This keeps one misbehaving computer from tying up the viewer, but someone with many addresses inside the `--allow` ranges can still keep it busy.

### Encryption (HTTPS)

Without TLS, the viewer speaks plain HTTP: the link with its token, the session cookie and all data travel unencrypted. Anyone who can read the network traffic between you and the viewer (on the same Wi-Fi, or on the path through the institution's network) can read them and get in. On 127.0.0.1 that traffic never leaves the computer, and an SSH tunnel encrypts it.

To share over the network with encryption, give the viewer a certificate:

```bash
stoms --ledger data.ledger serve --host 0.0.0.0 --allow 10.8.0.0/16 \
    --certfile office-pc.pem --keyfile office-pc.key
```

The viewer then serves `https://` and prints addresses with the certificate's name. STOMS does not make certificates. Where to get one:

- **Your institution:** many IT departments issue certificates for a computer's host name. This is the best choice; browsers trust it.
- **Let's Encrypt:** free, for computers with a public host name.
- **Self-signed:** `openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj /CN=office-pc.example.org -addext subjectAltName=DNS:office-pc.example.org -keyout office-pc.key -out office-pc.pem`. The traffic is encrypted, but every browser warns about the certificate, and you must check that warning against the certificate you made.

### Scripts

Scripts and tools such as `curl` can send the token in a header instead of logging in: `curl -H "Authorization: token $STOMS_TOKEN" http://127.0.0.1:8765/api/aggregations`.

Files you receive from others:

- **Phonopy yaml files:** a yaml file can carry tags that make phonopy run code while reading it. STOMS refuses such files, and files that are not valid yaml, before phonopy reads them. Opening the same file with phonopy itself would still run that code.
- **Viewer settings files** ("Import" under View): they change only how the viewer looks, and STOMS keeps only plain colours from them.
- **Linked pages** (`--link-page`): they run sandboxed, without access to the viewer's data and without dialogs or downloads, but they can open links in new tabs. Link only pages you trust.
