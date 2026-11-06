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
- **📏** measures distances, angles and dihedrals. See [Measurements](#measurements).
- **⧉** opens the viewer in a new browser tab. The tab is a copy with the current frame, settings and view; it is not linked to Python.
- **⚙** opens more settings:
  - repeat a × b × c, the cell outline (width, colour, solid/dashed/dotted), atom labels, coordination polyhedra (and their opacity), bond radius, and depth cueing (and how far it fades);
  - slicing: which elements are shown, and a window of fractional coordinates per axis;
  - per-element colours and radii, bond cutoffs and polyhedron centres;
  - Miller planes, with their position as t or in Å, and their opacity;
  - colour atoms: the property, how its values are read, the range, and the colour map;
  - force arrows: which vectors, length (with **Auto**), width, the smallest drawn, and colour;
  - which axes are shown, and whether they appear in saved images;
  - a transparent background for saved images;
  - the panel size in pixels, which is also the size of saved images;
  - settings export and import, Save HTML, and Reset view.

These are the same controls and settings as in the ledger viewer's Style, Slice and Planes tabs. Settings files move between the two (⚙ › Settings › Export and Import here, View › Viewer settings there).

## From Python

```python
viewer = view(trajectory)
viewer.frame = 10          # negative counts from the end
viewer.show_cell = True
viewer.cell_width = 2              # px, up to 6
viewer.cell_colour = "#000000"     # None: the theme's colour
viewer.cell_style = "dashed"       # "solid", "dashed" or "dotted"
viewer.show_bonds = True
viewer.atom_scale = 0.8
viewer.polyhedra_opacity = 0.6   # 0 to 1; also plane_opacity
viewer.bond_radius = 0.12        # Å
viewer.depth_cue = True          # fade atoms towards the back, by depth_strength (0.1 to 0.9)
viewer.repeat = (2, 2, 1)
viewer.labels = "element"  # "off", "index", "element", "element-index"
viewer.transparent = True  # saved SVGs without a background
viewer.panel_size = (600, 450)
viewer.set_view("c")       # "top", "side-a", "side-b", "a" … "z", "-c" from the other side

viewer.hidden_elements = ["H"]               # not drawn, nor their bonds
viewer.slice = {"c": (0.5, None)}            # fractional window per axis; None: no limit
viewer.element_colours = {"O": "#d62728"}    # others keep their colour
viewer.element_radii = {"Pt": 1.1}           # Å; others automatic (atom_scale)
viewer.bond_cutoffs = {("O", "Ti"): 2.3}     # or {"O-Ti": 2.3}; others default
viewer.polyhedron_centres = ["Ti"]           # with viewer.polyhedra = True; None: transition metals
viewer.add_plane(1, 1, 1, t=1)               # h·x + k·y + l·z = t; colour=, show=
viewer.add_plane(0, 0, 1, distance=7.5)      # or the position in Å from the origin (t = distance / d)
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

## Colouring by a per-atom property

Atoms can be coloured by any per-atom value of the frames:

- **Calculator results:** charges, magnetic moments, forces and the like.
- **ASE arrays:** such as `tags`, or extxyz columns.
- **Per-atom lists:** in `atoms.info`.
- **Values from the geometry:** coordination number (from the bond cutoffs), atom index, Cartesian x, y and z, and fractional coordinates.

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
