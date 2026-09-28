# Avoided emissions are a recycling avoided-burden, reported beside operational emissions, never netted

Date: 2026-06-04
Status: accepted

> NOTE (2026-09-28): the `monitoring/` package no longer exists. `_GENERIC_NAMESPACES` is now a single
> tuple in `analysis/_kpi_shared.py`. Both `analysis/baseline_aggregate.py` and
> `analysis/paired_comparison.py` import it, so the "two tuples must match" rule below no longer
> applies. The golden `--mode additive` gate it mentions was
> removed when the freeze regime was abandoned (2026-06-09). The decision is unchanged.

## Context

C11 (P4 circular-economy depth) adds an avoided-emissions KPI. It counts the GHG emissions the
system avoids because every MDF / particle board / OSB unit it produces is made from recovered wood
waste, and so replaces a panel that would otherwise have been made from virgin feedstock. The
driver, recycled produced volume per output type, is fully in scope and varies by scenario
(`treatment.product_volumes`, the same source C10 and the yield bridge use). The question was never
*whether* to build it but *what claim it makes*. The literature exported to `references.bib`
(2026-06-04) covers two incompatible concepts, which the C11 ticket had merged without comment
("virgin wood, fossil plastic, concrete"):

- **Material-substitution displacement** (Sathre & O'Connor 2010, avg 2.1 tC/tC; Smyth et al.
  2017, panels 0.45 tC/tC). The claim is that a wood panel displaces a *non-wood* functional
  equivalent (concrete, steel, fossil plastic), measured per unit of carbon in the wood product.
  This gives the large number that looks good in a headline.
- **Recycling avoided-burden** (Kim & Song 2014; per-product cradle-to-gate footprints in Lao &
  Chang 2023, Garcia & Freire 2014, Benetto et al. 2009). The claim is that a recycled panel
  displaces a *functionally identical* panel made from virgin wood, meaning secondary vs primary
  production of the same good.

## Decision

1. **Recycling avoided-burden, not material substitution.** Avoided Emissions is the footprint of
   the displaced virgin-feedstock production of the *same* product. The model does not represent
   the buyer choosing wood over concrete, steel or plastic, since Market Consumption only takes wood
   product. The material-substitution displacement factor (Sathre/Smyth) would therefore assert a
   counterfactual the simulation has no evidence for, and it is rejected as the headline despite the
   larger number. The recycling burden is what the waste-to-product model's structure actually
   represents. The glossary term "Avoided Emissions" is added to `CONTEXT.md`.

2. **Three independent carbon lines, with no net across boundaries.** Avoided emissions
   (displacement benefit), the C10 static biogenic-carbon stored credit (storage credit), and
   `total_emissions_kgco2e` (in-simulation operational cost: transport + landfill + processing
   energy) are reported side by side, each with its boundary stated. The earlier "net carbon =
   stored + avoided - process emissions" framing is **dropped**. The avoided figure is a full
   cradle-to-gate LCA of the displaced virgin panel (including resin, adhesive and upstream energy),
   while `total_emissions_kgco2e` is only the narrower in-simulation slice, so subtracting one from
   the other would overstate the benefit without showing it. They are not commensurable, so they are
   not subtracted.

3. **Lao 2023 biogenic-excluded per-m3 factors as the headline, European papers as sensitivity.**
   The per-product factors come from one consistent source, the Lao & Chang (2023) cradle-to-gate
   footprints *without biogenic carbon storage*: FB 406 -> MDF, PB 348 -> particle board, OSB 552
   (kg CO2eq/m3). One method, one boundary and one biogenic treatment keep the per-product
   *differences* coherent. Those differences are the avoided line's only independent signal, since
   its level is a linear rescale of production. The biogenic exclusion is **binding, not a matter of
   style**. C10 reports stored biogenic carbon as its own line, so a biogenic-inclusive footprint
   (e.g., Garcia's headline -939 kg CO2eq/m3) would count the stored carbon twice. European
   product-specific papers (Garcia 2014 PB, Benetto 2009 OSB, Piekarski 2017 / Kouchaki-Penchah 2016
   MDF) give the stated sensitivity range and are not blended into the headline. The factors live in
   `config/constants.py`, following project convention.

## Consequences

This is purely additive analysis with no change to simulation behaviour. Avoided emissions is a
post-hoc rescale of `product_volumes` by fixed coefficients, emitted as positive-magnitude
`avoided_emissions_{mdf,particle_board,osb,total}_kgco2e` under a generic `carbon` namespace in
`extract_kpis`, shared with C10. The golden `--mode additive` gate stays green against baseline-3
(run JSONs persist only `kpis`, and the driver lives in in-process `monitor_data`). `carbon` must be
added to `_GENERIC_NAMESPACES` in **both** `monitoring/baseline_aggregate.py` and
`monitoring/paired_comparison.py`. The two tuples must match, since paired_comparison imports no
project code.

The factor is a fixed coefficient applied identically across all six PUSH/PULL x strategy
configurations, so the absolute avoided-emissions level carries no cross-config signal beyond
production volume. The comparison the paper draws does not change between the Lao and European
factors, which is why internal consistency was preferred over geographic precision. The MDF<-FB map
is a category match (MDF is the dominant member of the fibreboard class Lao reports as FB). The PB
and OSB maps are exact.
