# Lakehouse Pipeline Manifest — AWS resources & cost

- **Generated:** 2026-10-01T07:50:46.780637+00:00  ·  region `us-east-2`
- **Source:** `measure_aws_resources.py` + `measure_storage_footprint.py` (S3 figures)
- Exact API values for Glue DPU-seconds, crawler runtime, CloudWatch `storedBytes`, catalog counts, Athena `DataScannedInBytes`. Prices: public on-demand, us-east-2.

## Consumption

| Resource | Quantity |
|---|--:|
| Glue ETL jobs (this pipeline) | 41 |
| Glue job runs (all, incl. failed) | 710 |
| Glue compute — all runs | 958.61 DPU-hr (3,451,005 DPU-s) |
| Glue compute — successful runs only | 873.59 DPU-hr |
| Glue compute — one clean pipeline (min ok run/job) | 10.30 DPU-hr |
| Glue crawler runs / elapsed | 23 / 913 s |
| Glue Data Catalog objects | 102 |
| Athena queries / data scanned (all history) | 55180 / 310.7 GiB |
| CloudWatch Logs (Glue groups, shared) | 1.8 GiB |
| S3 physical — total (as deployed) | 19.8 GiB |
| S3 — Gold live snapshot | 2.0 GiB |
| S3 — Gold objects | 67,242 |
| IAM roles | 8 (no charge) |

## Glue ETL jobs

| Job | Glue | Workers | Runs | ok / fail | DPU-s all | DPU-s 1 run |
|---|---|---|--:|--:|--:|--:|
| `fact-load-fact_chart_observation-full` | 4.0 | 10 x G.2X | 18 | 17 / 1 | 784,750 | 1344.0 |
| `medspacy-nlp-job-full` | 4.0 | 10 x G.1X | 23 | 16 / 5 | 533,998 | 1123.0 |
| `fact-load-fact_lab_result-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 430,502 | 1536.0 |
| `fact-load-fact_medication_administration_mini_detail-full` | 4.0 | 10 x G.2X | 18 | 18 / 0 | 369,344 | 1514.0 |
| `radiology-nlp-job-full` | 4.0 | 10 x G.1X | 23 | 17 / 3 | 264,573 | 597.0 |
| `fact-load-fact_provider_order-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 127,340 | 1298.0 |
| `fact-load-fact_medication_administration-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 114,310 | 1406.0 |
| `fact-load-fact_prescription-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 100,102 | 1446.0 |
| `agg-refresh-agg_admission_daily-full` | 4.0 | 4 x G.1X | 18 | 16 / 2 | 84,801 | 2903.0 |
| `agg-refresh-obt_admission_features-full` | 4.0 | 10 x G.2X | 16 | 16 / 0 | 84,776 | 3188.0 |
| `fact-load-fact_input_event-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 71,304 | 1436.0 |
| `fact-load-fact_ingredient_event-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 63,444 | 1372.0 |
| `agg-refresh-obt_icu_stay_features-full` | 4.0 | 10 x G.2X | 16 | 16 / 0 | 57,054 | 2768.0 |
| `notes-ingest-job-full` | 4.0 | 5 x G.2X | 16 | 16 / 0 | 47,262 | 2776.0 |
| `agg-refresh-agg_icu_fluid_balance_daily-full` | 4.0 | 4 x G.1X | 19 | 16 / 3 | 44,579 | 1677.0 |
| `fact-load-fact_datetime_event-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 41,054 | 1292.0 |
| `agg-refresh-obt_patient_360-full` | 4.0 | 10 x G.2X | 16 | 16 / 0 | 38,942 | 2150.0 |
| `fact-load-fact_provider_order_mini_detail-full` | 4.0 | 10 x G.2X | 19 | 18 / 1 | 34,448 | 1286.0 |
| `fact-load-fact_output_event-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 31,956 | 1250.0 |
| `fact-load-fact_procedure_event-full` | 4.0 | 10 x G.2X | 17 | 17 / 0 | 26,598 | 1316.0 |
| `agg-refresh-agg_admission_monthly-full` | 4.0 | 4 x G.1X | 16 | 16 / 0 | 21,422 | 272.0 |
| `fact-load-fact_pharmacy_order-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 15,832 | 258.0 |
| `fact-load-fact_microbiology_result-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 6,102 | 217.0 |
| `fact-load-fact_outpatient_measurement-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 4,599 | 189.0 |
| `fact-load-fact_diagnosis-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 4,586 | 216.0 |
| `fact-load-fact_transfer-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 4,005 | 193.0 |
| `fact-load-fact_drg_assignment-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 3,540 | 162.0 |
| `fact-load-fact_admission-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 3,374 | 158.0 |
| `fact-load-fact_procedure-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 3,197 | 157.0 |
| `fact-load-fact_hcpcs_event-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 3,125 | 154.0 |
| `fact-load-fact_service_assignment-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 3,120 | 155.0 |
| `dim-load-dim_patient-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,959 | 140.0 |
| `dim-load-dim_diagnosis-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,833 | 139.0 |
| `fact-load-fact_icu_stay_accumulating-full` | 4.0 | 2 x G.1X | 16 | 16 / 0 | 2,812 | 148.0 |
| `dim-load-dim_procedure-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,756 | 126.0 |
| `dim-load-dim_hcpcs-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,722 | 132.0 |
| `dim-load-dim_lab_item-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,679 | 127.0 |
| `dim-load-dim_caregiver-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,669 | 115.0 |
| `dim-load-dim_chart_item-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,589 | 122.0 |
| `dim-load-dim_provider-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,558 | 121.0 |
| `dim-date-seed-job-full` | 4.0 | 2 x G.1X | 17 | 17 / 0 | 2,389 | 106.0 |

