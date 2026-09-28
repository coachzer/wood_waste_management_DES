# OSB does not accept sawdust (03 01 05), and the code supersedes the thesis mapping

Date: 2026-06-11
Status: accepted

## Context

The thesis (§6.1, p28-29) lists `03 01 05` (sawdust, shavings and cuttings)
among OSB's input waste streams. The code's transformation catalogue
(`models/transformations.py::WASTE_TO_OUTPUT_TYPES`) maps `03 01 05` to
particle board and MDF only. This was the last open disagreement between the
thesis and code mappings (THESIS-RECONCILIATION §C, TASKLIST #36/#37). Every
such gap needs an explicit ruling: an intentional improvement (keep the code) or
accidental drift (a bug to fix). The unification commit `760cfd1` had already
dropped a phantom sawdust-to-OSB fallback row that no runtime path used, but
the ruling itself was never recorded.

## Decision

The code is correct and the thesis table is wrong. OSB (*oriented strand*
board) is made from wood strands or flakes cut from solid wood and oriented in
layers. Sawdust, shavings and cuttings are too fine to form strands and cannot
be oriented. Industry routes `03 01 05` to particle-board core material and MDF
fiber, which is what the catalogue encodes. `03 01 05 -> {PARTICLE_BOARD, MDF}`
stands, and no OSB pathway is added.

## Consequences

- No code or output change. This ADR records a ruling, not a behavior change.
- The transformation catalogue in `models/transformations.py` remains the
  single source of truth and now has no undocumented divergence from the
  thesis. The remaining differences (forestry `02 01 07` and other-wood
  `03 01 99`, mapped in code but under-described in the thesis) were ruled
  intentional on 2026-06-09 (they appear in 6 of 12 regions' data).
- Future papers must not copy the thesis table's OSB input list and should
  cite the catalogue instead. The thesis abstract and figure inconsistencies
  are recorded in THESIS-RECONCILIATION §D and must not be carried over either.
