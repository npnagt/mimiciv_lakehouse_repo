# Lakehouse vs Data Warehouse — resource usage across the last N runs

Generated 2026-10-01T07:52:12.298727+00:00.
- **Lakehouse**: 12 run(s) reported (of 16 available), source generated 2026-10-01T07:46:01.713619+00:00.
- **Warehouse**: 8 run(s) reported (of 8 available), source generated 2026-10-01T07:52:07.705726+00:00.

Supports propositions P1-P7 (see the proposition column per metric). Each statistic is mean / median / stdev / min / max across that side's last-N full pipeline runs, computed by each repo's own `measure_aws_resources.py --by-run --last-n <N>` -- run that in both repos first (same --dataset) to refresh these numbers.

## Detailed data -- one row per full_run_id, both sides

The raw per-run rows behind the statistics below, captured here alongside them so the detailed data and the cross-run statistics live in one document instead of two separate per-repo reports. "CW bytes (group total)" is every byte the account's shared Glue log groups ingested during that run's wall-clock window, from any job in the account; "CW bytes (attributed)" is the CloudWatch Logs Insights-computed subset attributable specifically to that run's own Glue JobRunIds -- see either repo's measure_aws_resources.py --by-run output for the full attribution methodology note.

### Lakehouse

| full_run_id | started_at | wall clock | jobs | failed | DPU-s | Cost $ | CW bytes (group total) | CW bytes (attributed) | raw rows | gold rows |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7 | 2026-09-20 02:21:50.915000 | 1h52m | 42 | 0 | 82,538.0 | $10.0880 | 1.6 GiB | — | 893,670,689 | 21,964,590 |
| 8 | 2026-09-20 04:30:38.652000 | 3h42m | 42 | 0 | 85,116.0 | $10.4031 | 1.6 GiB | — | 893,670,689 | 21,964,590 |
| 9 | 2026-09-20 08:38:19.648000 | 1h45m | 42 | 0 | 83,993.0 | $10.2658 | 1.6 GiB | — | 893,670,689 | 21,964,590 |
| 10 | 2026-09-20 11:00:17.399000 | 1h50m | 42 | 0 | 86,455.0 | $10.5667 | 1.6 GiB | — | 893,670,689 | 21,964,590 |
| 11 | 2026-09-20 13:36:40.710000 | 1h46m | 42 | 0 | 85,476.0 | $10.4471 | 1.6 GiB | — | 893,670,689 | 21,964,590 |
| 12 | 2026-09-21 10:54:36.126000 | 1h48m | 42 | 0 | 87,497.0 | $10.6941 | 1.6 GiB | — | 893,670,689 | 21,964,590 |
| 13 | 2026-09-26 17:05:51.495000 | 1h45m | 44 | 0 | 84,176.0 | $10.2882 | 1.6 GiB | 103.9 MiB | 896,323,837 | 22,606,053 |
| 14 | 2026-09-26 20:01:52.876000 | 4h02m | 47 | 1 | 92,688.0 | $11.3285 | 1.7 GiB | 125.3 MiB | 898,645,192 | 22,606,053 |
| 15 | 2026-09-27 16:09:05.830000 | 2h00m | 47 | 0 | 98,231.0 | $12.0060 | 1.6 GiB | 112.7 MiB | 894,002,482 | 22,606,053 |
| 16 | 2026-09-27 20:59:30.614000 | 2h01m | 47 | 0 | 99,086.0 | $12.1105 | 1.6 GiB | 112.7 MiB | 894,002,482 | 22,606,053 |
| 17 | 2026-09-30 00:23:33.620000 | 1h55m | 44 | 0 | 98,482.0 | $12.0367 | 1.6 GiB | 111.6 MiB | 894,002,482 | 22,606,053 |
| 18 | 2026-09-30 22:42:44.958000 | 2h14m | 45 | 0 | 99,461.0 | $12.1563 | 1.6 GiB | 111.8 MiB | 894,002,482 | 22,606,053 |

### Warehouse

| full_run_id | started_at | wall clock | jobs | failed | DPU-s | Cost $ | CW bytes (group total) | CW bytes (attributed) | raw rows | gold rows |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 2026-09-19T17:41:02.235776 | 44m39s | 65 | 0 | 5,364.0 | $0.6556 | 9.9 MiB | — | 20,568,186 | 40,626,166 |
| 2 | 2026-09-19T19:57:06.771674 | 38m49s | 65 | 0 | 4,657.0 | $0.5692 | 14.3 MiB | — | 20,568,186 | 40,627,781 |
| 3 | 2026-09-19T20:42:18.283884 | 37m57s | 65 | 0 | 4,550.0 | $0.5561 | 13.4 MiB | — | 20,568,186 | 40,629,396 |
| 4 | 2026-09-19T22:12:27.422217 | 36m59s | 65 | 0 | 4,446.0 | $0.5434 | 2.1 MiB | — | 20,568,186 | 40,631,011 |
| 5 | 2026-09-19T23:27:24.564409 | 37m25s | 65 | 0 | 4,459.0 | $0.5450 | 1.1 GiB | — | 20,568,186 | 40,632,626 |
| 6 | 2026-09-21T10:42:37.240036 | 38m25s | 65 | 0 | 4,589.0 | $0.5609 | 37.6 MiB | — | 20,568,186 | 40,634,241 |
| 7 | 2026-09-27T15:49:06.983541 | 40m03s | 65 | 0 | 4,833.0 | $0.5907 | 26.9 MiB | 1.1 MiB | 20,568,186 | 40,635,856 |
| 8 | 2026-09-27T16:47:45.926481 | 38m04s | 65 | 0 | 4,575.0 | $0.5592 | 793.4 MiB | 1.1 MiB | 20,568,186 | 40,637,471 |

