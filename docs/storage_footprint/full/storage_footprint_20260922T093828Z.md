# Lakehouse storage footprint

- **Generated:** 2026-09-22T09:38:28.664533+00:00  ·  script v1.2.0  ·  repo `e0441f1`
- **AWS account:** `605785396773`  ·  **region:** `us-east-2`
- **Buckets:** raw `mimic4-datalake-v3-2-full` · gold `mimic4-lakehouse-v3-2-full` (prefix `mimic_bus`) · nlp-debug `mimic4-nlp-v3-2-full` · scripts `mimic4-glue-scripts-v3-2-bucket`
- **Gold database:** `mimic4_db_business_full`  ·  Athena workgroup `primary`

## Summary

| Metric | Bytes | Human |
|---|--:|--:|
| Total lakehouse (physical) | 18,113,251,246 | 16.87 GiB |
| Raw bucket | 15,763,592,751 | 14.68 GiB |
| Gold bucket (physical) | 1,783,158,595 | 1.66 GiB |
| Gold live snapshot | 1,401,794,162 | 1.31 GiB |
| **AI-inference layer (physical)** | 345,268,045 | 329.27 MiB |

## Structured vs unstructured / NLP

The Aurora PostgreSQL warehouse (`mimic_datawarehouse_repo`) carries **only the structured category** — no clinical notes, no NLP-derived tables, no note text. So the P3 redundancy-ratio comparison is made on the **structured** row alone; the **unstructured / NLP** row is coverage the lakehouse adds, not duplication.

| Category | Physical | Live snapshot | % of lakehouse | In the Aurora warehouse? |
|---|--:|--:|--:|:--:|
| **Structured** — raw `*_raw` CSV + `dim_`/`fact_`/`agg_`/`obt_`/`etl_control` (40 Gold tables) | 11.26 GiB | 11.16 GiB | 66.7693% | yes — `warehouse` schema |
| **Unstructured / NLP** — note `.csv.gz` + `*_note_raw` Parquet + `fact_discharge_note_nlp`/`fact_radiology_note_nlp*` (3 Gold tables) + per-note JSON | 5.61 GiB | 5.35 GiB | 33.2295% | **no** |
| Infrastructure — Glue scripts, stray Athena results | 208.29 KiB | — | 0.0012% | n/a |

Breakdown of the unstructured / NLP category:

| Component | Physical |
|---|--:|
| Clinical note text (`discharge_raw` + `radiology_raw` `.csv.gz`) | 1.79 GiB |
| Converted note Parquet (`discharge_note_raw`, `radiology_note_raw`) | 2.97 GiB |
| NLP-derived Gold tables (physical / live) | 329.27 MiB / 68.53 MiB |
| Per-note debug JSON (`mimic4-nlp-v3-2-full`) | 540.05 MiB |

**For a P3 redundancy ratio vs. the Aurora warehouse, compare `11.16 GiB` (structured, live snapshot)** — ideally after `OPTIMIZE … REWRITE DATA` — against that warehouse's `pg_total_relation_size()` over `staging` + `warehouse` plus its own raw S3 landing copy. The lakehouse additionally carries **5.61 GiB** of unstructured / NLP data that has no warehouse equivalent at all.

## Data warehouse vs data lakehouse — space comparison

Aurora baseline: **AWS RDS Aurora PostgreSQL data warehouse (mimic_datawarehouse_repo)** (2026-09-22). The raw structured CSV files are identical for both architectures, so they are one shared line and excluded from the head-to-head of the *processed* layers — which is where the two designs actually differ.

| Layer | Data warehouse (Aurora) | Data lakehouse |
|---|--:|--:|
| Raw structured CSV.gz in S3 *(shared — same files)* | 9.92 GiB | 9.92 GiB |
| Staging / raw-mirror layer | *materialized* — part of the total below (`staging.stg_*`, full TRUNCATE+reload) | **0 B** — `mimic4_db_raw` is external tables over the same S3 files |
| Modeled / queryable layer | `warehouse.dim_/fact_/agg_*` | Gold Iceberg |
| **Processed structured — physical** | **8.65 GiB** (67 tables) | **1.34 GiB** (40 tables) |
| **Processed structured — live / current** | 8.14 GiB | 1.24 GiB |
| Processed structured — compacted-logical | ~8.14 GiB (Postgres, little bloat) | 1.24 GiB (**measured** — post-`OPTIMIZE … REWRITE DATA`) |
| `pg_database_size()` (incl. catalogs) | 8.66 GiB | n/a |

