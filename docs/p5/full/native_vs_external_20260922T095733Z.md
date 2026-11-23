# P5 -- native in-lake join vs externalized two-stage

- **Generated:** 2026-09-22T09:57:33.723993+00:00  ·  200 repeats (first discarded)
- **Benchmarks:** 2 -- lab, radiology

## Benchmark: lab  (structured)

fact_lab_result x dim_lab_item x fact_admission -> abnormal-rate agg  ·  1,547,679 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **3,038 ms** (±823) | 509,445 rows/s | $0.00004 | scans 9,354 KiB at $5/TiB |
| **External** — export + DuckDB join | 10,041 ms (export 9,979 + join 62) | 154,132 rows/s | $0.00004+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 62 ms (±3) | 24,764,942 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

## Benchmark: radiology  (cross-modal (structured + NLP-derived JSON))

fact_radiology_note_nlp (disorders, JSON UNNEST) x fact_admission -> non-negated disorder mentions by admission type  ·  548,560 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **1,963 ms** (±682) | 279,486 rows/s | $0.00001 | scans 2,531 KiB at $5/TiB |
| **External** — export + DuckDB join | 5,536 ms (export 5,507 + join 29) | 99,084 rows/s | $0.00001+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 29 ms (±2) | 18,697,097 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

## Summary across benchmarks

| Benchmark | Modality | Native median | External median | Ratio | Acceptance |
|---|---|--:|--:|--:|:--:|
| lab | structured | 3,038 ms | 10,041 ms | 3.3x | PASS |
| radiology | cross-modal (structured + NLP-derived JSON) | 1,963 ms | 5,536 ms | 2.8x | PASS |

The external arm's cost is the *extract hop* — the Athena scan to pull the tables out, including (for the radiology benchmark) reconstructing the same JSON-array-to-rows unnesting in DuckDB that Athena performs natively — plus, on a real deployment, the instance-hours of whatever box runs the second stage. DuckDB's join/unnest itself is fast once the data is local; the two-stage penalty is the extract-and-reload, not the processing engine, for either a plain structured join or a cross-modal JSON-bearing one.

