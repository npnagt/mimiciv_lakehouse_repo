# Iceberg vs Parquet vs CSV table-format storage -- raw measurement

- **Generated:** 2026-09-27T12:41:11.522352+00:00  ·  region `us-east-2`  ·  dataset `fulldataset`
- Raw per-table facts only -- see the companion compare_parquet_iceberg.py report for ratios and findings.

| Archetype | Iceberg table | Iceberg physical | Iceberg live | Iceberg rows | Parquet table | Parquet physical | Parquet rows | CSV table | CSV physical | CSV rows | Note |
|---|---|--:|--:|--:|---|--:|--:|---|--:|--:|---|
| Source Data Fact | `fact_admission` | 26.40 MiB | 26.37 MiB | 546,029 | `fact_admission_parquet` | 25.60 MiB | 546,029 | `fact_admission_csv` | 32.05 MiB | 546,029 |  |
| Computed Structured Fact | `obt_admission_features` | 37.57 MiB | 37.01 MiB | 546,031 | `obt_admission_features_parquet` | 23.95 MiB | 546,031 | `obt_admission_features_csv` | 27.37 MiB | 546,031 |  |
| Unstructured Data Fact | `fact_discharge_note` | 1.03 GiB | 1.03 GiB | 331,793 | `fact_discharge_note_parquet` | 1.03 GiB | 331,793 | `fact_discharge_note_csv` | 1.20 GiB | 331,793 |  |
| Unstructured Data Fact | `fact_radiology_note` | 323.75 MiB | 323.73 MiB | 309,670 | `fact_radiology_note_parquet` | 322.85 MiB | 309,670 | `fact_radiology_note_csv` | 376.80 MiB | 309,670 |  |
| Unstructured Features Fact | `fact_discharge_note_nlp` | 17.61 MiB | 14.11 MiB | 10,000 | `fact_discharge_note_nlp_parquet` | 4.76 MiB | 10,000 | `fact_discharge_note_nlp_csv` | 1.56 MiB | 10,000 |  |
| Unstructured Features Fact | `fact_radiology_note_nlp` | 68.81 MiB | 57.11 MiB | 2,711 | `fact_radiology_note_nlp_parquet` | 14.76 MiB | 2,711 | `fact_radiology_note_nlp_csv` | 3.86 MiB | 2,711 |  |
| Inference Fact | `fact_radiology_note_nlp_v` | 3.48 MiB | n/a | n/a | `fact_radiology_note_nlp_v_parquet` | 3.54 MiB | 2,711 | `fact_radiology_note_nlp_v_csv` | 3.36 MiB | 2,711 | Iceberg side is VARIANT-typed (format-v3); Parquet/CSV sides are the same columns flattened to STRING (neither format has a VARIANT type) -- not a same-type comparison for this row. |

## Reproduce

```
python measure_parquet_comparison.py --dataset fulldataset --region us-east-2
```

_Machine-readable companion: `parquet_comparison_measurement_20260927T124111Z.json`. Next: `python compare_parquet_iceberg.py --dataset fulldataset` to render the interpreted comparison._
