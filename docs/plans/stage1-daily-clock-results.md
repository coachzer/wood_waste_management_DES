# Stage 1 results — daily operating clock (ADR 0020)

Date: 2026-09-28. Baseline scenario, 100 CRN replications per combo (seeds 123456..123555),
marginal 95% t-CIs per combo (not paired-t).

- Reference: c12839b "Fix double-applied collector efficiency" -> `outputs/stage1/ref_n100`
  (547 s wall, 16 workers; smoke `outputs/stage1/ref_smoke`, 29 s).
- Daily clock: ffe7f0c "Move treatment and collectors onto a daily clock" (includes 87efddd
  mass-balance fix, accounting only) -> `outputs/stage1/new_n100` (313 s wall, 16 workers;
  smoke `outputs/stage1/new_smoke`, 42 s).
- Wall times are noise-dominated on this machine: a back-to-back re-time of both smoke runs
  gave 102 s (reference) vs 85 s (daily clock). No evidence the daily clock is slower.
- Script: `.scratch/compare_stage1.py` (per-m3 transport cost = collection_transport_cost /
  total_collected_m3; per-m3 transport emissions = sum of every entity's
  `transport_emissions` / total_collected_m3).

## Headline

- **Ranking unchanged, 0 flips.** push/reorder_50 > push/reorder_90 > pull/reorder_50 >
  pull/reorder_90 > push/on_demand > pull/on_demand, in both.
- **Every KPI moved far outside its CI.** The daily clock is not a neutral re-plumbing:
  - full service level rises 65-72% -> 93-99% (PUSH) and 48-66% -> 83-96% (PULL);
  - landfill falls to 0 for all PUSH combos and by 78-91% for PULL;
  - total emissions fall 72-98% (landfill emissions dominate the old totals);
  - total system cost rises for 5 of 6 combos (+3% to +32%): processing cost rises with
    ~40-75% more processed volume, outweighing the vanished overflow/landfill/expansion costs;
  - both anchored bullwhip ratios fall 34-89%.
- **Service level stays identical in its full and operational forms** (no_capability = 0 in
  Baseline), in both runs.

## Why the effect is this large (mechanism, checked)

