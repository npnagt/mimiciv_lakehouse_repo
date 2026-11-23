# Iceberg vs Parquet vs CSV table-format storage -- comparison

- **Generated:** 2026-09-27T11:36:53.475819+00:00  ·  dataset `fulldataset`
- **Source measurement:** `C:\MIMICIV\gitmimic\mimic_lakehouse_repo\docs\parquet_comparison\full\latest.json` (generated 2026-09-27T11:36:53.305035+00:00)
- Supports the research question: how does storage taken by Iceberg compare to storage taken by plain Parquet / plain CSV table format for the Multimodal Fusion Schema.

## Per-archetype storage

| Archetype | Iceberg table | Iceberg physical (raw) | Iceberg physical (excl. orphans, est.) | Parquet table | Parquet physical | CSV table | CSV physical |
|---|---|--:|--:|---|--:|---|--:|
| Source Data Fact | `fact_admission` | 26.40 MiB | 26.40 MiB | `fact_admission_parquet` | 32.30 MiB | `fact_admission_csv` | 164.67 MiB |
| Computed Structured Fact | `obt_admission_features` | 37.57 MiB | 37.57 MiB | `obt_admission_features_parquet` | 30.59 MiB | `obt_admission_features_csv` | 151.78 MiB |
| Unstructured Data Fact | `fact_discharge_note` | 1.03 GiB | 1.03 GiB | `fact_discharge_note_parquet` | 1.85 GiB | `fact_discharge_note_csv` | 3.49 GiB |
| Unstructured Data Fact | `fact_radiology_note` | 323.75 MiB | 323.75 MiB | `fact_radiology_note_parquet` | 604.54 MiB | `fact_radiology_note_csv` | 1.32 GiB |
| Unstructured Features Fact | `fact_discharge_note_nlp` | 17.61 MiB | 17.61 MiB | `fact_discharge_note_nlp_parquet` | 5.26 MiB | `fact_discharge_note_nlp_csv` | 8.12 MiB |
| Unstructured Features Fact | `fact_radiology_note_nlp` | 68.81 MiB | 68.81 MiB | `fact_radiology_note_nlp_parquet` | 17.07 MiB | `fact_radiology_note_nlp_csv` | 23.83 MiB |
| Inference Fact | `fact_radiology_note_nlp_v` | 3.48 MiB | n/a | `fact_radiology_note_nlp_v_parquet` | 9.04 MiB | `fact_radiology_note_nlp_v_csv` | 22.81 MiB |

## Per-archetype ratios

| Archetype | Ratio Ice(excl.)/Parquet | Ratio Ice(excl.)/CSV | Ratio Parquet/CSV | Bytes/row Ice(excl.) | Bytes/row Parquet | Bytes/row CSV |
|---|--:|--:|--:|--:|--:|--:|
| Source Data Fact | 0.817x | 0.16x | 0.196x | 50 B | 62 B | 316 B |
| Computed Structured Fact | 1.228x | 0.248x | 0.202x | 72 B | 58 B | 291 B |
| Unstructured Data Fact | 0.557x | 0.295x | 0.53x | 3.26 KiB | 5.86 KiB | 11.04 KiB |
| Unstructured Data Fact | 0.536x | 0.239x | 0.447x | 1.07 KiB | 2.00 KiB | 4.47 KiB |
| Unstructured Features Fact | 3.347x | 2.169x | 0.648x | 1.80 KiB | 551 B | 851 B |
| Unstructured Features Fact | 4.032x | 2.887x | 0.716x | 25.99 KiB | 6.45 KiB | 9.00 KiB |
| Inference Fact | n/a | n/a | 0.396x | n/a | 3.41 KiB | 8.61 KiB |

**"Excl. orphans, est."** = live-snapshot data bytes (from `"<table>$files"`, i.e. exactly what the current Iceberg snapshot references) plus the table's current physical metadata bytes. Since compact_gold_tables.py's VACUUM already ran and collapsed each table down to one live snapshot, any physical byte outside this set is -- by construction -- unreferenced by that snapshot, i.e. exactly what `system.remove_orphan_files` would delete once Iceberg's 24-hour safety floor on that operation has passed (see remove_orphan_files.py). This is an estimate computed from already-collected facts, not a measurement of files actually removed, and slightly overstates the true post-cleanup size if any current metadata bytes are themselves orphaned rather than part of the live snapshot's own manifest chain.

- **`fact_radiology_note_nlp_v`:** Iceberg side is VARIANT-typed (format-v3); Parquet/CSV sides are the same columns flattened to STRING (neither format has a VARIANT type) -- not a same-type comparison for this row.

## Summary

- Comparable rows (an Iceberg instance exists to compare against): **7** of 7
- Total Iceberg physical, raw (comparable rows): **1.50 GiB**
- Total Iceberg physical, excl. orphans (est.): **1.49 GiB**  (estimated orphaned bytes pending cleanup: 0 B)
- Total Iceberg live snapshot (comparable rows): **1.48 GiB**
- Total Parquet physical (comparable rows): **2.54 GiB**
- Total CSV physical (comparable rows): **5.18 GiB**
- Overall ratio, raw physical (Iceberg / Parquet): 0.591x -- inflated by orphaned pre-compaction files `remove_orphan_files` hasn't reclaimed yet
- **Overall ratio, excl. orphans / est. post-cleanup (Iceberg / Parquet): 0.59x** -- the number to use until remove_orphan_files actually runs (24h after compaction, see remove_orphan_files.py)
- Overall ratio, live snapshot data only, no metadata (Iceberg / Parquet): 0.583x
- **Overall ratio, excl. orphans / est. post-cleanup (Iceberg / CSV): 0.289x**
- Overall ratio (Parquet / CSV): 0.49x -- the direct binary-columnar vs. text-row format comparison, independent of Iceberg's own metadata overhead

Read the per-archetype tables above before quoting an overall ratio alone: the Inference Fact row compares Iceberg VARIANT against Parquet/CSV STRING (not the same column type on every side -- neither format has a VARIANT type), and every CSV/Parquet column is string-encoded end to end (see mimic_iv_ddl_csv_comparison.sql design decision 1), so a per-column byte comparison across formats would conflate the format difference with the encoding difference -- only the table-level totals above are directly comparable.

## Reproduce

```
python measure_parquet_comparison.py --dataset fulldataset
python compare_parquet_iceberg.py --dataset fulldataset
```