| Unstructured / NLP | Data warehouse (Aurora) | Data lakehouse |
|---|--:|--:|
| Clinical note text (raw source) | not stored | 1.79 GiB |
| **NLP-derived tables** (physical / live) | **0 B — cannot store** | 329.27 MiB / 68.53 MiB |

**Head-to-head, processed structured:** on the **live snapshot** — the data a correctly-maintained Iceberg table actually serves, and now bin-packed by `OPTIMIZE` — the lakehouse is **0.15×** the warehouse (1.24 GiB vs 8.14 GiB), i.e. it holds the same structured information in a fraction of the space — **P3 supported**. On **raw physical bytes** it is still **0.15×** the warehouse: the live snapshot is only 92.5% of physical because Athena `VACUUM` expired the superseded snapshots but did not delete their data files (verified) — a Spark `remove_orphan_files` pass is required to reclaim them, and is a tooling gap, not an architecture property.

**Redundancy ratio (physical ÷ one clean modeled copy), structured:**

| Architecture | Ratio | Why |
|---|--:|---|
| Data warehouse | **2.0×** | two full materializations inside Postgres -- staging.stg_* (full TRUNCATE+reload of every source) + warehouse.* (modeled copy); the shared raw CSV in S3 is a third copy, excluded as it is common to both architectures |
| Data lakehouse — as deployed | 1.08× | OPTIMIZE has run (live snapshot IS bin-packed); the residual physical/live gap is superseded data files that Athena VACUUM expired the snapshots for but did not delete -- reclaimable only by a Spark remove_orphan_files pass. Not architecture. |
| Data lakehouse — compacted | **1.0×** | live snapshot = one clean modeled copy; gold is the only physical processed copy, the mimic4_db_raw staging layer is external tables (0 bytes) |

**P3 holds.** The warehouse materializes the structured data twice inside Postgres (`staging.stg_*` full reload + `warehouse.*` modeled); the lakehouse materializes it once (Gold), because its staging layer is external tables over the raw CSVs — **0 bytes**. That is one full physical copy the lakehouse eliminates (redundancy 2.0× vs 1.0×). On information content (the live snapshot) the lakehouse is 0.15× the warehouse. The only figure that still favours the warehouse is raw physical bytes, and that is orphaned data files awaiting a Spark `remove_orphan_files` pass — not a second copy of the data.

**Unstructured / NLP:** Aurora holds 0 bytes -- a coverage gap, not a space win. The lakehouse holds the NLP-derived tables in ONE copy (shared catalog); a decoupled architecture that did NLP would hold each output in >= 2 (model store + warehouse load).

### Per-table detail — data warehouse (Aurora)

`live` = pgstattuple's exact live-tuple accounting (or the live/dead-tuple-ratio estimate if that extension isn't available) plus full-size indexes/TOAST — the same "current, visible content" concept as the lakehouse's Live snapshot column, just computed inside Postgres instead of from Iceberg's `$files` metadata table.