Annual processing capacity is not what binds: nominal system intake capacity is ~4.6M m3/yr
(sum of storage x 0.8 x 365 / 24 over all processors) against ~80-120k m3 processed. What
bound the old model was cadence. Output per tick is clamped by finished-goods headroom (at most
4 weeks of the operator's demand), and a treatment tick every 24 days against weekly
consumption left operators empty between ticks. Daily ticks refill continuously. On the
collector side, dropping the uniform(1, 4) jitter raises effective PUSH collection capacity
from 12/14.5 = 83% to 100% of nominal (ADR 0020 c, about +20%), and daily collection
keeps generator storage from overflowing, which removes landfill.

PULL gains more than PUSH (e.g. on_demand +73% vs +43%) partly because of the production
backlog (ADR 0020 a). The old PULL loop forgot any target it missed, while the backlog keeps
it. This confound is not separated (no no-carry control run).

## Transport per m3 (coupling e)

Per-m3 transport cost fell 2-11% and per-m3 transport emissions fell 7.5-17%. Emissions carry
no fixed charge, so the average haul got shorter per m3 (a distance/density mix effect,
mechanism not traced). The fixed per-trip charge did rise as expected. Probe at seed 123456
(`.scratch/trip_cost_probe.py`, sums `transport_cost` over dispatched collection trips):

| combo | trips ref | trips new | fixed $/m3 ref | fixed $/m3 new | total $/m3 ref | total $/m3 new |
|---|---|---|---|---|---|---|
| push__on_demand | 81 | 831 | 0.003 | 0.042 | 2.190 | 2.055 |
| push__reorder_50 | 119 | 1327 | 0.007 | 0.071 | 2.265 | 1.947 |
| push__reorder_90 | 160 | 1772 | 0.008 | 0.087 | 2.239 | 1.896 |
| pull__on_demand | 306 | 6295 | 0.019 | 0.304 | 2.305 | 2.085 |
| pull__reorder_50 | 221 | 3987 | 0.013 | 0.173 | 2.146 | 1.984 |
| pull__reorder_90 | 247 | 2768 | 0.010 | 0.100 | 2.292 | 1.933 |

So the fixed charge adds +$0.04-0.29/m3 (2-14% of the ~$2/m3 total), more for PULL, but a
larger per-m3 distance saving more than offsets it. Single seed only.

## Full tables

### service_level_full_pct

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 65.23 [64.77, 65.70] | 93.18 [92.91, 93.45] | +42.8% | no |
| push__reorder_50 | 72.47 [72.00, 72.94] | 98.93 [98.84, 99.01] | +36.5% | no |
| push__reorder_90 | 71.61 [71.16, 72.06] | 98.38 [98.23, 98.52] | +37.4% | no |
| pull__on_demand | 48.13 [47.11, 49.15] | 83.31 [82.77, 83.85] | +73.1% | no |
| pull__reorder_50 | 65.58 [64.94, 66.22] | 95.82 [95.43, 96.21] | +46.1% | no |
| pull__reorder_90 | 65.47 [64.83, 66.11] | 93.77 [93.25, 94.30] | +43.2% | no |

### service_level_operational_pct

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 65.23 [64.77, 65.70] | 93.18 [92.91, 93.45] | +42.8% | no |
| push__reorder_50 | 72.47 [72.00, 72.94] | 98.93 [98.84, 99.01] | +36.5% | no |
| push__reorder_90 | 71.61 [71.16, 72.06] | 98.38 [98.23, 98.52] | +37.4% | no |
| pull__on_demand | 48.13 [47.11, 49.15] | 83.31 [82.77, 83.85] | +73.1% | no |
| pull__reorder_50 | 65.58 [64.94, 66.22] | 95.82 [95.43, 96.21] | +46.1% | no |
| pull__reorder_90 | 65.47 [64.83, 66.11] | 93.77 [93.25, 94.30] | +43.2% | no |

### landfill_volume_m3

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 144,607 [136,862, 152,351] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_50 | 46,605 [40,468, 52,742] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_90 | 116,824 [111,246, 122,402] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| pull__on_demand | 42,771 [38,336, 47,206] | 5,409 [4,874, 5,943] | -87.4% | no |
| pull__reorder_50 | 59,227 [53,885, 64,570] | 13,209 [12,239, 14,179] | -77.7% | no |
| pull__reorder_90 | 185,624 [176,332, 194,916] | 17,216 [16,475, 17,958] | -90.7% | no |

### total_system_cost

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 18,662,341 [18,458,091, 18,866,591] | 19,198,446 [19,146,189, 19,250,704] | +2.9% | no |
| push__reorder_50 | 17,324,583 [17,147,709, 17,501,457] | 20,301,790 [20,279,039, 20,324,540] | +17.2% | no |
| push__reorder_90 | 19,902,863 [19,735,992, 20,069,734] | 20,976,667 [20,945,516, 21,007,819] | +5.4% | no |
| pull__on_demand | 12,974,768 [12,639,723, 13,309,812] | 17,178,202 [17,061,769, 17,294,635] | +32.4% | no |
| pull__reorder_50 | 17,143,647 [16,854,957, 17,432,337] | 21,021,543 [20,921,230, 21,121,855] | +22.6% | no |
| pull__reorder_90 | 21,650,140 [21,300,401, 21,999,878] | 21,492,593 [21,375,349, 21,609,836] | -0.7% | yes |

### collection_transport_cost

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 2,888,715 [2,856,946, 2,920,484] | 2,068,973 [2,064,081, 2,073,864] | -28.4% | no |
| push__reorder_50 | 2,443,186 [2,415,212, 2,471,161] | 1,951,491 [1,943,074, 1,959,909] | -20.1% | no |
| push__reorder_90 | 3,106,625 [3,084,264, 3,128,986] | 2,480,172 [2,473,134, 2,487,209] | -20.2% | no |
| pull__on_demand | 1,996,715 [1,926,727, 2,066,704] | 2,042,541 [2,029,149, 2,055,932] | +2.3% | yes |
| pull__reorder_50 | 2,325,907 [2,273,557, 2,378,257] | 2,409,948 [2,395,847, 2,424,048] | +3.6% | no |
| pull__reorder_90 | 3,165,060 [3,119,021, 3,211,098] | 2,862,176 [2,848,269, 2,876,083] | -9.6% | no |

### processing_cost

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 9,953,337 [9,869,370, 10,037,305] | 14,799,822 [14,748,133, 14,851,510] | +48.7% | no |
| push__reorder_50 | 11,252,933 [11,168,105, 11,337,761] | 15,922,861 [15,902,939, 15,942,784] | +41.5% | no |
| push__reorder_90 | 11,088,270 [11,005,633, 11,170,906] | 15,848,669 [15,819,201, 15,878,138] | +42.9% | no |
| pull__on_demand | 7,231,331 [7,044,016, 7,418,646] | 12,625,045 [12,524,724, 12,725,365] | +74.6% | no |
| pull__reorder_50 | 10,453,649 [10,329,465, 10,577,833] | 15,480,422 [15,403,461, 15,557,383] | +48.1% | no |
| pull__reorder_90 | 10,491,445 [10,369,946, 10,612,944] | 15,258,023 [15,169,885, 15,346,161] | +45.4% | no |

### storage_overflow_cost

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 3,318,803 [3,132,634, 3,504,972] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_50 | 1,052,850 [923,203, 1,182,498] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_90 | 2,984,324 [2,834,063, 3,134,585] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| pull__on_demand | 1,564,465 [1,377,118, 1,751,812] | 255,066 [220,378, 289,753] | -83.7% | no |
| pull__reorder_50 | 1,932,207 [1,752,369, 2,112,045] | 573,653 [513,708, 633,598] | -70.3% | no |
| pull__reorder_90 | 5,337,171 [5,052,936, 5,621,406] | 617,465 [576,369, 658,561] | -88.4% | no |

### landfill_cost

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 2,905,053 [2,733,666, 3,076,440] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_50 | 920,100 [799,202, 1,040,998] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_90 | 2,458,824 [2,324,796, 2,592,851] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| pull__on_demand | 1,218,465 [1,076,306, 1,360,624] | 220,566 [191,392, 249,739] | -81.9% | no |
| pull__reorder_50 | 1,559,207 [1,409,601, 1,708,813] | 426,903 [386,203, 467,603] | -72.6% | no |
| pull__reorder_90 | 4,503,421 [4,259,461, 4,747,381] | 505,215 [475,797, 534,632] | -88.8% | no |

### expansion_cost

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 413,750 [395,091, 432,409] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_50 | 132,750 [120,302, 145,198] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| push__reorder_90 | 525,500 [501,414, 549,586] | 0.0000 [0.0000, 0.0000] | -100.0% | no |
| pull__on_demand | 346,000 [296,698, 395,302] | 34,500 [25,395, 43,605] | -90.0% | no |
| pull__reorder_50 | 373,000 [338,838, 407,162] | 146,750 [125,602, 167,898] | -60.7% | no |
| pull__reorder_90 | 833,750 [781,502, 885,998] | 112,250 [96,747, 127,753] | -86.5% | no |

### holding_cost

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 2,501,486 [2,493,940, 2,509,032] | 2,329,652 [2,328,216, 2,331,088] | -6.9% | no |
| push__reorder_50 | 2,575,613 [2,569,011, 2,582,215] | 2,427,437 [2,423,614, 2,431,259] | -5.8% | no |
| push__reorder_90 | 2,723,645 [2,719,054, 2,728,235] | 2,647,826 [2,645,326, 2,650,326] | -2.8% | no |
| pull__on_demand | 2,182,256 [2,160,351, 2,204,162] | 2,255,551 [2,249,038, 2,262,063] | +3.4% | no |
| pull__reorder_50 | 2,431,884 [2,414,621, 2,449,147] | 2,557,520 [2,548,585, 2,566,455] | +5.2% | no |
| pull__reorder_90 | 2,656,464 [2,640,017, 2,672,912] | 2,754,929 [2,740,622, 2,769,235] | +3.7% | no |

### total_emissions_kgco2e

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 35,929,538 [34,061,485, 37,797,590] | 896,604 [894,429, 898,780] | -97.5% | no |
| push__reorder_50 | 12,288,921 [10,808,476, 13,769,366] | 922,132 [919,314, 924,949] | -92.5% | no |
| push__reorder_90 | 29,382,063 [28,038,598, 30,725,529] | 1,126,878 [1,124,161, 1,129,595] | -96.2% | no |
| pull__on_demand | 11,062,480 [9,992,086, 12,132,873] | 2,093,646 [1,964,283, 2,223,008] | -81.1% | no |
| pull__reorder_50 | 15,198,244 [13,904,515, 16,491,973] | 4,199,405 [3,966,012, 4,432,798] | -72.4% | no |
| pull__reorder_90 | 45,874,936 [43,632,344, 48,117,529] | 5,365,881 [5,185,133, 5,546,629] | -88.3% | no |

### bullwhip.treatment_anchored

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 978.22 [963.02, 993.41] | 391.90 [384.88, 398.92] | -59.9% | no |
| push__reorder_50 | 1,913 [1,890, 1,937] | 1,008 [995.89, 1,020] | -47.3% | no |
| push__reorder_90 | 1,087 [1,073, 1,102] | 525.02 [517.43, 532.61] | -51.7% | no |
| pull__on_demand | 985.99 [962.69, 1,009] | 325.19 [318.42, 331.97] | -67.0% | no |
| pull__reorder_50 | 1,753 [1,727, 1,780] | 937.08 [919.34, 954.81] | -46.6% | no |
| pull__reorder_90 | 1,112 [1,094, 1,130] | 736.63 [720.24, 753.01] | -33.7% | no |

### bullwhip.collector_anchored

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 1,248 [1,231, 1,265] | 198.93 [197.04, 200.81] | -84.1% | no |
| push__reorder_50 | 852.38 [836.71, 868.04] | 338.72 [334.27, 343.18] | -60.3% | no |
| push__reorder_90 | 561.65 [554.51, 568.79] | 229.69 [227.39, 232.00] | -59.1% | no |
| pull__on_demand | 1,051 [1,001, 1,101] | 117.57 [114.11, 121.03] | -88.8% | no |
| pull__reorder_50 | 1,031 [999.93, 1,062] | 159.36 [155.76, 162.96] | -84.5% | no |
| pull__reorder_90 | 836.31 [819.02, 853.61] | 175.25 [170.97, 179.53] | -79.0% | no |

### total_collected_m3

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 1,308,697 [1,293,215, 1,324,179] | 1,005,919 [1,004,645, 1,007,193] | -23.1% | no |
| push__reorder_50 | 1,113,206 [1,101,978, 1,124,434] | 996,315 [993,721, 998,909] | -10.5% | no |
| push__reorder_90 | 1,423,204 [1,415,622, 1,430,787] | 1,274,489 [1,273,422, 1,275,557] | -10.4% | no |
| pull__on_demand | 933,376 [908,280, 958,471] | 975,718 [969,927, 981,510] | +4.5% | no |
| pull__reorder_50 | 1,067,907 [1,047,655, 1,088,159] | 1,209,661 [1,202,070, 1,217,253] | +13.3% | no |
| pull__reorder_90 | 1,477,941 [1,458,853, 1,497,030] | 1,393,840 [1,383,646, 1,404,034] | -5.7% | no |

### total_processed_m3

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 79,483 [78,902, 80,063] | 116,128 [115,787, 116,468] | +46.1% | no |
| push__reorder_50 | 88,037 [87,426, 88,649] | 122,667 [122,543, 122,791] | +39.3% | no |
| push__reorder_90 | 86,894 [86,313, 87,475] | 121,890 [121,708, 122,073] | +40.3% | no |
| pull__on_demand | 57,715 [56,426, 59,004] | 100,696 [100,044, 101,348] | +74.5% | no |
| pull__reorder_50 | 79,239 [78,413, 80,065] | 116,171 [115,732, 116,611] | +46.6% | no |
| pull__reorder_90 | 79,014 [78,185, 79,842] | 114,295 [113,774, 114,815] | +44.7% | no |

### total_consumed_m3

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 65,235 [64,769, 65,701] | 93,178 [92,910, 93,447] | +42.8% | no |
| push__reorder_50 | 72,467 [71,998, 72,935] | 98,929 [98,844, 99,014] | +36.5% | no |
| push__reorder_90 | 71,611 [71,161, 72,062] | 98,377 [98,232, 98,522] | +37.4% | no |
| pull__on_demand | 48,128 [47,108, 49,149] | 83,310 [82,773, 83,847] | +73.1% | no |
| pull__reorder_50 | 65,584 [64,943, 66,224] | 95,821 [95,428, 96,215] | +46.1% | no |
| pull__reorder_90 | 65,473 [64,834, 66,113] | 93,774 [93,250, 94,297] | +43.2% | no |

### transport_cost_per_m3

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 2.21 [2.20, 2.22] | 2.06 [2.05, 2.06] | -6.9% | no |
| push__reorder_50 | 2.19 [2.18, 2.21] | 1.96 [1.95, 1.97] | -10.8% | no |
| push__reorder_90 | 2.18 [2.17, 2.19] | 1.95 [1.94, 1.95] | -10.9% | no |
| pull__on_demand | 2.14 [2.09, 2.20] | 2.09 [2.08, 2.10] | -2.3% | yes |
| pull__reorder_50 | 2.18 [2.15, 2.21] | 1.99 [1.98, 2.00] | -8.6% | no |
| pull__reorder_90 | 2.14 [2.12, 2.16] | 2.06 [2.04, 2.07] | -4.1% | no |

### transport_kgco2e_per_m3

| combo | reference mean [95% CI] | daily clock mean [95% CI] | change | CIs overlap |
|---|---|---|---|---|
| push__on_demand | 0.8312 [0.8267, 0.8357] | 0.6925 [0.6908, 0.6942] | -16.7% | no |
| push__reorder_50 | 0.8556 [0.8504, 0.8607] | 0.7136 [0.7107, 0.7165] | -16.6% | no |
| push__reorder_90 | 0.8395 [0.8349, 0.8441] | 0.7195 [0.7175, 0.7215] | -14.3% | no |
| pull__on_demand | 0.7491 [0.7313, 0.7670] | 0.6378 [0.6350, 0.6406] | -14.9% | no |
| pull__reorder_50 | 0.7938 [0.7836, 0.8040] | 0.6855 [0.6821, 0.6890] | -13.6% | no |
| pull__reorder_90 | 0.8046 [0.7976, 0.8117] | 0.7445 [0.7405, 0.7484] | -7.5% | no |

### Ranking (full_service_level desc, total_system_cost asc)

| rank | reference | daily clock |
|---|---|---|
| 1 | push__reorder_50 | push__reorder_50 |
| 2 | push__reorder_90 | push__reorder_90 |
| 3 | pull__reorder_50 | pull__reorder_50 |
| 4 | pull__reorder_90 | pull__reorder_90 |
| 5 | push__on_demand | push__on_demand |
| 6 | pull__on_demand | pull__on_demand |

### Flips (pair order swapped AND new full_service_level 95% CIs disjoint)


FLIPS: 0 []
