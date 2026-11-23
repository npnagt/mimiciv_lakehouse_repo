# Lakehouse vs Data Warehouse — resource usage across the last N runs

Generated 2026-09-22T00:00:18.618970+00:00.
- **Lakehouse**: 5 run(s) reported (of 9 available), source generated 2026-09-21T10:36:00.255935+00:00.
- **Warehouse**: 5 run(s) reported (of 5 available), source generated 2026-09-21T10:38:36.551747+00:00.

Supports propositions P1-P7 (see the proposition column per metric). Each statistic is mean / median / stdev / min / max across that side's last-N full pipeline runs, computed by each repo's own `measure_aws_resources.py --by-run --last-n <N>` -- run that in both repos first (same --dataset) to refresh these numbers.

## Detailed data -- one row per full_run_id, both sides

The raw per-run rows behind the statistics below, captured here alongside them so the detailed data and the cross-run statistics live in one document instead of two separate per-repo reports. "CW bytes (group total)" is every byte the account's shared Glue log groups ingested during that run's wall-clock window, from any job in the account; "CW bytes (attributed)" is the CloudWatch Logs Insights-computed subset attributable specifically to that run's own Glue JobRunIds -- see either repo's measure_aws_resources.py --by-run output for the full attribution methodology note.

### Lakehouse

| full_run_id | started_at | wall clock | jobs | failed | DPU-s | Cost $ | CW bytes (group total) | CW bytes (attributed) | raw rows | gold rows |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 7 | 2026-09-20 02:21:50.915000 | 1h52m | 42 | 0 | 82,538.0 | $10.0880 | 1.6 GiB | 103.5 MiB | 893,670,689 | 21,964,590 |
| 8 | 2026-09-20 04:30:38.652000 | 3h42m | 42 | 0 | 85,116.0 | $10.4031 | 1.6 GiB | 103.6 MiB | 893,670,689 | 21,964,590 |
| 9 | 2026-09-20 08:38:19.648000 | 1h45m | 42 | 0 | 83,993.0 | $10.2658 | 1.6 GiB | 103.6 MiB | 893,670,689 | 21,964,590 |
| 10 | 2026-09-20 11:00:17.399000 | 1h50m | 42 | 0 | 86,455.0 | $10.5667 | 1.6 GiB | 103.5 MiB | 893,670,689 | 21,964,590 |
| 11 | 2026-09-20 13:36:40.710000 | 1h46m | 42 | 0 | 85,476.0 | $10.4471 | 1.6 GiB | 103.5 MiB | 893,670,689 | 21,964,590 |

### Warehouse

| full_run_id | started_at | wall clock | jobs | failed | DPU-s | Cost $ | CW bytes (group total) | CW bytes (attributed) | raw rows | gold rows |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 2026-09-19T17:41:02.235776 | 44m39s | 65 | 0 | 5,364.0 | $0.6556 | 9.9 MiB | 1.1 MiB | 20,568,186 | 40,626,166 |
| 2 | 2026-09-19T19:57:06.771674 | 38m49s | 65 | 0 | 4,657.0 | $0.5692 | 14.3 MiB | 1.1 MiB | 20,568,186 | 40,627,781 |
| 3 | 2026-09-19T20:42:18.283884 | 37m57s | 65 | 0 | 4,550.0 | $0.5561 | 13.4 MiB | 1.1 MiB | 20,568,186 | 40,629,396 |
| 4 | 2026-09-19T22:12:27.422217 | 36m59s | 65 | 0 | 4,446.0 | $0.5434 | 2.1 MiB | 1.1 MiB | 20,568,186 | 40,631,011 |
| 5 | 2026-09-19T23:27:24.564409 | 37m25s | 65 | 0 | 4,459.0 | $0.5450 | 1.1 GiB | 1.1 MiB | 20,568,186 | 40,632,626 |

## Per-run statistics, lakehouse vs warehouse

### Wall clock per run (s)  (`wall_clock_seconds` — P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 7,880.111 | 6,610.968 | 3,052.252 | 6,303.437 | 13,330.234 |
| Warehouse | 5 | 2,350.544 | 2,277.885 | 188.422 | 2,219.946 | 2,679.575 |

