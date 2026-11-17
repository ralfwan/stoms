# Viewing ASE structures in Jupyter

2026-11-05 · Ralf Wanzenböck

`stoms.viewer.view()` shows ASE `Atoms` in the STOMS viewer, inline in a notebook, much like `ase.visualize.view()`. It uses the same drawing code as `stoms serve`, including its SVG export, which writes real vector graphics. No ledger and no server are involved.

## Install

```bash
pip install "stoms[jupyter]"     # or: uv add "stoms[jupyter]"
```

The `jupyter` extra adds [anywidget](https://anywidget.dev), which links the viewer to Python. Without it, `view()` still works but is not linked (see [Without anywidget](#without-anywidget)).

Install the extra **in the environment that runs Jupyter** as well as in the kernel's environment, if they differ. JupyterLab loads the widget's browser side from the extensions installed with it. If the kernel has the extra but the Jupyter server does not, the output shows only `Viewer(…)` text, and the browser console reports "Exception opening new comm".

## Quick start

```python
from ase.build import bulk
from stoms.viewer import view

atoms = bulk("Si", "diamond", a=5.43)

viewer = view(atoms)
viewer
```

You can drag to rotate, right-drag or Shift-drag to pan, and scroll to zoom. Hovering an atom shows its element, index, height, and up to four per-atom values (for example charges or |forces|).

`view()` accepts the following:

- one `Atoms`;
- a list of them;
- an ASE `Trajectory`, or any iterable of `Atoms`;
- a file name that ASE reads; all of its frames are shown.

```python
view([atoms1, atoms2, atoms3])

from ase.io import Trajectory
view(Trajectory("opt.traj"))

view("relax.extxyz")
```

The `Atoms` are copied: the viewer never changes them, and later changes to your objects don't reach the viewer. Energies, forces, charges and other calculator results are read from `atoms.calc.results`. Nothing is computed, and the calculator itself is not stored.

At most 10 000 frames are shown at once, because all of them are copied into the page. For longer trajectories, pass every n-th frame, for example `images[::10]`.

## The controls

The toolbar sits under the structure:

- **Frames** (more than one frame): ◀ ▶, a slider, the frame number (from 0, as in Python) and ▶ play. The ← and → keys also step through the frames.
- **Cell**, **Bonds**, **Wrap** (periodic structures only), and **Size**, a factor on the automatic atom radii.
- **Arrows** (when the frames have per-atom vectors): force arrows. See [Force arrows](#force-arrows).
- **Colour**: element colours, or a per-atom property. See [Colouring by a per-atom property](#colouring-by-a-per-atom-property).
- **View…** looks from the top, from the side, or along a, b, c, x, y or z. **Fit** fits the structure into the panel.
- **Save SVG** downloads the view as a vector image.
- **📏** measures distances, angles and dihedrals, plane angles and distances to a plane, and describes coordination polyhedra. See [Measurements](#measurements), [Planes through atoms](#planes-through-atoms) and [Polyhedra](#polyhedra).
- **⧉** opens the viewer in a new browser tab. The tab is a copy with the current frame, settings and view; it is not linked to Python.
- **⚙** opens more settings:
  - repeat a × b × c or a transformation matrix, the cell outline (width, colour, solid/dashed/dotted), atom labels, the model (drawing style) and radius type, coordination polyhedra (and their opacity), bond radius, and depth cueing (and how far it fades);
  - slicing: which elements are shown, and a window of fractional coordinates per axis;
  - per-element colours and radii, bond cutoffs and polyhedron centres;
  - Miller planes, with their position as t or in Å and their spacing d, planes through atoms, and their opacity;
  - colour atoms: the property, how its values are read, the range, and the colour map;
  - force arrows: which vectors, length (with **Auto**), width, the smallest drawn, and colour;
  - which axes are shown, and whether they appear in saved images;
  - a transparent background for saved images;
  - the panel size in pixels, which is also the size of saved images;
  - settings export and import, Save HTML, and Reset view.

These are the same controls and settings as in the ledger viewer's Style, Slice and Planes tabs. Settings files move between the two (⚙ › Settings › Export and Import here, View › Viewer settings there).

### Simple or Advanced controls

"Controls: Simple | Advanced" at the top of ⚙ chooses which controls are shown, in the toolbar and in ⚙. *Simple*, the default (new in this release), shows the controls most pictures need, and every control whose setting differs from its default, so nothing that changes the picture is hidden; *Advanced* shows all of them, as before. Sections with nothing to show disappear; the ⚙ button always stays. In Simple, an advanced control whose setting is in use carries a small grey *adv.* after its label ("Advanced setting, shown because it is in use"); one that a lock overrides (a transformation matrix while *Single cell only* is on) is shown greyed with the lock's tooltip; set back to its default, it stays until ⚙ is closed. Beside the switch, *3 advanced settings active* counts them; click it for the list and choose one to go to it in ⚙ (a closed section unfolds). Some controls are simple only for data with the feature, such as hydrogen bonds for H with O, N or F, and the frame controls for several frames. Switching never changes a setting or the picture. In Python it is `viewer.profile`:

```python
viewer = view(atoms, profile="advanced")   # or later:
viewer.profile = "simple"                  # "simple" or "advanced"; anything else is a ValueError
```

The profile is synced both ways like the settings, and kept in saved HTML files and the ⧉ copy, but it is not a setting: `get_settings()` and settings files do not hold it.

## From Python

```python
viewer = view(trajectory)
viewer.frame = 10          # negative counts from the end
viewer.show_cell = True
viewer.cell_width = 2              # px, up to 6
viewer.cell_colour = "#000000"     # None: the theme's colour
viewer.cell_style = "dashed"       # "solid", "dashed" or "dotted"
viewer.repeat_cell_outline = True   # the outline at every repeated copy (⚙ › Outline every copy)
viewer.single_cell = True   # only the stored cell, nothing from periodic images (⚙ › Single cell only)
viewer.show_bonds = True
viewer.style = "space-filling"    # "ball-and-stick", "space-filling", "stick", "wireframe"
viewer.radius_type = "vdw"         # "covalent", "vdw" or "ionic"
viewer.atom_scale = 0.8
viewer.polyhedra_opacity = 0.6   # 0 to 1; also plane_opacity
viewer.bond_radius = 0.12        # Å
viewer.depth_cue = True          # fade atoms towards the back, by depth_strength (0.1 to 0.9)
viewer.repeat = (2, 2, 1)
viewer.repeat = [[2, 1, 0], [-1, 1, 0], [0, 0, 1]]  # (√3×√3)R30°, see below
viewer.labels = "element"  # "off", "index", "element", "element-index"
viewer.transparent = True  # saved SVGs without a background
viewer.panel_size = (600, 450)
viewer.set_view("c")       # "top", "side-a", "side-b", "a" … "z", "-c" from the other side

viewer.hidden_elements = ["H"]               # not drawn, nor their bonds
viewer.slice = {"c": (0.5, None)}            # fractional window per axis; None: no limit
viewer.element_colours = {"O": "#d62728"}    # others keep their colour
viewer.element_radii = {"Pt": 1.1}           # Å; others automatic (atom_scale)
viewer.bond_cutoffs = {("O", "Ti"): 2.3}     # or {"O-Ti": 2.3}; others default
viewer.bond_cutoffs = {"H-O": (0.8, 1.2)}    # (min, max): shorter bonds are not drawn either
viewer.hydrogen_bonds = True                 # dashed D–H···A lines (see Bond search)
viewer.hydrogen_bond_distance = {"O": (1.5, 2.5), "N": (1.6, 2.6)}  # H···A per acceptor; or (min, max) for all
viewer.bonded_outside = "partners"           # "hide", "partners" or "ligands"
viewer.polyhedron_centres = ["Ti"]           # with viewer.polyhedra = True; None: transition metals
viewer.show_polyhedron_centres = False        # polyhedra without their centre atoms (⚙ › Show centre atoms)
viewer.add_plane(1, 1, 1, t=1)               # h·x + k·y + l·z = t; colour=, show=, scale= (extend, 1 to 10)
viewer.add_plane(0, 0, 1, distance=7.5)      # or the position in Å from the origin (t = distance / d)
viewer.add_plane(atoms=[9, 10, 11])         # the plane through atoms (3, or more for a best fit); patch=True
viewer.planes, viewer.clear_planes()
```

These properties are views onto `viewer.settings`, which is the same settings dictionary the viewer's own controls change. `viewer.frame`, `viewer.settings` and `viewer.camera` are synced both ways:

- What you set in Python is shown at once.
- What you change in the viewer reaches Python once the running cell has finished.

`viewer.selected_atoms` is a copy of the shown frame, including its calculator results:

```python
viewer.frame = 42
atoms = viewer.selected_atoms
```

`viewer.set_images(other_images)` shows other structures and keeps the settings and the view.

## Repeat by a transformation matrix

`viewer.repeat` also takes a 3×3 integer matrix whose rows are the shown cell's vectors in units of the stored a, b and c, for surface cells such as (√3×√3)R30° or c(4×2): `viewer.repeat = [[2, 1, 0], [-1, 1, 0], [0, 0, 1]]` shows the √3 cell of a hexagonal a-b lattice with γ = 120° (`[[1, 1, 0], [-1, 2, 0], [0, 0, 1]]` for γ = 60°, as in ASE's `fcc111`). ⚙ › Transformation matrix has the same 3×3 fields and presets: (√3×√3)R30° (rows for the structure's angle between a and b), c(2×2) (its primitive cell, (√2×√2)R45°), p(2×1) and c(4×2) (its primitive cell). Entries are whole numbers from −12 to 12; the determinant, the number of cell copies, is from 1 to 12³ (a negative determinant, a left-handed cell, is refused: swap two rows). Along a non-periodic axis (c of a slab) the matrix keeps one copy, as the repeat does. A 3-list sets the repeat again and drops the matrix; reading `viewer.repeat` gives the matrix while one is set. Each atom is drawn once per new cell (none twice at its faces) where its position in the stored cell plus a lattice vector falls into the new cell; atoms stored outside the cell stay outside as with the repeat, and `viewer.wrap = True` puts every atom inside the new cell. The new outline is drawn; `viewer.show_stored_cell = True` adds the stored cell, dotted. `viewer.repeat_cell_outline = True` draws the stored-cell grid inside the new cell, dotted: the stored cells' edges cut to the new cell, without those on its outline (this includes the stored cell, so ⚙ › Stored cell outline too is locked meanwhile). Without a matrix it draws the outline at every copy of the repeat, in the outline's own style; edges shared by neighbouring copies are drawn once. Slice windows and Miller planes keep referring to the stored cell (the same h k l and t with and without a matrix); planes are cut to the new cell. Measurements keep their atoms (index and periodic image of the stored cell). It is display only: the frames, saved structures and the cell numbers stay those of the stored cell, and the status line says that a transformation is shown. A diagonal matrix draws exactly what the same repeat draws, apart from the outline (the new cell instead of the stored one).

## Single cell only

`viewer.single_cell = True` (⚙ › Single cell only, for periodic structures; off by default) shows only the stored cell: each atom once, wrapped into the cell, and nothing from periodic images. While it is on, `repeat` counts as 1 × 1 × 1 and a transformation matrix is not applied, atoms are wrapped as with `viewer.wrap = True`, `bonded_outside` counts as `"hide"`, and bonds and hydrogen bonds run only between atoms of the cell. Polyhedra are drawn only when the centre and all ligands lie in the cell itself (one at the cell edge, with a ligand in a neighbouring copy, is left out and its centre drawn as an atom); rings likewise. Planes are clipped to the cell; a patch around atoms is cut at the cell's faces and its extend factor still applies up to them (for planes across the cell ⚙ › Extend × is locked). Labels, arrows and measurements are unchanged: a measurement to a periodic image keeps its value (as with `wrap`). The settings it overrides (`repeat`, `wrap`, `repeat_cell_outline`, `show_stored_cell`, `bonded_outside`) keep their values, so `viewer.single_cell = False` brings the previous view back; in ⚙ (and Wrap in the toolbar) their controls are disabled with the tooltip "Single cell only is on" and show what is in effect (repeat 1 × 1 × 1, Wrap ticked, "hide", no transformation matrix, "Outline every copy" unticked), as is the vibrations' repeat "Apply", and the status line says "single cell only". `viewer.polyhedra(i)` uses the wrapped positions, as the drawing does.

## Drawing styles and radius types

`viewer.style` (⚙ › Model) chooses *ball and stick* (the default: spheres at a third of the radius with bonds or polyhedra, at half without), *space-filling* (spheres at the radius type's radii exactly; no bonds or polyhedra), *stick* (bonds as cylinders, atoms as spheres of the bond radius) and *wireframe* (bonds as thin lines in the atoms' colours, atoms without bonds as small dots). Stick and wireframe always draw bonds, so the toolbar's Bonds box is off for them. The radius type sets the automatic radii: *covalent* (Cordero et al. 2008, the default), *van der Waals* (Alvarez 2013) or *ionic* (Shannon 1976: one ion per element, its usual charge in oxides, halides and chalcogenides, at coordination 6, such as O²⁻ 1.40 Å, Ti⁴⁺ 0.605 Å, Na⁺ 1.02 Å; N³⁻ at coordination 4; H and the noble gases keep their covalent radius). The atom size factor scales them only in ball and stick: space-filling always shows the table's radii, and stick and wireframe atoms take the bond radius, so the size control is off in those styles. A radius set for an element (`element_radii`, ⚙ › Elements) wins in every style except space-filling: that element is drawn as a sphere of that radius, also in stick and wireframe. Space-filling ignores it and its radius fields are off; the stored radii and size factor come back with another style. Nothing switches style by itself: above 3000 atoms the status line suggests wireframe, which draws fastest (on screen its lines are one device pixel wide, saved images draw them 1 px wide, and they lie beneath spheres and polyhedra). Saved SVG and PNG images and videos draw every style with the same circles and lines. Settings files without a style keep today's look. `viewer.radius_type` (⚙ › Radius type) takes `"covalent"`, `"vdw"` or `"ionic"`.

## Bond search

Bonds are drawn from a minimum up to a maximum length per element pair (⚙ › Bond cutoffs, Min and Max; `bond_cutoffs` takes a number for the maximum or `(min, max)`). The minimum defaults to 0; polyhedra, coordination numbers and `viewer.polyhedron()` use the same range. Ring analysis ignores the minimum: it uses its own ring cutoffs, or the bond maximum where none is set. Bonds are found across as many cell copies as the cutoff reaches, so small cells get all their bonds. Settings files from earlier versions, with plain numbers, load unchanged.

⚙ › Bond search draws hydrogen bonds D–H···A as dashed lines in their own colour, on screen and in SVG. The acceptor A and the donor D (the atom bonded to the H) are of the elements in `hydrogen_bond_acceptors` (default `["O", "N", "F"]`); `hydrogen_bond_distance` is the H···A range (default `(1.5, 2.5)` Å) and `hydrogen_bond_angle` the smallest D–H···A angle at the H (default 120°); `hydrogen_bond_colour` sets the colour. For a range per acceptor element (⚙ › Bond search › Per acceptor), give `hydrogen_bond_distance` a dict: `viewer.hydrogen_bond_distance = {"O": (1.5, 2.5), "N": (1.6, 2.6)}` switches per-acceptor ranges on (replacing the stored ones); acceptors without an entry keep the single range, and entries for elements not in `hydrogen_bond_acceptors` are stored but have no effect. While they are on, `hydrogen_bond_distance` reads as a dict of every acceptor element with the range in effect (such as `{"O": (1.5, 2.5), "N": (1.6, 2.6), "F": (1.5, 2.5)}`); writing that value back stores a range for every acceptor, which then no longer follows the single range (↺ beside a row in ⚙ › Bond search undoes that per element); setting `(min, max)` again sets the single range and switches them off.

`bonded_outside` (⚙ › Bond search › Bonded atoms outside) decides what happens to atoms bonded to shown ones but outside the repeat or the slice: `"hide"` (the default), `"partners"` (drawn with their bonds, one step only) or `"ligands"` (only the ligands of shown polyhedra, such as the O of octahedra cut by a slice). These atoms can be hovered and labelled, but they are not counted as shown atoms. Hidden elements stay hidden.

`show_polyhedron_centres = False` (⚙ › Show centre atoms, under Coordination polyhedra) draws the polyhedra without the atoms at their centres: no sphere, label or bonds for an atom that is the centre of a drawn polyhedron, while atoms of the same element with fewer than 4 ligands stay; the hidden centres still count as shown atoms, keep their colour scale, and can be hovered and clicked inside their polyhedron (for 📏 › Polyhedron).

## Colouring by a per-atom property

Atoms can be coloured by any per-atom value of the frames:

- **Calculator results:** charges, magnetic moments, forces and the like.
- **ASE arrays:** such as `tags`, or extxyz columns.
- **Per-atom lists:** in `atoms.info`.
- **Values from the geometry:** coordination number (from the bond cutoffs), atom index, Cartesian x, y and z, fractional coordinates, and the displacement from a reference frame (see [Displacements](#displacements)).

Choose **Colour › Property** in the toolbar, then the property under ⚙ › Colour atoms, or set it from Python:

```python
viewer.colour_by("charges", palette="diverging", symmetric=True)   # signed values, centred on 0
viewer.colour_by("tags")                                          # whole numbers: one colour each
viewer.colour_by("forces", component="z")                         # a vector: its norm (default) or a component
viewer.colour_by("magmoms", range=(0, 3))                         # fixed ends of the colour scale
viewer.colour_by(None)                                            # back to element colours
```

- **Categories or a scale:** with `kind="auto"`, whole numbers with at most 12 distinct values (such as tags) become categories, each with its own colour. Other values get a colour scale.
- **One scale for all frames:** the automatic ends cover the shown atoms of every frame, so colours mean the same throughout a trajectory. `range` fixes them; values outside get the end colours.
- **Choosing a source:** when the same name exists in several places, `source=` picks one (`"calculator"`, `"arrays"`, `"info"`).
- **Palettes:** viridis by default; others include `"diverging"` for signed values, `"plasma"` and `"turbo"`. See the viewer's ⚙ › Colour map.
- **In the figure:** a legend under the structure shows the scale or the categories, and the hover tooltip shows each atom's value. Atoms without a value keep their element colour. Saved SVGs use the same colours.

The colouring is part of the settings, so `get_settings()` reproduces it on other structures with the same property.

## Force arrows

Arrows show the calculator forces of each frame (`atoms.calc.results["forces"]`). They can also show any other per-atom 3-vector, such as an extxyz `REF_forces` column; choose it under ⚙ › Arrows. Turn them on with **Arrows** in the toolbar or from Python:

```python
viewer.show_forces = True
viewer.force_scale = 1.5   # Å of arrow per eV/Å
```

- **Auto** under ⚙ › Arrows makes the largest vector of all frames a 1.5 Å arrow.
- Arrows start on the atom's surface and follow the frame shown.
- An arrow pointing straight at you has no length on screen and is not drawn.
- They are part of the settings, so `get_settings()` reproduces them; they are also in saved SVGs.

## Displacements

With two frames or more, arrows can show how far each atom has moved from a reference frame instead: choose **Displacement** under ⚙ › Arrows, or from Python:

```python
viewer.show_displacements()            # from the first frame
viewer.show_displacements("previous")  # from the frame before the shown one
viewer.show_displacements(5)           # from frame 5 (negative indices count from the end)
viewer.arrow_source = "vectors"        # back to forces
```

- **Minimum image:** along periodic axes the shortest displacement over periodic images is drawn, so an atom that crossed a cell face gets a short arrow.
- **Different cells** (after a cell relaxation): the reference's fractional coordinates are taken in the shown frame's cell, and the status line says so.
- **Status line:** the RMSD and the largest displacement of the shown frame, with its atom.
- **Colours:** `viewer.colour_by("displacement")` colours atoms by the length of their displacement (or a component, `component="z"`), from the same reference; the colour scale covers all frames.
- Frames need the same atoms in the same order; the reference frame itself has no arrows.

## Measurements

Click **📏**, choose Distance, Angle or Dihedral, and click the atoms in the structure; Esc cancels a measurement you've started.

- **Drawn in the figure:** measurements appear as dashed lines with their values, also in saved SVGs.
- **Listed:** the list under 📏 gives each value; a distance also shows the distance to the nearest periodic image when that is shorter.
- **They follow the frames:** a measurement names atoms by index, so stepping through a trajectory shows its value in every frame.

In Python, once the cell has finished:

```python
viewer.measurements
# [{'kind': 'distance', 'atoms': [0, 1], 'images': [(0, 0, 0), (0, 0, 0)],
#   'value': 0.969, 'unit': 'Å', 'nearest': None}]
```

`images` gives the periodic image of each atom as clicked; it is non-zero for atoms in a repeated cell copy. `value` is for the shown frame. Measurements are kept in ⧉ tabs, in `save("x.html")` files and in `get_settings()` (see below).

## Planes through atoms

⚙ › Planes › **Plane through atoms** turns clicks into picks: click 3 atoms (more give the least-squares plane; a second click drops an atom), then **Make plane**. `viewer.add_plane(atoms=[i, j, k])` does the same from Python (indices of the shown frame, or atom refs as in measurements for periodic images; atoms on a line are refused). Like a measurement, the plane names its atoms by index and periodic image, so it follows the frames, and on a frame with other atoms it is not drawn and its row says why. Its row also gives the fit: "Through 3 atoms", or the RMS and largest deviation of the atoms from a best-fit plane. It is drawn where it cuts the shown cell (the repeat, or the cell of a transformation matrix), as Miller planes are; with *Patch around the atoms* (`patch=True`), and always for a structure without a cell, it is a patch around its atoms instead, 1 Å wider. *Extend ×* (`scale=` in `add_plane`, 1 to 10, also for Miller planes) enlarges a drawn plane by that factor in all in-plane directions about its centre, beyond the cell outline or the patch. Its colour, opacity and visibility work as for Miller planes, in every drawing style and in saved SVG, PNG and video. Each Miller plane's row lists its spacing d.

Under 📏, **Plane angle** gives the angle between two planes (Miller or through atoms; 0 to 90°), and **Distance to a plane** the signed distance of each clicked atom from the chosen plane, along its normal. The normal of a plane through atoms points to the side the surface normal points to (up for a slab), so the distance is the height above the plane and differs from the Info heights by the plane's height; a Miller plane's normal is h·a* + k·b* + l·c*. The distance is drawn as a dashed line to the plane. Such a measurement keeps the planes as they were when measured (Miller indices and t, or the atoms), not a link to the Planes list; `viewer.measurements` lists them with `"planes"`, and settings files carry them as `{"kind": "plane-angle", "atoms": [], "planes": [{"h": 0, "k": 0, "l": 1, "t": 0.5}, {"atoms": [ref, ...]}]}` or `{"kind": "plane-distance", "atoms": [ref], "planes": [plane]}`.

## Polyhedra

Choose **Polyhedron** under 📏 and click an atom: the list "Polyhedra" shows its coordination polyhedron. The ligands are its bonded non-metals within the bond cutoffs, the same rule as drawn polyhedra, but polyhedra need not be drawn and any atom can be the centre. For each polyhedron you get the coordination number, the ligands, the sorted bond lengths and their mean, the volume of the ligands' convex hull, the distortion index (Baur), the quadratic elongation and bond-angle variance (Robinson et al.; for 4 and 6 ligands, against the regular tetrahedron and octahedron of the same volume) and the effective coordination number (Hoppe, as VESTA computes it). Entries follow the frames; on a frame with other atoms they are left out, with a note. **Copy as CSV** copies the table. The entries live in the page only: they are not kept in `get_settings()` or saved HTML.

The same numbers from Python, with the viewer's bond cutoffs, or without a viewer:

```python
viewer.polyhedron(0)                  # atom 0 on the shown frame
viewer.polyhedron(0, frame=3)
from stoms.analysis import polyhedron
polyhedron(rutile, 0, cutoffs={"O-Ti": 2.4})   # rutile TiO2
# {'index': 0, 'symbol': 'Ti', 'cn': 6, 'ligands': [...], 'lengths': [...],
#  'mean': 1.959, 'volume': 9.906, 'distortion_index': 0.00713,
#  'quadratic_elongation': 1.00802, 'bond_angle_variance': 28.08, 'econ': 5.988}
```

## Symmetry

With the optional `symmetry` extra (`pip install "stoms[symmetry]"`, which installs spglib), the viewer knows each frame's space group: the status line below the structure shows it with the crystal system, ⚙ › Symmetry shows it with the tolerance (default 0.01 Å), hovering an atom shows its Wyckoff letter and site symmetry, and Colour › Atomic property › "Equivalent site (symmetry)" colours each inequivalent site. Frames without a 3D cell (molecules, slabs with a non-periodic axis) have none. Python computes the symmetry when the viewer is made and embeds it in the page, so saved HTML files show it too. Another tolerance, set under ⚙ or with `viewer.symmetry_tolerance = 0.1`, is computed by Python while the viewer is linked to the kernel; a saved page shows only the tolerance it was saved with. For trajectories, frames are embedded until their atoms add up to 5000; later frames are computed when shown (linked viewers only). Without spglib in the kernel's environment nothing is embedded and ⚙ › Symmetry names the extra.

```python
viewer.symmetry_tolerance = 0.05      # Å; recomputes
viewer.colour_by("equivalent")        # one colour per inequivalent site
from stoms.analysis import symmetry
result = symmetry(rutile)             # tolerance=0.01 by default
result.symbol, result.crystal_system  # ('P4_2/mnm (136)', 'tetragonal')
result.wyckoffs                       # ('a', 'a', 'f', 'f', 'f', 'f')
result.equivalent_atoms               # (0, 0, 2, 2, 2, 2)
```

## Saving an SVG

```python
viewer.save("structure.svg")   # in a cell after the one that displays the viewer
```

The browser draws the structure, so the SVG comes from the browser too. After every change it sends the SVG of what it shows, and `save()` writes that SVG. It is the same file as the **Save SVG** button produces: circles with shading and outlines for atoms, lines for bonds and cell edges, polygons for polyhedra and planes, and text for labels. It never contains an embedded raster image. Its size is the panel size in pixels (`panel_size`, or ⚙ › Panel width × height).

`save()` raises `StaleViewError` instead of writing an outdated picture:

- **when the viewer hasn't been displayed yet**, because no browser has drawn it;
- **when you changed the view from Python in the same cell**, for example `viewer.frame = 3; viewer.save(...)`. Jupyter only delivers the browser's new drawing after the cell has finished, so call `save()` in the next cell.

`viewer.save("view.html")` writes a standalone, interactive HTML file. It needs no Python to open, and you can send it to colleagues.

## The same look for several structures

```python
settings = viewer.get_settings()   # settings and the view (camera)

for name, atoms in reconstructions.items():
    other = view(atoms, settings=settings)
    display(other)
```

`get_settings()` returns a settings file of the form `{"stoms_viewer_settings": 1, "settings": …, "view": …, "measurements": […]}`. It includes the camera: rotation, zoom in pixels per Å, and pan. Structures with the same cell are therefore drawn at the same scale and orientation.

Measurements are stored by atom: index, periodic image, element, and the structure's atom count; their values are not stored. Another structure with the same atoms at those indices gets the same measurements, measured anew, such as a relaxed copy or another frame. A structure with other atoms shows them in the 📏 list with "–" and doesn't draw them. ⚙ › Settings › Export and Import carry measurements too. Save it with `json.dump` to reuse it later; `view(atoms, settings="look.json")` reads it back. The ledger viewer imports the same files and ignores the camera and the measurements.

## Phonons: vibrational modes, band structure and DOS

```python
from stoms.viewer import view_phonons

viewer = view_phonons("phonopy_params.yaml")       # pip install "stoms[jupyter,phonopy]"
viewer
```

This shows the same Vibrations panel and band-structure/DOS plot as `stoms --file phonopy_params.yaml serve`:

- **Modes:** pick a mode, play it, record a video, or show the displacements as arrows.
- **Any q-point:** type a q, or click on the bands to go to that q and mode.
- **NAC and LO–TO splitting:** for polar crystals with Born charges, NAC can be switched off. At Γ, the direction q approaches from sets the splitting.
- **Wavelength hint:** at q ≠ 0, a hint gives the repeat that shows a whole wavelength.

The viewer asks Python for every q-point, band structure and DOS, and phonopy computes them in your kernel. It needs no ledger and no server. Saving SVG, settings and the view work as for any other viewer.

`view_phonons()` accepts the same inputs as `stoms --file … serve`:

```python
view_phonons("phonopy_params.yaml")                                    # force constants or forces inside, or a FORCE_* file next to it
view_phonons("POSCAR", dim="4 4 4", force_constants="FORCE_CONSTANTS") # or force_sets="FORCE_SETS"
view_phonons("POSCAR", dim=[2, 2, 2], force_sets="FORCE_SETS", born="BORN", dos_mesh=30)
view_phonons(phonon)                                                   # a phonopy.Phonopy object you already have
view_phonons("phonopy_params.yaml", band="0 0 0  0.5 0 0.5, 0.375 0.375 0.75  0 0 0", band_labels="Γ X K Γ")
```

A `BORN` file next to the input turns NAC on, as with `stoms serve`. Without `band`, seekpath chooses the band path. `viewer.phonons` is the loaded calculation; `viewer.phonons.phonon` is the phonopy object.

Because these values are computed on request, the viewer needs its kernel:

- **In the notebook:** when the kernel has stopped, a new q-point gives the message "computed in Python … with the kernel running".
- **⧉ tabs:** they keep every q-point already shown in the notebook, but can't compute new ones.
- **`viewer.save("x.html")`:** stores the modes at Γ, the band structure and the DOS, so the file shows them with no Python. Other q-points need the notebook.

## Opening the viewer separately

- **⧉ in the viewer** opens a browser tab with a copy of the viewer. It works for local and remote notebooks alike, because the copy is made in your browser.
- **`viewer.open_in_browser()`** writes the HTML file and opens it in a browser on *the computer running the kernel*. That is useful for local notebooks, but on a remote server it opens nothing on your screen.
- **`viewer.save("view.html")`** writes the HTML file for you to open anywhere.

## Remote Jupyter and SSH tunnels

The viewer needs no port of its own. Its page is part of the notebook output, and the link to Python uses the kernel's own connection. Viewing, saving SVG from Python and the ⧉ tab therefore work wherever the notebook works, including JupyterLab or Notebook 7 reached through an SSH tunnel. Files written with `save()` are on the server.

## Without anywidget

Without the `jupyter` extra, or with `view(..., static=True)`, `view()` returns a `StaticView`. It is the same viewer as HTML output, fully interactive in the browser (including Save SVG and ⧉), but not linked to Python:

- Python does not see frame, settings or view changes;
- `save()` writes `.html` only;
- `set_view` is not available.

## Limitations

- **Theme:** the viewer follows your operating system's light or dark setting, not the JupyterLab theme.
- **Notebook previews:** outputs are only interactive in frontends that run scripts in outputs (JupyterLab, Notebook 7, VS Code). GitHub and nbviewer previews show nothing. A notebook reopened without a running kernel shows the widget as text.
- **Not available in notebooks yet:**
  - ring analysis, and colouring by ring size;
  - modes from v_sim files (phonopy calculations work, see [Phonons](#phonons-vibrational-modes-band-structure-and-dos));
  - side-by-side comparison;
  - PNG export from Python;
  - perspective projection (the projection is orthographic).

  Use `stoms --file … serve` for these.
- **Size:** large trajectories make the notebook file large, because the widget output stores the frames.