## Glue crawler · CloudWatch · Catalog

- **Crawler `mimic4-data-v3-2-crawler-full`** — 23 runs, 913 s elapsed, last 39.673 s.

| CloudWatch log group | Stored |
|---|--:|
| `/aws-glue/jobs/error` | 1.6 GiB |
| `/aws-glue/jobs/logs-v2` | 149.7 MiB |
| `/aws-glue/jobs/output` | 346.2 KiB |
| `/aws-glue/crawlers` | 11.4 KiB |
| `/aws-glue/python-jobs/output` | 3.5 KiB |
| `/aws-glue/python-jobs/error` | 738 B |

| Catalog database | Tables |
|---|--:|
| `mimic4_db_business_full` | 68 |
| `mimic4_db_raw_full` | 34 |

## Cost estimate (USD)

### One-time — build + debugging history (already spent)

| Item | Cost |
|---|--:|
| Glue ETL — every run ever (958.61 DPU-hr) | $421.79 |
| Athena — all query history (310.7 GiB) | $1.67 |
| CloudWatch Logs — ingestion of 1.8 GiB | $0.96 |
| **Total one-time** | **$424.42** |

### One clean end-to-end pipeline run (repeatable unit cost)

| Item | Cost |
|---|--:|
| Glue ETL — one successful run of each of 41 jobs (10.30 DPU-hr) | $4.53 |
| Glue crawler — one run | $0.15 |
| **Total per full rebuild** | **$4.68** |

### Steady-state — monthly, no pipeline runs

| Item | As deployed | After orphan cleanup |
|---|--:|--:|
| S3 storage | $0.490 | $0.412 |
| CloudWatch log storage | $0.058 | $0.058 |
| Glue Data Catalog | $0.000 | $0.000 |
| **Monthly total** | **$0.547** | **$0.469** |

### Load the environment once, keep it running for a year

| Item | As deployed | After orphan cleanup |
|---|--:|--:|
| Load cost (one clean pipeline run) | $4.68 | $4.68 |
| Annual steady-state (12 × monthly) | $6.57 | $5.63 |
| **First-year total** | **$11.25** | **$10.31** |

- load_cost_usd = one_clean_pipeline_run.total_min (one successful Glue ETL run per job + one crawler run) -- the cost to populate an empty environment once.
- annual_steady_state = 12 x steady_state_monthly -- assumes no further pipeline runs during the year (build once, query many); add load_cost_usd again per additional full reload during the year.

### Notes
- Glue Data Catalog: 102 objects < 1,000,000 free tier -> $0/month.
- IAM roles (8), Lake Formation, SSE-S3 encryption: no charge.
- CloudWatch /aws-glue/jobs/* groups are account-wide, shared with the 5 warehouse Glue jobs -- attributed in full here as an upper bound.
- Athena figure is ALL query history in the region (compaction + measurement + NLP dev); a steady-state month scans ~0 ($files reads are metadata, not data).
- S3 'after cleanup' = raw bucket + Gold live snapshot, i.e. once a Spark remove_orphan_files pass removes the superseded pre-compaction files.

## Prices used (us-east-2 on-demand)

- `glue_dpu_hour` = 0.44
- `s3_standard_gb_month` = 0.023
- `s3_put_per_1k` = 0.005
- `s3_get_per_1k` = 0.0004
- `athena_per_tb_scanned` = 5.0
- `cw_logs_ingest_per_gb` = 0.5
- `cw_logs_storage_gb_month` = 0.03
- `glue_catalog_per_100k_objects_month` = 1.0