## Per-run statistics, lakehouse vs warehouse

### Wall clock per run (s)  (`wall_clock_seconds` — P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 8,027.830 | 6,860.916 | 2,824.984 | 6,303.437 | 14,574.186 |
| Warehouse | 8 | 2,343.354 | 2,295.108 | 146.780 | 2,219.946 | 2,679.575 |

Ratio (lakehouse mean / warehouse mean): 3.426×

### Total Glue DPU-seconds per run  (`total_dpu_seconds` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 90,266.583 | 86,976.000 | 6,788.819 | 82,538.000 | 99,461.000 |
| Warehouse | 8 | 4,684.125 | 4,582.000 | 300.348 | 4,446.000 | 5,364.000 |

Ratio (lakehouse mean / warehouse mean): 19.271×

### Total Glue DPU-hours per run  (`total_dpu_hours` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 25.074 | 24.160 | 1.886 | 22.927 | 27.628 |
| Warehouse | 8 | 1.301 | 1.273 | 0.083 | 1.235 | 1.490 |

Ratio (lakehouse mean / warehouse mean): 19.271×

### Glue compute cost per run (USD)  (`glue_cost_usd` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 11.033 | 10.630 | 0.830 | 10.088 | 12.156 |
| Warehouse | 8 | 0.573 | 0.560 | 0.037 | 0.543 | 0.656 |

Ratio (lakehouse mean / warehouse mean): 19.271×

### CloudWatch bytes ingested per run  (`cloudwatch_bytes_ingested` — P3, P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 1,733,430,045.833 | 1,725,901,808.000 | 20,487,054.723 | 1,718,221,022.000 | 1,788,196,170.000 |
| Warehouse | 8 | 269,092,580.625 | 21,607,778.500 | 475,631,097.126 | 2,189,168.000 | 1,211,518,853.000 |

Ratio (lakehouse mean / warehouse mean): 6.442×

### Jobs / tables loaded per run  (`job_count` — P1, P2)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 43.833 | 43.000 | 2.167 | 42 | 47 |
| Warehouse | 8 | 65 | 65.000 | 0.000 | 65 | 65 |

Ratio (lakehouse mean / warehouse mean): 0.674×

### Failed jobs per run  (`failed_count` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 0.083 | 0.000 | 0.289 | 0 | 1 |
| Warehouse | 8 | 0 | 0.000 | 0.000 | 0 | 0 |

### Total raw rows processed per run  (`total_raw_rows` — P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 894,416,924.250 | 893,836,585.500 | 1,523,835.359 | 893,670,689 | 898,645,192 |
| Warehouse | 8 | 20,568,186 | 20,568,186.000 | 0.000 | 20,568,186 | 20,568,186 |

Ratio (lakehouse mean / warehouse mean): 43.485×

### Total gold rows produced per run  (`total_gold_rows` — P3, P4)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 12 | 22,285,321.500 | 22,285,321.500 | 334,993.126 | 21,964,590 | 22,606,053 |
| Warehouse | 8 | 40,631,818.500 | 40,631,818.500 | 3,955.926 | 40,626,166 | 40,637,471 |

Ratio (lakehouse mean / warehouse mean): 0.548×

## Current resource footprint (point-in-time, not per-run)

Storage, catalog, and log-retention totals don't have a clean per-run reading on either side (the underlying AWS metrics are daily-to-hourly and lag) -- these are each side's current state, for context alongside the per-run statistics above.

**Lakehouse** (measured 2026-10-01T07:46:01.713477+00:00):
- S3 physical (all): 19.8 GiB  ·  Gold live: 2.0 GiB (67242 objects)
- CloudWatch log groups: 1.8 GiB across 6 group(s)
- Glue Data Catalog: 102 tables  ·  Crawlers: 1  ·  IAM roles: 8
- Load + 1 year running: $11.25 as-deployed (load $4.68 + annual $6.57)

**Warehouse** (measured 2026-10-01T07:52:06.946641+00:00):
- Aurora `mimic4rds` volume: 8.8 GiB  ·  ACU-hr since 2026-09-19: 74.738
- Aurora cost: $19.7415 compute+I/O ($8.9685 ACU + $10.7730 I/O, 53,865,025 requests) since 2026-09-19, plus $0.9480/month storage
- S3: 10.2 GiB across 219 objects
- CloudWatch log groups: 1.8 GiB across 3 group(s)
- IAM roles: 2
- Load + 1 year running: $12.60 (load $0.5333 + annual $12.07)

**Load + 1 year running, side by side**: lakehouse $11.25 vs warehouse $12.60 (1.12× the lakehouse figure).

