# Lakehouse vs Data Warehouse — consolidated comparison

Generated 2026-10-01T07:52:12.395180+00:00. Sources: lakehouse_cost 2026-10-01, lakehouse_storage 2026-10-01, lakehouse_tti 2026-10-01, lakehouse_p5 2026-10-01, lakehouse_iceberg_vs_raw 2026-10-01, aurora_baseline 2026-09-22, warehouse_by_run 2026-10-01

## Proposition scorecard

| P | Claim | Lakehouse | Warehouse | Verdict |
|---|---|---|---|---|
| **P1** | Layered architecture supports more end-to-end workflows | 88.9%  (35 S / 10 P / 0 U) | 72.2%  (26 S / 13 P / 6 U) | holds — the gap is entirely in the 18 cross-modal workflows |
| **P2** | Fewer integration points for cross-modal queries | ≈ 3.3 | ≈ 6.1 | holds — mechanism is the shared Glue catalog |
| **P3** | Less physical data duplication (redundancy ratio) | 12197.0 MiB live / 14875.0 MiB phys / 1.0× compacted (gold is the only copy) | 8334.41 MiB live / 8856.23 MiB phys / 2.0× (staging + warehouse) | holds architecturally — lakehouse eliminates the staging materialization (external tables = 0 bytes); on information content it is ~0.15× the warehouse |
| **P4** | More ad-hoc queries combining structured data with AI outputs | 97.8%  (43 answerable, 2 partial, 0 no) | 7.8%  (0 answerable, 7 structured proxy, 38 no path) | holds decisively — NLP tables are in the shared catalog vs absent from Postgres |
| **P5** | Native in-lake join beats externalized two-stage pipeline | native (Athena/Iceberg): 1,938 ms, 798,548 rows/s | external (Athena UNLOAD + DuckDB): 4,820 ms (321,108 rows/s); DuckDB join alone 120 ms | holds — native ~2.5× faster end to end; the whole penalty is the extract hop, not the engine |
| **P6** | Unified abstraction layer renders results inside Nielsen's sustained-attention band (1-10 s), not the >10 s attention-lost band | cold 0 A / 19 B / 0 C  (p90 2104 ms); 100.0% within 10 s; warm 100% band A (~0.8 s) | n/a — proposition has no baseline comparison | PASS -- every query lands at or under 10 s |
| **P7** | Less effort to re-execute models when new data arrives | agg/OBT + NLP jobs incremental via etl_control — re-run 100–125 s (platform floor) vs 183–1,846 s backfill; 2–16× faster | no incremental mechanism — every refresh is a full TRUNCATE+reload (~954 DPU-s, README: “that mechanism isn’t implemented here”) | holds — lakehouse cost scales with what changed, warehouse with total volume |
| **P8** | Engineers complete tasks faster + lower NASA-TLX with multimodal schemas | — | — | not tested — human study |
| **P9** | Practitioners perceive gains outweigh complexity (TAM), high intent to adopt | — | — | not tested — human study |

## Evidence status

| P | Metric | Evidence |
|---|---|---|
| P1 | workflow coverage (Supported + ½·Partial) / 45 | analysis — atlas_P1_workflow_taxonomy.docx (lakehouse repo-verified; decoupled baseline scored as-designed, not built) |
| P2 | mean onboarding integration points, cross-modal rows | analysis — counted from Glue job DAGs + Athena joins in both repos |
| P3 | structured layer: live bytes / physical bytes / redundancy ratio | ✅ measured both sides — measure_storage_footprint.py + measure_warehouse_size.py |
| P4 | 45-query catalogue coverage | analysis — atlas_P4_adhoc_query_catalog.docx (2 queries verified live in Athena) |
| P5 | wall-clock + throughput for a 3-way join + aggregate | ✅ measured — measure_native_vs_external_join.py (12 reps) |
| P6 | 19-query battery; % within 10 s (sustained attention or faster), p90 | ✅ measured — measure_time_to_insight.py (standalone; no baseline required) |
| P7 | incremental refresh vs full reload, re-run wall time | ✅ lakehouse verified via Glue run stats; warehouse from its manifest + README |
| P8 | task completion time + raw NASA-TLX, within-subject | needs a 5-task battery, a digital NASA-TLX form, counterbalanced design, paired t-tests + Cohen's d |
| P9 | Davis TAM instrument (PU / PEOU / BI) + net-benefit item | needs the validated TAM survey; ~N=34 per condition for d=0.5 at power 0.8 |

## Pipeline cost

| | Lakehouse | Warehouse |
|---|--:|--:|
| One-time build + debug | $424.42 | $27.14 |
| One clean rebuild | $4.68 | $0.5333 |
| Steady-state / month (idle) | $0.547 (→ $0.469 cleaned) | $1.006 |
| **Load + 1 year running** | **$11.25** | **$12.60** |

Warehouse one-time detail (live): LIVE (measured 2026-10-01T07:52:06.946641+00:00): Aurora compute+I/O $19.7415 + Glue $6.44 + CloudWatch ingest $0.9590

## Gold Iceberg vs raw source CSV archives (lakehouse)

Per-row comparison (fact tables over 1M rows hold a 1M-row sample; the raw archive holds every row). Full per-table detail: `docs/iceberg_vs_raw/<mode>/latest.md`.

| Group | Tables | Raw .csv.gz | Iceberg, full-row equivalent | Iceberg / raw | Iceberg smaller per row |
|---|--:|--:|--:|--:|--:|
| Fact tables | 23 | 9.9 GiB | 19.9 GiB | 2.006× (100.6%) | 1 of 23 |
| Dimensions | 8 | 4.7 MiB | 4.8 MiB | 1.018× (1.8%) | 3 of 8 |
| **All source-loaded** | 31 | 9.9 GiB | 19.9 GiB | 2.006× (100.6%) | 4 of 31 |
| Note text (as loaded, bytes only) | 2 | 1.8 GiB | 1.3 GiB | 0.752× | -- |

Whole Gold layer: 45 tables, 2.0 GiB live / 4.6 GiB physical. Not a pure format benchmark -- the Gold schema adds keys, derived measures and audit columns (see the detail report).

Row-count mismatch on 7 fully loaded table(s): `fact_drg_assignment` +1, `fact_hcpcs_event` +1, `fact_procedure` +1, `fact_service_assignment` +1, `fact_procedure_event` +1, `fact_admission` +1, `fact_icu_stay_accumulating` +1.

