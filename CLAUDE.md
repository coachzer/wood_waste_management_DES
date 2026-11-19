# CLAUDE.md

SimPy DES of wood waste management in Slovenia: generators in 12 regions produce EWC-coded waste, collectors move it, treatment operators make MDF, particle board and OSB. Monte Carlo over `InventoryPolicy` (push/pull) x `StockStrategy` (on_demand/reorder_50/reorder_90).

## Running

```bash
.venv/bin/python main.py --mode baseline --scenario Baseline --replications 50
.venv/bin/python -m analysis.paired_comparison outputs/baseline/Baseline
```

Outputs: `outputs/baseline/{scenario}/{policy}__{strategy}/`. Seeds are CRN: replication `i` uses `base_seed + i` for every combo; `paired_comparison` exploits the pairing.

## Traps

- **Sort enum sets.** Enum members hash by `id()`, so iterating a set of `WasteType`/`OutputType` breaks per-seed reproducibility silently. On ordered-work paths, iterate `models.enums.sorted_by_value(...)` and keep a `List`. Guarded by `tests/test_enum_set_ordering.py`, `tests/test_determinism.py`.
- **PULL needs treatment orders.** If `TreatmentOperator._order_volumes_by_waste_type()` returns nothing, collectors stall.
- **PUSH ignores signals**; under PULL, generators emit none (ADR 0032), collectors serve largest order first (ADR 0031), short operators also signal the richest region (ADR 0033).

## Conventions

- Commits: `type(scope): Imperative subject` (<72 chars; feat/fix/docs/test/refactor/chore), body says why. Changes that can shift results need an `Affects: <what>` trailer. Enforced by `.githooks/commit-msg` (`git config core.hooksPath .githooks`).
- New waste types or products: `docs/adding-waste-types.md`.

## Done means

`.venv/bin/python -m pytest --run-slow` passes (slow tests include determinism). Run it in the background.

## Agent skills

### Issue tracker

GitHub Issues on coachzer/wood_waste_management_DES, via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/decisions.md` (one file, entries keyed by ADR number). See `docs/agents/domain.md`.
