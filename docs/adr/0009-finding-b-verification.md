# Finding B verification (issue 09) — CONFIRMED

Date 2026-06-03, seed 123456, Baseline. Throwaway record (gitignored). Verdict: **Finding B holds
robustly**; the bullwhip metric's treatment echelon measures collector<->collector repositioning, not
treatment replenishment.

## 1. Static audit — all `track_transport_flow` call sites (exhaustive)

Only TWO call sites exist (grep `track_transport_flow` in core/):

| site | pair logged | what it actually is |
| --- | --- | --- |
| `core/collector.py:257` | `generator -> collector` | real collection pickup (legit) |
| `core/transport_manager.py:112` (`_create_transport`) | `collector -> treatment` | **cross-region collector->collector repositioning, mislabeled** |

Mechanism proving the mislabel, purely from source:
- The `collector->treatment` flow is logged by `_create_transport`, fed only by
  `collector.transfer_waste_to_region` (collector.py:483), called only from
  `treatment._request_via_transport` (treatment.py:643) for the CROSS-region portion.
- `transfer_waste_to_region` removes volume from the *remote* collector (collector.py:506).
- On arrival, `_handle_completed_transport` (collector.py:619-627) **re-deposits the volume into a
  collector in the destination region** — never into a TreatmentOperator.
- Treatment's REAL intake is `collector.provide_waste_for_treatment` (treatment.py:594 local,
  :627 fallback), which decrements collector storage directly and **never calls `track_transport_flow`**.

So the logged treatment-inbound series is a prepositioning move between collectors; the real intake is
invisible to `transport_flows`.

## 2. Runtime ledger sweep (transport_ledger_sweep_probe.py) — PUSH + PULL

| combo | c2t_flow (logged) | transfer_out | redeposited | dropped | net_out | provide REAL | ratio |
| --- | --- | --- | --- | --- | --- | --- | --- |
| push__on_demand | 45093.1 | 45093.1 | 45093.1 | 0.0 | 0.0 | 411459.3 | 9.1x |
| pull__on_demand | 55098.2 | 55098.2 | 55098.2 | 0.0 | 0.0 | 382765.6 | 6.9x |
| pull__reorder_50 | 41278.3 | 41278.3 | 41278.3 | 0.0 | 0.0 | 338762.7 | 8.2x |
| pull__reorder_90 | 70889.4 | 70889.4 | 70889.4 | 0.0 | 0.0 | 369449.0 | 5.2x |
| push__reorder_90 | 67874.8 | 67874.8 | 67874.8 | 0.0 | 0.0 | 377343.1 | 5.6x |

Across EVERY combo: `c2t_flow == transfer_out == redeposited`, `dropped == 0`, **`net_out == 0`** ->
the logged treatment-inbound is purely net-zero repositioning. Real intake is 5.2x-9.1x larger and
entirely unlogged. (Earlier handoff only ran push__on_demand; PULL was the open gap — now closed.)

Note: transport `dropped == 0` everywhere, so Finding A (the ~132K expand-drop leak) is a SEPARATE
defect in `utils/capacity_utils.py::handle_storage_event` (storage-expand branch), not a transport leak.

## 3. Impact map onto published metrics (monitoring/bullwhip.py)

Corrupted = depends on the `collector->treatment` repositioning series.

| metric | uses collector->treatment? | status |
| --- | --- | --- |
| `treatment_anchored_bullwhip` | yes (numerator) | **CORRUPTED** |
| `treatment_stage` (stage_bullwhip) | yes (numerator) | **CORRUPTED** |
| `collector_stage` (stage_bullwhip) | yes (DENOMINATOR) | **CORRUPTED** — source of spurious `cstage<1` |
| `treatment_anchored_pooled_bullwhip` | yes | **CORRUPTED** |
| `collector_anchored_bullwhip` | no (gen->coll / consumption) | clean |
| `collector_anchored_pooled_bullwhip` | no (gen->coll / consumption) | clean |

Telescoping caveat: `treatment_stage * collector_stage` cancels the repositioning term and equals the
(clean) collector pooled anchored ratio — so the PRODUCT survives but each FACTOR is meaningless. The
"which echelon injects amplification" decomposition (ADRs 0004/0006/0007) is invalid as published.

## Conclusion

The treatment-echelon headline and the entire stage decomposition are built on the wrong flow. The
collector-echelon anchored metrics (generator->collector vs consumption) are unaffected. This contradicts
ADR 0004's premise that `transport_flows` captures the delivered echelon flow. Remediation requires
logging `provide_waste_for_treatment` as the real `collector->treatment` flow (and deciding how to treat
the existing repositioning move) before re-running the bullwhip track. Finding A bundled per user.
