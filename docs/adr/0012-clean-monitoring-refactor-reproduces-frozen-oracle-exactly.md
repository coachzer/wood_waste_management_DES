# The clean-monitoring refactor reproduces the frozen oracle exactly, at zero tolerance

Date: 2026-06-07
Status: accepted

## Context

The `clean-monitoring` refactor (issues 00–12, branch `refactor/clean-monitoring`) restructured the
monitoring/analysis layer into four spaces — `instrumentation/` (live recorders + the in-memory store),
`persistence/` (the one serializer + `jsonify` encoder), `analysis/` (`extract_kpis` + bullwhip/flow/
carbon + paired/SD/pareto), `visualization/` (all plotting) — and inverted the
`models/data_classes.py -> monitoring.waste_monitor` import so the dependency arrows point one way. It
moved code: recorder injection, the `monitoring/__init__` re-export removal, the module relocations, the
WasteMonitor split into recorder/serializer/store, namespace de-duplication, and output-path
centralization. None of it was meant to change a single number — it is pure structure, the
"clean before the paper" step.

A structural refactor that silently moves a result is the failure mode this whole sequence was built to
prevent. So the merge criterion was set to **"reproduces the frozen dataset exactly," not "tests pass."**
The reference is the tag **`frozen-oracle-100rep`** on `main` (commit `2b23dcc`): the behaviour was
golden-locked to `baseline-3` (ADR 0010 / C3), the 100-rep oracle frozen, and only the manifest committed
to git — `frozen-oracle/manifest.sha256`, covering all 600 `run_NNN.json` (kpis) and 600 `raw_NNN.json`
(raw history) blobs. The sim is byte-deterministic per seed, so the run data itself is regenerable and
stays out of git; the manifest is the tamper-evident reference. The branch cannot regenerate its own
oracle — it can only reproduce or fail against the tag.

## Decision

**`frozen-oracle-100rep` is the behavioral oracle for this refactor, and reproduction is enforced at zero
tolerance — exact byte equality throughout. No blanket tolerance, and no ULP exception was needed or
granted.**

The gate philosophy (clean-monitoring INDEX): every slice is pure structure and cannot legitimately move
a number, so `compare_baselines.py` stays exact (`!=`), and the raw-vs-raw comparator (issue 01) checks
regenerated blobs against the committed manifest. A per-step ULP exception would have been admissible only
if some step provably had to reorder floating-point operations. **None did** — the relocations and import
inversion preserved evaluation order, so exact equality held end to end and the exception clause is unused.

## Verification (the merge gate, this session)

The fully-refactored code at branch HEAD regenerated the 100-rep Baseline dataset to default `outputs/`
(600 runs) and was checked against the tag:

1. **Raw + kpis byte-identical.** All **1200/1200** manifest entries verified — 600 raw sidecars + 600
   kpis `run` files — `0 FAILED`, `0 missing` (`sha256sum -c frozen-oracle/manifest.sha256`;
   `compare_raw verify` independently reports the raw side MATCH 600/600). Byte-identical `run` files is a
   *stronger* result than the additive kpis gate, which only tolerates new namespaces: there are no
   new namespaces and no changed values — the kpis are bit-for-bit the oracle's.
2. **Full pytest green:** 184 passed, 6 skipped (`tests/`).
3. **Grid mass-balance clean:** the full `MassBalanceMonitor` suite (continuous, final, waste-system,
   collection-centers, yield-bridge) raised on no combo across all **30** scenario×policy×strategy
   configurations with `raise_on_violation=True`.

The refactor moved recording and serialization across module boundaries (the WasteMonitor split most of
all) yet perturbed neither the raw history nor the derived KPIs. That is the result the four-space layout
was supposed to guarantee, confirmed rather than assumed.

## Consequences

The branch is clear to merge to `main`; the merge unblocks Phase 4 (the paper). Because reproduction is
exact, the refactor cannot have moved any published number — the paper consumes the same `baseline-3`
numbers whether it reads pre- or post-refactor code.

**One environment caveat, out of scope for this refactor.** `python main.py` (grid mode) exits non-zero in
a Chrome-less environment: `visualization/mfa_visualization.py` calls `fig.write_image(pdf_path)`, and
Kaleido requires Google Chrome. This is **pre-existing** — the PDF export dates to commit `ca7e6a0`, long
before this branch, and is present identically on `main` — and it fires only *after* the simulation
completes and the mass-balance suite has already passed, so it does not affect any gate result above. The
grid mass-balance was therefore verified with `create_mfa=False`, which skips only the Chrome render. Left
unfixed here under surgical-change discipline; a candidate for the post-merge landmines track if the
grid-mode papercut is worth closing.

Two reference notes inherited by this branch, neither a reproduction concern: the husk
`visualization/demand_visualization.py` is imported by nobody and sits off every output path (left
untouched); the stale `monitoring/` paths in ADRs 0008/0009/0011 predate the four-space move and, being
append-only past records, are left as written.
