# Frozen oracle — 100-rep baseline (tag `frozen-oracle-100rep`)

Tamper-evident reference for the `refactor/clean-monitoring` branch. This directory holds a
**SHA256 manifest only** — never the run data itself. The simulation is byte-deterministic per
seed (CRN: `seed = base_seed + i`), so anyone with the repo regenerates the runs by running the
code; git stores a fingerprint, not the regenerable artifacts.

## Provenance

- Source commit (code that produced the oracle): **`3964639`**
- Command: `python main.py --mode baseline --scenario Baseline --replications 100`
- `base_seed = 123456`, `replications = 100`, `scenario = Baseline`
- 6 combos x 100 reps = **600 runs** (600 `run_NNN.json` + 600 `raw_NNN.json` sidecars)
- Behaviour matches golden `baseline-3` (ADR 0010 / C3): 10-rep additive gate = MATCH (60 runs, 0 mismatched)

## What the manifest covers

`manifest.sha256` — 1200 entries, one per file, paths relative to repo root:
- 600 `outputs/baseline/Baseline/<combo>/run_NNN.json` (KPI-bearing run files, ~2.4 MB total)
- 600 `outputs/baseline/Baseline/<combo>/raw_NNN.json` (raw monitor sidecars, ~4.0 GB total, local-only)

## How the refactor branch verifies (no stored data, no trust)

The branch `refactor/clean-monitoring` is cut from the tag `frozen-oracle-100rep` and may never
regenerate its own reference. To verify a slice preserved behaviour bit-for-bit:

```bash
# 1. Regenerate the 100-rep freeze from the (refactored) code
python main.py --mode baseline --scenario Baseline --replications 100
# 2. Verify every regenerated run + raw blob against the frozen fingerprint
sha256sum -c frozen-oracle/manifest.sha256        # expect: all OK
```

Any mismatch means the slice changed simulation behaviour and must be reverted or explained.
This is the raw-vs-raw EXACT gate from ticket issues 01 and 13.

## Regenerating the manifest (only at a fresh freeze)

```bash
find outputs/baseline/Baseline -type f \( -name 'run_*.json' -o -name 'raw_*.json' \) \
  | LC_ALL=C sort | xargs sha256sum > frozen-oracle/manifest.sha256
```
