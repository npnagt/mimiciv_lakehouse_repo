# Lakehouse vs Data Warehouse — resource usage across the last N runs

Generated 2026-09-23T01:44:50.088852+00:00.
- **Lakehouse**: 6 run(s) reported (of 10 available), source generated 2026-09-23T01:43:38.065138+00:00.
- **Warehouse**: 6 run(s) reported (of 6 available), source generated 2026-09-23T01:44:34.466798+00:00.

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

### Warehouse

| full_run_id | started_at | wall clock | jobs | failed | DPU-s | Cost $ | CW bytes (group total) | CW bytes (attributed) | raw rows | gold rows |
|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 2026-09-19T17:41:02.235776 | 44m39s | 65 | 0 | 5,364.0 | $0.6556 | 9.9 MiB | — | 20,568,186 | 40,626,166 |
| 2 | 2026-09-19T19:57:06.771674 | 38m49s | 65 | 0 | 4,657.0 | $0.5692 | 14.3 MiB | — | 20,568,186 | 40,627,781 |
| 3 | 2026-09-19T20:42:18.283884 | 37m57s | 65 | 0 | 4,550.0 | $0.5561 | 13.4 MiB | — | 20,568,186 | 40,629,396 |
| 4 | 2026-09-19T22:12:27.422217 | 36m59s | 65 | 0 | 4,446.0 | $0.5434 | 2.1 MiB | — | 20,568,186 | 40,631,011 |
| 5 | 2026-09-19T23:27:24.564409 | 37m25s | 65 | 0 | 4,459.0 | $0.5450 | 1.1 GiB | — | 20,568,186 | 40,632,626 |
| 6 | 2026-09-21T10:42:37.240036 | 38m25s | 65 | 0 | 4,589.0 | $0.5609 | 37.6 MiB | — | 20,568,186 | 40,634,241 |

## Per-run statistics, lakehouse vs warehouse

### Wall clock per run (s)  (`wall_clock_seconds` — P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 7,650.258 | 6,555.983 | 2,787.470 | 6,303.437 | 13,330.234 |
| Warehouse | 6 | 2,343.049 | 2,291.730 | 169.527 | 2,219.946 | 2,679.575 |

Ratio (lakehouse mean / warehouse mean): 3.265×

### Total Glue DPU-seconds per run  (`total_dpu_seconds` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 85,179.167 | 85,296.000 | 1,759.259 | 82,538.000 | 87,497.000 |
| Warehouse | 6 | 4,677.500 | 4,569.500 | 345.579 | 4,446.000 | 5,364.000 |

Ratio (lakehouse mean / warehouse mean): 18.210×

### Total Glue DPU-hours per run  (`total_dpu_hours` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 23.661 | 23.693 | 0.489 | 22.927 | 24.305 |
| Warehouse | 6 | 1.299 | 1.269 | 0.096 | 1.235 | 1.490 |

Ratio (lakehouse mean / warehouse mean): 18.210×

### Glue compute cost per run (USD)  (`glue_cost_usd` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 10.411 | 10.425 | 0.215 | 10.088 | 10.694 |
| Warehouse | 6 | 0.572 | 0.558 | 0.042 | 0.543 | 0.656 |

Ratio (lakehouse mean / warehouse mean): 18.211×

### CloudWatch bytes ingested per run  (`cloudwatch_bytes_ingested` — P3, P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 1,721,301,360.667 | 1,719,536,956.500 | 4,936,874.332 | 1,718,221,022.000 | 1,731,244,051.000 |
| Warehouse | 6 | 215,421,112.333 | 14,494,346.000 | 488,145,747.044 | 2,189,168.000 | 1,211,518,853.000 |

Ratio (lakehouse mean / warehouse mean): 7.990×

### Jobs / tables loaded per run  (`job_count` — P1, P2)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 42 | 42.000 | 0.000 | 42 | 42 |
| Warehouse | 6 | 65 | 65.000 | 0.000 | 65 | 65 |

Ratio (lakehouse mean / warehouse mean): 0.646×

### Failed jobs per run  (`failed_count` — P5, P7)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 0 | 0.000 | 0.000 | 0 | 0 |
| Warehouse | 6 | 0 | 0.000 | 0.000 | 0 | 0 |

### Total raw rows processed per run  (`total_raw_rows` — P5)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 893,670,689 | 893,670,689.000 | 0.000 | 893,670,689 | 893,670,689 |
| Warehouse | 6 | 20,568,186 | 20,568,186.000 | 0.000 | 20,568,186 | 20,568,186 |

Ratio (lakehouse mean / warehouse mean): 43.449×

### Total gold rows produced per run  (`total_gold_rows` — P3, P4)

| Environment | n | Mean | Median | Stdev | Min | Max |
|---|--:|--:|--:|--:|--:|--:|
| Lakehouse | 6 | 21,964,590 | 21,964,590.000 | 0.000 | 21,964,590 | 21,964,590 |
| Warehouse | 6 | 40,630,203.500 | 40,630,203.500 | 3,021.388 | 40,626,166 | 40,634,241 |

Ratio (lakehouse mean / warehouse mean): 0.541×

## Current resource footprint (point-in-time, not per-run)

Storage, catalog, and log-retention totals don't have a clean per-run reading on either side (the underlying AWS metrics are daily-to-hourly and lag) -- these are each side's current state, for context alongside the per-run statistics above.

**Lakehouse** (measured 2026-09-23T01:43:38.065013+00:00):
- S3 physical (all): 16.9 GiB  ·  Gold live: 1.3 GiB (74059 objects)
- CloudWatch log groups: 0 B across 0 group(s)
- Glue Data Catalog: 77 tables  ·  Crawlers: 1  ·  IAM roles: 8
- Load + 1 year running: $9.76 as-deployed (load $4.76 + annual $5.00)

**Warehouse** (measured 2026-09-23T01:44:33.502068+00:00):
- Aurora `mimic4rds` volume: 8.8 GiB  ·  ACU-hr since 2026-09-19: 64.031
- Aurora cost: $16.4907 compute+I/O ($7.6837 ACU + $8.8070 I/O, 44,034,929 requests) since 2026-09-19, plus $0.9453/month storage
- S3: 10.2 GiB across 187 objects
- CloudWatch log groups: 0 B across 0 group(s)
- IAM roles: 2
- Load + 1 year running: $11.88 (load $0.5333 + annual $11.34)

**Load + 1 year running, side by side**: lakehouse $9.76 vs warehouse $11.88 (1.22× the lakehouse figure).

