# OSB does not accept sawdust (03 01 05) — code supersedes the thesis mapping

Date: 2026-06-11
Status: accepted

## Context

The thesis (§6.1, p28-29) lists `03 01 05` (sawdust, shavings and cuttings)
among OSB's input waste streams; the code's transformation catalogue
(`models/transformations.py::WASTE_TO_OUTPUT_TYPES`) maps `03 01 05` to
particle board and MDF only. This was the last open thesis-vs-code mapping
disagreement (THESIS-RECONCILIATION §C, TASKLIST #36/#37): every such gap
needs an explicit ruling — intentional improvement (keep code) or accidental
drift (bug to fix). The unification commit `760cfd1` had already dropped a
phantom sawdust-to-OSB fallback row that no runtime path exercised, but the
ruling itself was never recorded.

## Decision

The code is correct; the thesis table is in error. OSB — *oriented strand*
board — is manufactured from wood strands/flakes cut from solid wood and
oriented in layers; sawdust, shavings and cuttings are too fine to form
strands and physically cannot be oriented. Industry routes `03 01 05` to
particle-board core material and MDF fiber, exactly what the catalogue
encodes. `03 01 05 -> {PARTICLE_BOARD, MDF}` stands; no OSB pathway is added.

## Consequences

- No code or output change — this ADR records a ruling, not a behavior shift.
- The transformation catalogue in `models/transformations.py` remains the
  single source of truth and now has no undocumented divergence from the
  thesis: the remaining differences (forestry `02 01 07` and other-wood
  `03 01 99` mapped in code but under-described in the thesis) were ruled
  intentional on 2026-06-09 (live in 6 of 12 regions' data).
- Any future paper must not copy the thesis Table's OSB input list; it should
  cite the catalogue. The thesis abstract/figure inconsistencies are recorded
  in THESIS-RECONCILIATION §D and are likewise not to be carried over.
