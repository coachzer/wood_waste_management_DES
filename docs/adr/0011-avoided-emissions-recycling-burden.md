# Avoided emissions are a recycling avoided-burden, reported beside operational emissions, never netted

Date: 2026-06-04
Status: accepted

## Context

C11 (P4 circular-economy depth) adds an avoided-emissions KPI: the GHG emissions the system
avoids because every MDF / particle board / OSB unit it produces is made from recovered wood
waste and therefore stands in for a panel that would otherwise have been manufactured from
virgin feedstock. The driver — recycled produced volume per output type — is fully in scope and
scenario-varying (`treatment.product_volumes`, the same source C10 and the yield bridge use). The
open question was never *whether* to build it but *what claim it encodes*, and the literature
exported to `references.bib` (2026-06-04) spans two incompatible concepts the C11 ticket had
quietly merged ("virgin wood, fossil plastic, concrete"):

- **Material-substitution displacement** (Sathre & O'Connor 2010, avg 2.1 tC/tC; Smyth et al.
  2017, panels 0.45 tC/tC) — the claim that a wood panel displaces a *non-wood* functional
  equivalent (concrete, steel, fossil plastic), measured per unit carbon in the wood product. The
  large, headline-friendly number.
- **Recycling avoided-burden** (Kim & Song 2014; per-product cradle-to-gate footprints in Lao &
  Chang 2023, Garcia & Freire 2014, Benetto et al. 2009) — the claim that a recycled panel
  displaces a *functionally identical* panel made from virgin wood. Secondary-vs-primary
  production of the same good.

## Decision

1. **Recycling avoided-burden, not material substitution.** Avoided Emissions is the displaced
   virgin-feedstock production footprint of the *same* product. The model does not represent the
   buyer choosing wood over concrete/steel/plastic — Market Consumption simply takes wood product —
   so the material-substitution displacement factor (Sathre/Smyth) asserts a counterfactual the
   simulation has no evidence for, and is rejected as the headline despite the larger number. The
   recycling burden is what the waste-to-product model structurally embodies. Glossary term added
   to `CONTEXT.md` ("Avoided Emissions").

2. **Three independent carbon lines, no boundary-mixing net.** Avoided emissions (displacement
   benefit), the C10 static biogenic-carbon stored credit (storage credit), and
   `total_emissions_kgco2e` (in-sim operational cost: transport + landfill + processing energy) are
   reported side by side with their boundaries stated. The earlier "net carbon = stored + avoided -
   process emissions" framing is **dropped**: the avoided figure is a full cradle-to-gate LCA of the
   displaced virgin panel (includes resin/adhesive and upstream energy), whereas
   `total_emissions_kgco2e` is only the narrower in-simulation slice, so subtracting them would
   silently overstate the benefit. They are not commensurable, so they are not subtracted.

3. **Lao 2023 biogenic-excluded per-m3 factors as headline; European papers as sensitivity.** The
   per-product factors come from one consistent source — Lao & Chang (2023) cradle-to-gate footprints
   *without biogenic carbon storage*: FB 406 -> MDF, PB 348 -> particle board, OSB 552 (kg CO2eq/m3).
   One method, one boundary, one biogenic treatment, so the per-product *differences* (the avoided
   line's only independent signal, since the level is a linear rescale of production) are coherent.
   The biogenic exclusion is **binding, not stylistic**: C10 ships the stored biogenic carbon as its
   own line, so a biogenic-inclusive footprint (e.g. Garcia's headline -939 kg CO2eq/m3) would count
   the stored carbon twice. European product-specific papers (Garcia 2014 PB, Benetto 2009 OSB,
   Piekarski 2017 / Kouchaki-Penchah 2016 MDF) are the stated sensitivity range, not blended into the
   headline. Factors live in `config/constants.py` per project convention.

## Consequences

Purely additive analysis — no simulation behaviour change. Avoided emissions is a post-hoc rescale
of `product_volumes` by fixed coefficients, emitted as positive-magnitude
`avoided_emissions_{mdf,particle_board,osb,total}_kgco2e` under a generic `carbon` namespace in
`extract_kpis`, shared with C10. The golden `--mode additive` gate stays green vs baseline-3 (run
JSONs persist only `kpis`; the driver lives in in-process `monitor_data`). `carbon` must be added to
`_GENERIC_NAMESPACES` in **both** `monitoring/baseline_aggregate.py` and
`monitoring/paired_comparison.py` (the tuples must mirror; paired_comparison imports no project code).

Because the factor is a fixed coefficient applied identically across all six PUSH/PULL x strategy
configurations, the absolute avoided-emissions level carries no cross-config signal beyond production
volume; the comparative contrast the paper draws is invariant to the Lao-vs-European choice, which is
why internal consistency was preferred over geographic precision. The MDF<-FB map is a category match
(MDF is the dominant member of the fibreboard class Lao reports as FB); PB and OSB maps are exact.