| Table | Schema | Cat. | Rows | Physical | Live | Phys/Live |
|---|---|---|--:|--:|--:|--:|
| `fact_input_event` | warehouse | str | 999,887 | 463.57 MiB | 447.27 MiB | 1.04 |
| `fact_prescription` | warehouse | str | 999,892 | 398.18 MiB | 385.85 MiB | 1.03 |
| `fact_ingredient_event` | warehouse | str | 1,000,020 | 364.17 MiB | 351.21 MiB | 1.04 |
| `fact_microbiology_result` | warehouse | str | 1,000,166 | 337.20 MiB | 324.32 MiB | 1.04 |
| `fact_procedure_event` | warehouse | str | 808,693 | 326.08 MiB | 314.47 MiB | 1.04 |
| `fact_pharmacy_order` | warehouse | str | 999,850 | 318.73 MiB | 305.54 MiB | 1.04 |
| `stg_inputevents` | staging | str | 1,000,139 | 309.11 MiB | 299.33 MiB | 1.03 |
| `fact_datetime_event` | warehouse | str | 1,000,000 | 293.23 MiB | 283.60 MiB | 1.03 |
| `fact_medication_administration_mini_detail` | warehouse | str | 999,936 | 281.60 MiB | 271.52 MiB | 1.04 |
| `fact_output_event` | warehouse | str | 1,000,000 | 278.27 MiB | 267.00 MiB | 1.04 |
| `fact_medication_administration` | warehouse | str | 999,986 | 275.45 MiB | 264.09 MiB | 1.04 |
| `stg_microbiologyevents` | staging | str | 999,668 | 272.20 MiB | 260.71 MiB | 1.04 |
| `fact_lab_result` | warehouse | str | 1,000,000 | 260.95 MiB | 250.28 MiB | 1.04 |
| `stg_pharmacy` | staging | str | 999,953 | 253.66 MiB | 243.73 MiB | 1.04 |
| `fact_chart_observation` | warehouse | str | 1,008,075 | 229.15 MiB | 218.79 MiB | 1.05 |
| `fact_provider_order` | warehouse | str | 1,000,000 | 228.04 MiB | 217.62 MiB | 1.05 |
| `stg_prescriptions` | staging | str | 1,000,000 | 213.55 MiB | 202.94 MiB | 1.05 |
| `stg_procedureevents` | staging | str | 808,706 | 203.55 MiB | 196.84 MiB | 1.03 |
| `fact_transfer` | warehouse | str | 1,000,000 | 202.74 MiB | 193.01 MiB | 1.05 |
| `stg_ingredientevents` | staging | str | 1,000,000 | 202.19 MiB | 195.16 MiB | 1.04 |
| `fact_outpatient_measurement` | warehouse | str | 1,000,000 | 185.38 MiB | 176.34 MiB | 1.05 |
| `stg_emar` | staging | str | 1,000,000 | 183.84 MiB | 174.10 MiB | 1.06 |
| `fact_diagnosis` | warehouse | str | 999,977 | 177.86 MiB | 168.03 MiB | 1.06 |
| `fact_drg_assignment` | warehouse | str | 761,856 | 174.98 MiB | 167.57 MiB | 1.04 |
| `fact_admission` | warehouse | str | 546,028 | 166.84 MiB | 160.05 MiB | 1.04 |
| `stg_labevents` | staging | str | 1,000,000 | 160.81 MiB | 152.76 MiB | 1.05 |
| `fact_procedure` | warehouse | str | 859,650 | 156.42 MiB | 148.84 MiB | 1.05 |
| `stg_datetimeevents` | staging | str | 1,000,000 | 144.97 MiB | 139.57 MiB | 1.04 |
| `stg_chartevents` | staging | str | 1,000,000 | 137.42 MiB | 132.19 MiB | 1.04 |
| `stg_poe` | staging | str | 1,000,000 | 135.38 MiB | 126.27 MiB | 1.07 |
| `stg_emar_detail` | staging | str | 1,000,000 | 122.62 MiB | 114.34 MiB | 1.07 |
| `stg_outputevents` | staging | str | 1,000,000 | 120.26 MiB | 109.74 MiB | 1.1 |
| `dim_patient` | warehouse | str | 364,627 | 119.30 MiB | 65.08 MiB | 1.83 |
| `stg_admissions` | staging | str | 546,028 | 113.09 MiB | 109.47 MiB | 1.03 |
| `stg_transfers` | staging | str | 1,000,000 | 107.58 MiB | 100.98 MiB | 1.07 |
| `fact_service_assignment` | warehouse | str | 593,070 | 107.28 MiB | 102.20 MiB | 1.05 |
| `stg_poe_detail` | staging | str | 1,000,000 | 85.33 MiB | 76.33 MiB | 1.12 |
| `stg_drgcodes` | staging | str | 761,856 | 82.98 MiB | 78.01 MiB | 1.06 |
| `stg_omr` | staging | str | 1,000,000 | 80.62 MiB | 71.94 MiB | 1.12 |
| `stg_procedures_icd` | staging | str | 859,655 | 65.84 MiB | 62.06 MiB | 1.06 |
| `stg_diagnoses_icd` | staging | str | 1,000,000 | 65.16 MiB | 61.09 MiB | 1.07 |
| `agg_admission_daily` | warehouse | str | 244,500 | 54.11 MiB | 34.42 MiB | 1.57 |
| `dim_diagnosis` | warehouse | str | 112,107 | 48.34 MiB | 26.52 MiB | 1.82 |
| `stg_services` | staging | str | 593,071 | 40.95 MiB | 36.81 MiB | 1.11 |
| `dim_procedure` | warehouse | str | 86,423 | 37.79 MiB | 20.60 MiB | 1.83 |
| `fact_hcpcs_event` | warehouse | str | 186,074 | 37.55 MiB | 35.77 MiB | 1.05 |
| `fact_provider_order_mini_detail` | warehouse | str | 159,231 | 33.58 MiB | 32.06 MiB | 1.05 |
| `dim_hcpcs` | warehouse | str | 89,208 | 30.52 MiB | 16.58 MiB | 1.84 |
| `stg_patients` | staging | str | 364,627 | 26.95 MiB | 24.09 MiB | 1.12 |
| `fact_icu_stay_accumulating` | warehouse | str | 94,458 | 24.91 MiB | 23.84 MiB | 1.04 |
| `dim_date` | warehouse | str | 47,846 | 19.20 MiB | 10.16 MiB | 1.89 |
| `stg_hcpcsevents` | staging | str | 186,074 | 19.01 MiB | 17.59 MiB | 1.08 |
| `agg_icu_fluid_balance_daily` | warehouse | str | 75,366 | 17.09 MiB | 10.70 MiB | 1.6 |
| `stg_icustays` | staging | str | 94,458 | 15.85 MiB | 15.30 MiB | 1.04 |
| `stg_d_icd_diagnoses` | staging | str | 112,107 | 12.70 MiB | 11.79 MiB | 1.08 |
| `stg_d_icd_procedures` | staging | str | 86,423 | 10.12 MiB | 9.42 MiB | 1.07 |
| `stg_d_hcpcs` | staging | str | 89,208 | 5.84 MiB | 5.17 MiB | 1.13 |
| `dim_provider` | warehouse | str | 42,244 | 5.68 MiB | 5.39 MiB | 1.05 |
| `agg_admission_monthly` | warehouse | str | 10,856 | 2.47 MiB | 1.59 MiB | 1.56 |
| `dim_caregiver` | warehouse | str | 17,984 | 2.45 MiB | 2.33 MiB | 1.05 |
| `dim_chart_item` | warehouse | str | 4,095 | 1.90 MiB | 1.03 MiB | 1.84 |
| `stg_provider` | staging | str | 42,244 | 1.50 MiB | 1.29 MiB | 1.16 |
| `stg_caregiver` | staging | str | 17,984 | 672.00 KiB | 594.00 KiB | 1.13 |
| `dim_lab_item` | warehouse | str | 1,650 | 632.00 KiB | 363.81 KiB | 1.74 |
| `stg_d_items` | staging | str | 4,095 | 568.00 KiB | 527.73 KiB | 1.08 |
| `etl_process_log` | warehouse | str | 390 | 192.00 KiB | 170.86 KiB | 1.12 |
| `stg_d_labitems` | staging | str | 1,650 | 160.00 KiB | 144.44 KiB | 1.11 |

