# P5 -- native in-lake join vs externalized two-stage

- **Generated:** 2026-09-22T00:05:51.804071+00:00  ·  200 repeats (first discarded)
- **Benchmarks:** 2 -- lab, radiology

## Benchmark: lab  (structured)

fact_lab_result x dim_lab_item x fact_admission -> abnormal-rate agg  ·  1,547,679 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **3,120 ms** (±761) | 496,100 rows/s | $0.00004 | scans 9,354 KiB at $5/TiB |
| **External** — export + DuckDB join | 12,117 ms (export 12,054 + join 62) | 127,730 rows/s | $0.00004+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 62 ms (±2) | 24,831,350 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

## Benchmark: radiology  (cross-modal (structured + NLP-derived JSON))

fact_radiology_note_nlp (disorders, JSON UNNEST) x fact_admission -> non-negated disorder mentions by admission type  ·  548,560 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **2,000 ms** (±758) | 274,293 rows/s | $0.00001 | scans 2,531 KiB at $5/TiB |
| **External** — export + DuckDB join | 6,735 ms (export 6,701 + join 34) | 81,447 rows/s | $0.00001+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 34 ms (±3) | 16,130,875 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

## Summary across benchmarks

| Benchmark | Modality | Native median | External median | Ratio | Acceptance |
|---|---|--:|--:|--:|:--:|
| lab | structured | 3,120 ms | 12,117 ms | 3.9x | PASS |
| radiology | cross-modal (structured + NLP-derived JSON) | 2,000 ms | 6,735 ms | 3.4x | PASS |

The external arm's cost is the *extract hop* — the Athena scan to pull the tables out, including (for the radiology benchmark) reconstructing the same JSON-array-to-rows unnesting in DuckDB that Athena performs natively — plus, on a real deployment, the instance-hours of whatever box runs the second stage. DuckDB's join/unnest itself is fast once the data is local; the two-stage penalty is the extract-and-reload, not the processing engine, for either a plain structured join or a cross-modal JSON-bearing one.