Ratio (lakehouse mean / warehouse mean): 3.352×

### Total Glue DPU-seconds per run  (`total_dpu_seconds` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 84,715.600 | 85,116.000 | 1,502.343 | 82,538.000 | 86,455.000 |
| Warehouse | 5 | 4,695.200 | 4,550.000 | 383.317 | 4,446.000 | 5,364.000 |

Ratio (lakehouse mean / warehouse mean): 18.043×

### Total Glue DPU-hours per run  (`total_dpu_hours` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 23.532 | 23.643 | 0.417 | 22.927 | 24.015 |
| Warehouse | 5 | 1.304 | 1.264 | 0.106 | 1.235 | 1.490 |

Ratio (lakehouse mean / warehouse mean): 18.043×

### Glue compute cost per run (USD)  (`glue_cost_usd` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 10.354 | 10.403 | 0.184 | 10.088 | 10.567 |
| Warehouse | 5 | 0.574 | 0.556 | 0.047 | 0.543 | 0.656 |

Ratio (lakehouse mean / warehouse mean): 18.043×

### CloudWatch bytes ingested per run  (`cloudwatch_bytes_ingested` — P3, P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 1,721,449,719.800 | 1,719,426,497.000 | 5,504,619.149 | 1,718,221,022.000 | 1,731,244,051.000 |
| Warehouse | 5 | 250,610,304.200 | 14,004,396.000 | 537,187,810.514 | 2,189,168.000 | 1,211,518,853.000 |

Ratio (lakehouse mean / warehouse mean): 6.869×

### Jobs / tables loaded per run  (`job_count` — P1, P2)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 42 | 42 | 0.000 | 42 | 42 |
| Warehouse | 5 | 65 | 65 | 0.000 | 65 | 65 |

Ratio (lakehouse mean / warehouse mean): 0.646×

### Failed jobs per run  (`failed_count` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 0 | 0 | 0.000 | 0 | 0 |
| Warehouse | 5 | 0 | 0 | 0.000 | 0 | 0 |

### Total raw rows processed per run  (`total_raw_rows` — P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 893,670,689 | 893,670,689 | 0.000 | 893,670,689 | 893,670,689 |
| Warehouse | 5 | 20,568,186 | 20,568,186 | 0.000 | 20,568,186 | 20,568,186 |

Ratio (lakehouse mean / warehouse mean): 43.449×

### Total gold rows produced per run  (`total_gold_rows` — P3, P4)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 5 | 21,964,590 | 21,964,590 | 0.000 | 21,964,590 | 21,964,590 |
| Warehouse | 5 | 40,629,396 | 40,629,396 | 2,553.539 | 40,626,166 | 40,632,626 |

Ratio (lakehouse mean / warehouse mean): 0.541×

## Current resource footprint (point-in-time, not per-run)

Storage, catalog, and log-retention totals don't have a clean per-run reading on either side (the underlying AWS metrics are daily-to-hourly and lag) -- these are each side's current state, for context alongside the per-run statistics above.

**Lakehouse** (measured 2026-09-21T10:36:00.255840+00:00):
- S3 physical (all): 16.8 GiB  ·  Gold live: 1.3 GiB (73208 objects)
- CloudWatch log groups: 4.3 GiB across 7 group(s)
- Glue Data Catalog: 77 tables  ·  Crawlers: 1  ·  IAM roles: 8
- Load + 1 year running: $11.43 as-deployed (load $4.77 + annual $6.65)

**Warehouse** (measured 2026-09-21T10:38:35.530635+00:00):
- Aurora `mimic4rds` volume: 8.8 GiB  ·  ACU-hr since 2026-09-19: 56.689
- Aurora cost: $14.2660 compute+I/O ($6.8027 ACU + $7.4633 I/O, 37,316,704 requests) since 2026-09-19, plus $0.9431/month storage
- S3: 10.1 GiB across 171 objects
- CloudWatch log groups: 4.3 GiB across 3 group(s)
- IAM roles: 2
- Load + 1 year running: $13.52 (load $0.5333 + annual $12.98)

**Load + 1 year running, side by side**: lakehouse $11.43 vs warehouse $13.52 (1.18× the lakehouse figure).

