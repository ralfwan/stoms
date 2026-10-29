# VASP test data

## `uma2x3b_74/`

`vasprun.xml` from the owner's r2SCAN single-point calculation
`sto-2xn/vasp/uma2x3b_74` (SrTiO3 slab, VASP 6.2.0, run 2024-02-25).
`tests/test_vasp_parser.py` uses it to check that method and provenance stay
distinct on real output.

Only `vasprun.xml` is included. `POTCAR` is missing because the VASP licence
forbids redistributing it; the parser falls back to the dataset titles stored
in `vasprun.xml`. `INCAR` and `KPOINTS` are left out as well; the parser uses
the INCAR values and actual k-points from `vasprun.xml` and records a warning
for each missing file.
