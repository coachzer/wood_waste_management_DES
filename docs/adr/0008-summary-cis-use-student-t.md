# Summary.csv confidence intervals use Student-t uniformly

> NOTE (2026-09-28): the `monitoring/` package no longer exists. `monitoring/paired_comparison.py` is now
> `analysis/paired_comparison.py`. The decision is unchanged.

When we added the Monte Carlo `bullwhip` KPIs to per-combo `summary.csv` (issue 06),
we switched every CI in that file, both the marginal KPIs and the new `bullwhip.*`
rows, from the earlier `z = 1.96` normal approximation to a Student-t interval
`t(0.975, n-1) * stdev / sqrt(n)`. It is computed with `scipy.stats.t.ppf`, the same
path `monitoring/paired_comparison.py` already uses. When the population variance is
unknown and estimated from the replications, the t-interval is the correct small-n
interval. At the default `--replications 10`, the z approximation understates the
half-width by about 15%. The change also makes the two sets of statistics
(`summary.csv` marginal CIs and the CRN paired comparison) agree.

## Considered options

- **Keep z = 1.96 everywhere.** The smallest possible change, with no downstream
  churn. But it keeps an anticonservative method the rest of the codebase had
  already dropped, and the two sets of statistics stay inconsistent.
- **Use t only for the new `bullwhip.*` rows and leave marginal rows on z.** This
  respects a strict issue-06 scope, but puts two CI conventions in one CSV, which
  would surprise a reader and cannot be justified.
- **Use t uniformly (chosen).** One correct, consistent convention. The cost is that
  previously reported marginal CI *values* change. Accepted because nothing
  downstream cited them yet, and `summary.csv` is outside the golden byte-identical
  check (`compare_baselines.py` compares only the `run_*.json` `kpis` dicts), so the
  golden test is not at risk.

## Consequences

- Single-replication runs keep the existing `n <= 1` guard (stdev 0, so the CI
  collapses to the mean), because `t.ppf` is undefined at df 0.
- The marginal-CI method change matters for provenance. Record it in
  `.scratch/paper-draft-audit/DATASET-README.md` when the dataset is regenerated.