## Raw bucket

| Class | Category | Bytes | Human | % of bucket | Prefixes |
|---|---|--:|--:|--:|---|
| note_parquet | unstructured_nlp | 3,186,351,281 | 2.97 GiB | 20.2134% | 2 |
| note_text_gz | unstructured_nlp | 1,921,034,145 | 1.79 GiB | 12.1865% | 2 |
| structured_csv | structured | 10,656,207,325 | 9.92 GiB | 67.6001% | 31 |

Free-text clinical notes (`.csv.gz`) are **12.1865%** of the raw bucket; the structured MIMIC-IV CSVs are **67.6001%** (9.92 GiB).

## Gold Iceberg layer

- Physical: **1.66 GiB** in **74,059 objects** (1.54 GiB data + 118.49 MiB Iceberg metadata)
- Current snapshot ("live"): **1.31 GiB** in **67,497 files** — physical is **1.27×** the live snapshot (un-expired snapshots).
- **40 tables** average < 1 MiB per live data file (small-file fragmentation from `bucket()` / `day()` partitioning on a demo-sized dataset):
  - `etl_control` — 8.00 KiB in 7 files (~1.14 KiB/file)
  - `agg_admission_monthly` — 2.86 MiB in 1,262 files (~2.32 KiB/file)
  - `etl_process_log` — 1.18 MiB in 418 files (~2.90 KiB/file)
  - `dim_lab_item` — 75.21 KiB in 20 files (~3.76 KiB/file)
  - `fact_discharge_note_nlp` — 12.83 MiB in 2,304 files (~5.70 KiB/file)
  - `fact_diagnosis` — 19.91 MiB in 3,201 files (~6.37 KiB/file)
  - `fact_hcpcs_event` — 5.65 MiB in 801 files (~7.22 KiB/file)
  - `fact_provider_order_mini_detail` — 23.07 MiB in 3,200 files (~7.38 KiB/file)

