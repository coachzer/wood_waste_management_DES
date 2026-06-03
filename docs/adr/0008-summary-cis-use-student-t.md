# Summary.csv confidence intervals use Student-t uniformly

When wiring the Monte Carlo `bullwhip` KPIs into per-combo `summary.csv` (issue 06),
we switched every CI in that file -- marginal KPIs and the new `bullwhip.*` rows
alike -- from the prior `z = 1.96` normal approximation to a Student-t interval
`t(0.975, n-1) * stdev / sqrt(n)`, computed via the `scipy.stats.t.ppf` path that
`monitoring/paired_comparison.py` already uses. With unknown population variance
estimated from the replications, the t-interval is the correct small-n interval;
at the default `--replications 10` the z approximation understates the half-width
by ~15%. This also makes the two statistics surfaces (`summary.csv` marginal CIs
and the CRN paired comparison) consistent rather than contradictory.

## Considered Options

- **Keep z = 1.96 everywhere.** Fully surgical and zero downstream churn, but keeps
  an anticonservative method the rest of the codebase had already moved past, and
  leaves the two stats surfaces inconsistent.
- **Use t only for the new `bullwhip.*` rows, leave marginal rows on z.** Honors a
  strict issue-06 scope but creates two CI conventions in one CSV -- surprising and
  indefensible to a reader.
- **Use t uniformly (chosen).** One correct, consistent convention. Cost: previously
  reported marginal CI *values* change. Accepted because nothing downstream cited
  them yet, and `summary.csv` is not part of the golden byte-identical surface
  (`compare_baselines.py` compares only `run_*.json` `kpis` dicts), so there is no
  golden-test risk.

## Consequences

- Single-replication runs keep the existing `n <= 1` guard (stdev 0, CI collapses to
  the mean): `t.ppf` at df 0 is undefined.
- The marginal-CI method change is provenance-relevant -- record it in
  `.scratch/paper-draft-audit/DATASET-README.md` when the dataset is regenerated.
