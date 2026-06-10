# Densities unified per waste type for transport emissions and landfill cost

Date: 2026-06-08 (decided), 2026-06-10 (accepted)
Status: accepted

> Implemented in `67bb9e3`. Drafted while the frozen-oracle regime was still in force; the
> draft's re-freeze procedure was overtaken by the freeze teardown (2026-06-09) and is
> recorded below only as history. Numbering note: 0012 was the oracle-reproduction ADR,
> removed with the freeze teardown.

## Context

The codebase carried two unconnected density models. `utils/unit_conversion.py::WASTE_DENSITIES` holds 14
per-`WasteType` bulk densities (200-600 kg/m3) used to convert generation rates tonnes->m3 at sim init.
`config/constants.py::DENSITY = 0.6` was a single flat 600 kg/m3 used to derive
`TRANSPORT_EMISSIONS_PER_M3_KM` and `landfill_per_m3` (`LANDFILL_COST_PER_TONNE * DENSITY`). So transport
emissions and landfill cost were computed at a flat 600 kg/m3 regardless of the actual stream density — up
to ~3x too high for low-density waste (sawdust 200 kg/m3) and wrong for every non-600 stream. The
volume-weighted effective density across all 12 regions is ~462 kg/m3, not 600 (ticket
`.scratch/utils-cleanup/issues/07-unify-density-model.md`).

A coupled currency-restatement-and-cost-sourcing effort (ticket
`.scratch/currency-consistency/issue-01-usd-model-eur-sources.md`) was investigated alongside this — the two
debts share the `landfill_per_m3 = LANDFILL_COST_PER_TONNE_USD * DENSITY` line. A two-round literature search
(web deep-research + Scopus, 2026-06-08) found that only two of the four cost-KPI drivers are cleanly
citable (industrial energy price; landfill gate fee/tax); processing opex, transport, and storage capex have
no clean single source. **Decision (2026-06-08): the currency/cost-sourcing work is deferred as future work**
— it is recorded with its findings and citations in the currency-consistency ticket, not implemented here.
This ADR covers only the density unification, which has a clear physical basis (the per-type densities
already exist in code).

## Decision

1. **Densities unified per waste type for transport emissions and landfill cost.** The flat `DENSITY = 0.6`
   is retired from the two cost/emission paths and replaced by the per-type `WASTE_DENSITIES` already used at
   sim init:
   - Transport emissions (`core/collector.py`): the flat `collected_amount * distance *
     TRANSPORT_EMISSIONS_PER_M3_KM` becomes a per-type sum over the in-scope `collected_waste`
     (`dict[WasteType, float]`): `sum(vol_m3 * (WASTE_DENSITIES[wt]/1000) * distance *
     TRANSPORT_EMISSIONS_PER_TON_KM ...)` over the items sorted by `WasteType.value`.
     `TRANSPORT_EMISSIONS_PER_TON_KM` (0.087) already existed in `constants.py`.
   - Landfill cost (`utils/capacity_utils.py`): `handle_storage_event` takes a `dict[WasteType, float]`
     instead of a scalar `volume` (`split_overflow_by_type` splits overflow proportionally); its callers in
     `core/generator.py`, `core/collector.py`, and `core/treatment.py` pass the per-type overflow breakdown.
     Cost becomes `sum(vol_m3 * (WASTE_DENSITIES[wt]/1000) * LANDFILL_COST_PER_TONNE for ...)` over the
     sorted items.
   - Every new iteration over a per-type dict is `sorted(..., key=lambda kv: kv[0].value)` per the
     determinism rule (CLAUDE.md; `tests/test_enum_set_ordering.py`).

2. **`DENSITY = 0.6` and `TRANSPORT_EMISSIONS_PER_M3_KM` removed.** After the two paths above, no legitimate
   use of the flat density remained; `TRANSPORT_EMISSIONS_PER_M3_KM` (which baked in the flat density) is
   removed in favour of the per-type computation built from `TRANSPORT_EMISSIONS_PER_TON_KM`, and
   `CostParams.landfill_per_m3` is removed. The `WASTE_DENSITIES` table moves to its no-magic-numbers home in
   `config/constants.py` (`unit_conversion.py` re-imports it); that part is behaviour-neutral.

3. **Currency restatement and cost-parameter sourcing are deferred.** The cost layer stays USD-labelled;
   `operational_costs`, `energy_consumption`, `transport_cost`, `volume_cost_factor`, and
   `expansion_cost_per_m3` keep their current values. The investigation's findings and citations are
   preserved in the currency-consistency ticket as future work — see that ticket for the energy-price and
   landfill-gate-fee sources that are adoptable when the work is scheduled.

## Consequences

This is a **behaviour change** on the emissions and cost KPIs. Measured deltas (verified MISMATCH against
the then-current baseline by design; KPI movements decomposed across two comparison runs, consistent in
both):

- `storage_overflow_cost`: **down ~35%**
- `total_system_cost`: **down ~6%**
- `landfill_volume_m3`: **up ~0.5%**
- `total_emissions_kgco2e`: **up ~0.2%**

The pre-run estimate in the draft of this ADR predicted total emissions would fall ~23% (transport emissions
and landfill cost each scaling down with the 462-vs-600 kg/m3 effective density). That estimate was wrong in
direction for total emissions because it modelled the change as a pure rescaling and missed a second-order
behavioural channel: `total_emissions_kgco2e` sums transport and landfill emissions, and while per-type
density does lower transport emissions (~-69k and ~-178k kgCO2e on the two comparison runs), lowering the
per-type landfill *cost* shifts the cost-minimizing expand-vs-landfill decision in `handle_storage_event`
toward landfilling. Landfill volume rises, and landfill emissions — 240 kgCO2e/m3, volumetric, unchanged by
density — rise more than transport emissions fall (~+101k and ~+183k kgCO2e on the same runs). Net: total
emissions edge up. The same channel explains why `landfill_volume_m3`, a pure volume the draft predicted
unchanged, rises ~0.5%.

The draft also prescribed a re-freeze to a `baseline-4` oracle under the then-active frozen-oracle regime.
That regime was abandoned on 2026-06-09 (freeze infrastructure removed); no baseline-4 was cut and none is
needed. The operative consequence for the paper stands: every published emissions/cost figure that predates
this change measured the flat-density system and must be regenerated from current code before being
consumed, and the limitations section gains a one-line note that the cost layer remains nominally USD
pending the deferred EUR restatement.

The cross-process determinism guard stays green: every new per-type iteration is sorted by
`WasteType.value` and no unordered set-of-enum iteration is introduced.
