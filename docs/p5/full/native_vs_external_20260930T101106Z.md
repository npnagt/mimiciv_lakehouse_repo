# P5 -- native in-lake join vs externalized two-stage

- **Generated:** 2026-09-30T10:11:06.111445+00:00  ·  200 repeats (first discarded)
- **Benchmarks:** 2 -- lab, radiology

## Benchmark: lab  (structured)

fact_lab_result x dim_lab_item x fact_admission -> abnormal-rate agg  ·  1,547,679 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **3,003 ms** (±880) | 515,353 rows/s | $0.00004 | scans 9,354 KiB at $5/TiB |
| **External** — export + DuckDB join | 9,716 ms (export 9,653 + join 62) | 159,300 rows/s | $0.00004+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 62 ms (±3) | 24,795,023 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

## Benchmark: radiology  (cross-modal (structured + NLP-derived JSON))

fact_radiology_note_nlp (disorders, JSON UNNEST) x fact_admission -> non-negated disorder mentions by admission type  ·  548,560 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **1,602 ms** (±545) | 342,414 rows/s | $0.00001 | scans 2,114 KiB at $5/TiB |
| **External** — export + DuckDB join | 3,804 ms (export 3,765 + join 38) | 144,224 rows/s | $0.00001+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 38 ms (±2) | 14,267,547 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

## Summary across benchmarks

| Benchmark | Modality | Native median | External median | Ratio | Acceptance |
|---|---|--:|--:|--:|:--:|
| lab | structured | 3,003 ms | 9,716 ms | 3.2x | PASS |
| radiology | cross-modal (structured + NLP-derived JSON) | 1,602 ms | 3,804 ms | 2.4x | PASS |

The external arm's cost is the *extract hop* — the Athena scan to pull the tables out, including (for the radiology benchmark) reconstructing the same JSON-array-to-rows unnesting in DuckDB that Athena performs natively — plus, on a real deployment, the instance-hours of whatever box runs the second stage. DuckDB's join/unnest itself is fast once the data is local; the two-stage penalty is the extract-and-reload, not the processing engine, for either a plain structured join or a cross-modal JSON-bearing one.

