# Inter-region transfers are priced

Date: 2026-11-18
Status: accepted

## Context

A treatment operator's cross-region request moves waste from a remote collection center to a
local one through `PointToPointTransport` (ADR 0009). The move takes travel time and a vehicle, but
`_handle_completed_transport` only added the volume to the destination center. It charged no
transport cost and recorded no emissions, so every cross-region move was free in the KPIs.

## Decision

A completed transfer is charged like a collection trip, through the shared
`CollectorCompany._record_trip_cost_and_emissions`:

- Cost is the trip's fixed `transport_cost` plus distance × `COLLECTION_COST_PER_KM_PER_M3` × volume.
- Emissions are tonnes × distance × `TRANSPORT_EMISSIONS_PER_TON_KM`.
- Distance is the great-circle `get_distance(origin, destination)`, the same basis collection uses.
  Like collection, only the loaded leg is charged.
- The collector that owns the vehicle pays.

Collection trips call the same helper, unchanged.

## Consequences

Seeds 1-10, Baseline, after minus before (paired, 95% CI). Service, collection rate and
uncollected volume are unchanged in every combo; only cost and emissions move.

| Combo | Collection transport cost, model currency | Emissions, kg CO2e |
|---|---|---|
| PUSH ON_DEMAND | +724,385 | +24,758 |
| PUSH REORDER_50 | +350,053 | +39,681 |
| PUSH REORDER_90 | +451,680 | +38,936 |
| PULL ON_DEMAND | +526,853 | +33,165 |
| PULL REORDER_50 | +268,189 | +31,813 |
| PULL REORDER_90 | +314,370 | +32,273 |

Most cross-region intake still bypasses this path through the treatment fallback drain, which is
fixed in ADR 0035.
