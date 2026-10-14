---
status: accepted
---

# Default units for standard properties

STOMS assigns default units during ingestion for its initial standard numerical
properties: energy and node energy use `eV`, and forces use `eV/angstrom`.
Callers may explicitly override a property unit, which remains stored with the
immutable evaluation. This removes routine ingestion boilerplate without
silently discarding non-default units; mixed-unit projections still fail.
