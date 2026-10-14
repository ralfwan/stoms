# Viewing a STOMS ledger

2026-10-08 · Ralf Wanzenböck

Install STOMS 0.5.0 from PyPI, then start its local web viewer on the ledger file you received. It takes about five minutes and runs only on your machine.

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
    uvx stoms@0.5.0 --ledger data.ledger serve --open
    ```

Nothing else to set up: `uvx` keeps STOMS in its own environment, separate from any project. If you'd rather have a plain `stoms` command, install it once with `uv tool install stoms@0.5.0` and then run `stoms --ledger data.ledger serve --open`.

## Option B: conda

STOMS is on PyPI, not on conda-forge, so you create a conda environment and install STOMS into it with pip. This works the same with mamba or micromamba.

1. Create and activate an environment:

    ```bash
    conda create -n stoms -c conda-forge python=3.12 pip
    conda activate stoms
    ```

2. Install STOMS:

    ```bash
    pip install stoms==0.5.0
    ```

3. Start the viewer:

    ```bash
    stoms --ledger data.ledger serve --open
    ```

Next time, only `conda activate stoms` and step 3 are needed.

## Browse the data

The terminal prints `Serving data.ledger at http://127.0.0.1:8765/ (Ctrl+C to stop)`, and `--open` opens that page in your browser. If no browser opens, copy the address into one yourself.

On Linux inside Windows (WSL) there is usually no Linux browser, so `--open` cannot start one. Open the address in your Windows browser; it reaches the viewer running in WSL. To make `--open` use the Windows browser, install `wslu` (`sudo apt install wslu`) and add `export BROWSER=wslview` to your `~/.bashrc`.

- **Homepage:** lists the aggregations in the ledger, the named sets of structures.
- **An aggregation:** shows a summary (evaluation coverage and a histogram per property), the member table, and an "Export to extxyz" panel.
- **A structure:** click the eye icon next to a member, or "View" above the table to step through all (or only the selected) members in the structure viewer.

The viewer is read-only and never changes the ledger file. Leave the terminal open while you browse, and press Ctrl+C there to stop it.

If the terminal reports that the address is already in use, add `--port 0` after `serve`. STOMS then picks a free port and prints the new address.

## Viewing an extxyz file

The same viewer also opens a single extxyz file instead of a ledger. Use `--file` in place of `--ledger`:

```bash
uvx stoms@0.5.0 --file frames.extxyz serve --open
```

Every frame appears in file order, as one aggregation named after the file. Energies and forces stored in the file (for example `REF_energy` and `REF_forces`, or plain `energy` and `forces`) are shown as the frame's evaluation. The file is only read; exports from it copy the chosen frames unchanged.