### Per-table detail

`file records` = Σ `record_count` over the current snapshot's data files — the true current row count for a copy-on-write table. If it exceeds `count(*)` (run with `--exact-rows` to check) the snapshot holds unmerged delete files or duplicate data from an append-instead-of-overwrite re-run.

| Table | Class | Cat. | Physical | Data | Iceberg meta | Live snapshot | Live files | File records | Phys/Live |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|
| `fact_radiology_note_nlp_v` | ai_nlp | NLP | 245.71 MiB | 245.18 MiB | 542.68 KiB | n/a (fmt-v3) | — | — | — |
| `fact_lab_result` | fact | str | 150.94 MiB | 148.33 MiB | 2.61 MiB | 148.33 MiB | 12,801 | 1,000,000 | 1.02 |
| `fact_medication_administration_mini_detail` | fact | str | 105.82 MiB | 104.19 MiB | 1.62 MiB | 104.19 MiB | 6,400 | 1,000,000 | 1.02 |
| `fact_medication_administration` | fact | str | 103.26 MiB | 101.86 MiB | 1.39 MiB | 101.86 MiB | 6,400 | 1,000,000 | 1.01 |
| `fact_pharmacy_order` | fact | str | 103.08 MiB | 102.03 MiB | 1.05 MiB | 102.03 MiB | 3,201 | 1,000,000 | 1.01 |
| `fact_prescription` | fact | str | 93.78 MiB | 92.94 MiB | 856.49 KiB | 92.94 MiB | 3,201 | 1,000,000 | 1.01 |
| `etl_process_log` | control | str | 90.83 MiB | 1.21 MiB | 89.62 MiB | 1.18 MiB | 418 | 426 | 76.66 |
| `fact_input_event` | fact | str | 87.82 MiB | 87.29 MiB | 535.08 KiB | 87.29 MiB | 1,601 | 1,000,000 | 1.01 |
| `fact_ingredient_event` | fact | str | 86.92 MiB | 86.14 MiB | 804.03 KiB | 86.14 MiB | 3,201 | 1,000,000 | 1.01 |
| `fact_microbiology_result` | fact | str | 77.79 MiB | 77.25 MiB | 549.21 KiB | 77.25 MiB | 1,601 | 1,000,000 | 1.01 |
| `fact_radiology_note_nlp` | ai_nlp | NLP | 67.30 MiB | 55.70 MiB | 11.61 MiB | 55.70 MiB | 2,711 | 2,711 | 1.21 |
| `fact_procedure_event` | fact | str | 56.59 MiB | 56.27 MiB | 325.76 KiB | 56.27 MiB | 1,000 | 808,707 | 1.01 |
| `fact_datetime_event` | fact | str | 46.26 MiB | 45.98 MiB | 288.48 KiB | 45.98 MiB | 1,601 | 1,000,000 | 1.01 |
| `fact_output_event` | fact | str | 42.87 MiB | 42.61 MiB | 269.89 KiB | 42.61 MiB | 1,601 | 1,000,000 | 1.01 |
| `fact_transfer` | fact | str | 39.26 MiB | 38.99 MiB | 281.72 KiB | 38.99 MiB | 1,601 | 1,000,000 | 1.01 |
| `fact_chart_observation` | fact | str | 38.72 MiB | 38.43 MiB | 296.11 KiB | 38.43 MiB | 1,601 | 1,000,000 | 1.01 |
| `obt_admission_features` | obt | str | 35.41 MiB | 34.86 MiB | 563.73 KiB | 34.86 MiB | 1,259 | 546,031 | 1.02 |
| `fact_provider_order` | fact | str | 31.21 MiB | 31.17 MiB | 46.81 KiB | 31.17 MiB | 200 | 1,000,000 | 1.0 |
| `fact_admission` | fact | str | 26.40 MiB | 26.37 MiB | 33.76 KiB | 26.37 MiB | 17 | 546,029 | 1.0 |
| `fact_provider_order_mini_detail` | fact | str | 23.34 MiB | 23.07 MiB | 282.14 KiB | 23.07 MiB | 3,200 | 1,000,000 | 1.01 |
| `fact_diagnosis` | fact | str | 20.13 MiB | 19.91 MiB | 229.76 KiB | 19.91 MiB | 3,201 | 1,000,000 | 1.01 |
| `fact_drg_assignment` | fact | str | 19.76 MiB | 19.61 MiB | 155.66 KiB | 19.61 MiB | 1,601 | 761,857 | 1.01 |
| `fact_outpatient_measurement` | fact | str | 18.34 MiB | 18.19 MiB | 153.31 KiB | 18.19 MiB | 1,601 | 1,000,000 | 1.01 |
| `fact_procedure` | fact | str | 16.53 MiB | 16.44 MiB | 96.51 KiB | 16.44 MiB | 801 | 859,656 | 1.01 |
| `fact_discharge_note_nlp` | ai_nlp | NLP | 16.25 MiB | 12.83 MiB | 3.42 MiB | 12.83 MiB | 2,304 | 10,000 | 1.27 |
| `obt_icu_stay_features` | obt | str | 15.04 MiB | 14.69 MiB | 356.81 KiB | 14.69 MiB | 1,230 | 94,458 | 1.02 |
| `fact_service_assignment` | fact | str | 12.81 MiB | 12.72 MiB | 97.90 KiB | 12.72 MiB | 801 | 593,072 | 1.01 |
| `obt_patient_360` | obt | str | 7.39 MiB | 7.36 MiB | 27.15 KiB | 7.36 MiB | 5 | 364,627 | 1.0 |
| `fact_hcpcs_event` | fact | str | 5.74 MiB | 5.65 MiB | 96.57 KiB | 5.65 MiB | 801 | 186,075 | 1.02 |
| `fact_icu_stay_accumulating` | fact | str | 3.56 MiB | 3.54 MiB | 25.37 KiB | 3.54 MiB | 17 | 94,459 | 1.01 |
| `agg_admission_monthly` | agg | str | 2.93 MiB | 2.86 MiB | 71.13 KiB | 2.86 MiB | 1,262 | 10,856 | 1.02 |
| `dim_diagnosis` | dim | str | 1.84 MiB | 1.82 MiB | 18.90 KiB | 1.82 MiB | 20 | 112,107 | 1.01 |
| `dim_patient` | dim | str | 1.70 MiB | 1.68 MiB | 20.24 KiB | 1.68 MiB | 20 | 364,627 | 1.01 |
| `agg_icu_fluid_balance_daily` | agg | str | 1.41 MiB | 1.39 MiB | 26.09 KiB | 1.39 MiB | 64 | 75,366 | 1.02 |
| `dim_procedure` | dim | str | 1.24 MiB | 1.22 MiB | 19.03 KiB | 1.22 MiB | 20 | 86,423 | 1.02 |
| `agg_admission_daily` | agg | str | 902.25 KiB | 878.14 KiB | 24.10 KiB | 878.14 KiB | 64 | 244,500 | 1.03 |
| `dim_hcpcs` | dim | str | 598.67 KiB | 578.95 KiB | 19.72 KiB | 578.95 KiB | 20 | 89,208 | 1.03 |
| `dim_date` | dim | str | 442.23 KiB | 416.26 KiB | 25.97 KiB | 416.26 KiB | 1 | 47,846 | 1.06 |
| `dim_chart_item` | dim | str | 243.66 KiB | 221.82 KiB | 21.84 KiB | 221.82 KiB | 20 | 4,095 | 1.1 |
| `dim_provider` | dim | str | 156.69 KiB | 139.81 KiB | 16.88 KiB | 139.81 KiB | 1 | 42,245 | 1.12 |
| `etl_control` | control | str | 130.29 KiB | 8.00 KiB | 122.29 KiB | 8.00 KiB | 7 | 7 | 16.29 |
| `dim_lab_item` | dim | str | 94.53 KiB | 75.21 KiB | 19.31 KiB | 75.21 KiB | 20 | 1,650 | 1.26 |
| `dim_caregiver` | dim | str | 38.85 KiB | 21.96 KiB | 16.88 KiB | 21.96 KiB | 1 | 17,985 | 1.77 |

