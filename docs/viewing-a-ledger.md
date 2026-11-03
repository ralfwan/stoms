# Viewing a STOMS ledger

2026-10-08 · Ralf Wanzenböck

Install STOMS 0.9.0 from PyPI, then start its local web viewer on the ledger file you received. It takes about five minutes and runs only on your machine.

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
    uvx stoms@0.9.0 --ledger data.ledger serve --open
    ```

Nothing else to set up: `uvx` keeps STOMS in its own environment, separate from any project. If you'd rather have a plain `stoms` command, install it once with `uv tool install stoms@0.9.0` and then run `stoms --ledger data.ledger serve --open`.

## Option B: conda

STOMS is on PyPI, not on conda-forge, so you create a conda environment and install STOMS into it with pip. This works the same with mamba or micromamba.

1. Create and activate an environment:

    ```bash
    conda create -n stoms -c conda-forge python=3.12 pip
    conda activate stoms
    ```

2. Install STOMS:

    ```bash
    pip install stoms==0.9.0
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
- **Your own files:** "+ Add structures" in the sidebar opens structure files (extxyz, POSCAR/CONTCAR, CIF, OUTCAR, …) next to the ledger's data, to view and compare them. They are kept only while the viewer runs and are not written to the ledger.
- **Wrap atoms into cell:** a setting in the View tab of the structure viewer (off by default). It draws every atom inside the cell, as ASE's `Atoms.wrap` does: along each periodic direction, an atom is moved by a cell vector so it lies in the cell. With a repeat, each copy fills its own cell. Bonds, measurements, height colouring and ring height windows use the drawn positions; the Info tab and exported files keep the stored ones. In a trajectory, an atom that crosses a cell face jumps to the other side.
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
uvx stoms@0.9.0 --file frames.extxyz serve --open
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

`--file` also takes phonopy output, and the structure page then gets a **Vibrations** section that animates the modes. A phonopy calculation (the yaml, or a structure with its force constants) needs the `phonopy` extra: run the commands below as `uvx --from "stoms[phonopy]==0.9.0" stoms …`, or install it with `uv tool install "stoms[phonopy]==0.9.0"` or `pip install "stoms[phonopy]==0.9.0"`. v_sim files need no extra.

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
