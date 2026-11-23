# Iceberg vs Parquet vs CSV table-format storage -- raw measurement

- **Generated:** 2026-09-27T11:36:53.305035+00:00  ·  region `us-east-2`  ·  dataset `fulldataset`
- Raw per-table facts only -- see the companion compare_parquet_iceberg.py report for ratios and findings.

| Archetype | Iceberg table | Iceberg physical | Iceberg live | Iceberg rows | Parquet table | Parquet physical | Parquet rows | CSV table | CSV physical | CSV rows | Note |
|---|---|--:|--:|--:|---|--:|--:|---|--:|--:|---|
| Source Data Fact | `fact_admission` | 26.40 MiB | 26.37 MiB | 546,029 | `fact_admission_parquet` | 32.30 MiB | 546,029 | `fact_admission_csv` | 164.67 MiB | 546,029 |  |
| Computed Structured Fact | `obt_admission_features` | 37.57 MiB | 37.01 MiB | 546,031 | `obt_admission_features_parquet` | 30.59 MiB | 546,031 | `obt_admission_features_csv` | 151.78 MiB | 546,031 |  |
| Unstructured Data Fact | `fact_discharge_note` | 1.03 GiB | 1.03 GiB | 331,793 | `fact_discharge_note_parquet` | 1.85 GiB | 331,793 | `fact_discharge_note_csv` | 3.49 GiB | 331,793 |  |
| Unstructured Data Fact | `fact_radiology_note` | 323.75 MiB | 323.73 MiB | 309,670 | `fact_radiology_note_parquet` | 604.54 MiB | 309,670 | `fact_radiology_note_csv` | 1.32 GiB | 309,670 |  |
| Unstructured Features Fact | `fact_discharge_note_nlp` | 17.61 MiB | 14.11 MiB | 10,000 | `fact_discharge_note_nlp_parquet` | 5.26 MiB | 10,000 | `fact_discharge_note_nlp_csv` | 8.12 MiB | 10,000 |  |
| Unstructured Features Fact | `fact_radiology_note_nlp` | 68.81 MiB | 57.11 MiB | 2,711 | `fact_radiology_note_nlp_parquet` | 17.07 MiB | 2,711 | `fact_radiology_note_nlp_csv` | 23.83 MiB | 2,711 |  |
| Inference Fact | `fact_radiology_note_nlp_v` | 3.48 MiB | n/a | n/a | `fact_radiology_note_nlp_v_parquet` | 9.04 MiB | 2,711 | `fact_radiology_note_nlp_v_csv` | 22.81 MiB | 2,711 | Iceberg side is VARIANT-typed (format-v3); Parquet/CSV sides are the same columns flattened to STRING (neither format has a VARIANT type) -- not a same-type comparison for this row. |

## Reproduce

```
python measure_parquet_comparison.py --dataset fulldataset --region us-east-2
```

_Machine-readable companion: `parquet_comparison_measurement_20260927T113653Z.json`. Next: `python compare_parquet_iceberg.py --dataset fulldataset` to render the interpreted comparison._
