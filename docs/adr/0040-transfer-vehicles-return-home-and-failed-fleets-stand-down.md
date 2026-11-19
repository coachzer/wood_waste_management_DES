# Transfer vehicles return home, and a FAILED collector's fleet takes no transfers

Date: 2026-11-19
Status: accepted

## Context

After an inter-region transfer, `_check_completed_transports` left the vehicle in the region it
delivered to. Nothing brought it home. `PointToPointTransport.find_available_vehicle` takes an
idle vehicle in the origin region first, otherwise the nearest one, from any collector's fleet, and
it did not check the owner's status. So vehicles drifted across regions, an idle vehicle in the
origin region was usually another collector's (5-9% of transfers used the origin's own vehicle),
and FAILED collectors' vehicles carried about 9% of transfers while their owner was down. A
teleport-home sensitivity on seeds 1-10 moved PULL-PUSH ON_DEMAND total cost from +59k to -7k
(`.scratch/docs-open-items/issues/07`).

## Decision

- When a transfer delivers, its vehicle drives home empty. The return leg takes road travel time
  (`PointToPointTransport.travel_time_days`, the same circuity as the loaded leg), and the vehicle
  stays `in_transit` until it is home. The leg has no per-km charge: the fixed trip cost covers it,
  as the pickup leg's empty running is already unpriced.
- `find_available_vehicle` skips every vehicle whose collector is FAILED. A transfer under way when
  its collector fails still delivers, and the vehicle returns home and waits. RECOVERING collectors
  dispatch as usual. Local collection already stopped on FAILED.
- `_handle_completed_transport` finds the receiving collector by `transport["destination"]`, not by
  the vehicle's region. Delivery and return can complete in one check, and the vehicle is home by then.

## Consequences

Seeds 1-10, Baseline, paired against d382a9f (`.scratch/vehicle-return/`, chart in
`evaluation.html`). Every transfer now starts at the owner's home, no FAILED collector's vehicle
is dispatched, and no vehicle sits idle away from home. The origin collector's own vehicle now takes
11-59% of transfers.

The return leg never holds a vehicle past the next transport check. Transfers start on the 1-day
`manage_transport` tick, and pickup, haul and return together take at most about 0.75 days (0 of
292,447 transfers held over). The vehicle is unavailable until home in the model, but at this tick
that costs no availability. What moves results is which vehicle takes a transfer.

PULL minus PUSH total cost, thousand (95% paired-t):

| Strategy | Before | Return home only | After |
|---|---|---|---|
| ON_DEMAND | +59 [+36, +83] | -33 [-74, +8] | -176 [-224, -129] |
| REORDER_50 | +53 [+12, +95] | +75 [+13, +136] | +37 [-24, +99] |
| REORDER_90 | +96 [+66, +126] | +71 [+50, +91] | +76 [+39, +112] |

Emissions, t: ON_DEMAND +14 -> -60 [-73, -46]; REORDER_50 +24 -> +22; REORDER_90 +23 -> +14.
Service level and uncollected volume do not move.

The ON_DEMAND flip is PUSH ON_DEMAND getting dearer (+171k [+137, +205]; +35k from the return
home, the rest from standing FAILED fleets down). PUSH ON_DEMAND makes about 10,800 transfers a year
of about 2 m3 each, each holding a vehicle for a whole tick, so about 30 of the 36 vehicles are on
transfers and transfers queue about 23 days. Losing the FAILED fleets' share of that supply crowds
out local collection. On seeds 1-5 it makes fewer, longer local trips (1,771 -> 1,305 a year, same
volume) and drains more through the fallback (40,158 -> 45,792 m3). The ON_DEMAND comparison
therefore rests on that vehicle saturation, not on the policies, and is not a PULL-PUSH finding
until the tiny-transfer saturation is resolved
(`.scratch/docs-open-items/issues/08`). REORDER_90 stays PULL-dearer, and REORDER_50 loses
significance.