## AI-inference layer  (P4: structured queries joined to AI inference outputs)

Tables: `fact_discharge_note_nlp`, `fact_radiology_note_nlp`, `fact_radiology_note_nlp_v`

- Physical: **329.27 MiB**  ·  live snapshot: **68.53 MiB**
- **19.3627%** of the Gold layer  ·  **2.1903%** of the raw bucket  ·  **1.9062%** of the total lakehouse

**Marginal storage cost of the P4 capability ≈ 0.** An AI-inference output is a new small Iceberg table in the existing catalog (`mimic4_db_business_full`) and the existing bucket — no new store, no new format, no partitioning. It is joined to `fact_admission` in place.

**Redundancy ratio for the AI-inference layer = 1.0** (one physical copy). In a decoupled architecture the same output is materialized in the model/NLP store *and* copied into the warehouse to become joinable — redundancy ≥ 2.0 plus an ongoing sync. The bytes are tiny either way; the property is structural, and is what makes P4's "no ETL detour" true. This is the native side of P3's redundancy-ratio measurement.

## Methodology

- **Physical bytes** — `s3:ListObjectsV2` over each bucket, summed. Current object versions only; noncurrent versions (if bucket versioning is on) are not counted.
- **Live-snapshot bytes** — `SELECT count(*), sum(file_size_in_bytes), sum(record_count) FROM "<db>"."<table>$files"` per Gold table (Iceberg metadata table; scans no data).
- **Data vs Iceberg metadata** — a Gold object is "metadata" iff its key is `<prefix>/<table>/metadata/...`, else "data".
- **AI-inference layer** — the tables `fact_discharge_note_nlp`, `fact_radiology_note_nlp`, `fact_radiology_note_nlp_v`.
- **Logical / compacted size** is *not* measured here — obtain it by running `OPTIMIZE <table> REWRITE DATA` + `VACUUM` (or Spark `rewrite_data_files` + `expire_snapshots`) and re-running this script; the drop is the accumulated bloat.

## Caveats before using this for a P3 redundancy ratio

The Gold layer's *physical* footprint is inflated over its logical content by (1) un-expired Iceberg snapshots (physical ≈ 2–3× live) and (2) small-file fragmentation from partitioned writes on a demo-sized dataset. Compact and expire snapshots first, or the ratio measures ETL hygiene rather than architecture. The AI/NLP tables are effectively exempt (unpartitioned, few re-runs).

The Aurora baseline used above is `C:\MIMICIV\gitmimic\mimic_lakehouse_repo\docs\storage_footprint\aurora_baseline.json` — regenerate it from `mimic_datawarehouse_repo` and re-run with `--aurora-baseline <file>` to refresh the comparison.

## Reproduce

```
python measure_storage_footprint.py --dataset fulldataset --region us-east-2
```

_Machine-readable companion: `storage_footprint_20260922T093828Z.json`_
