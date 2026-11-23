# P5 -- native in-lake join vs externalized two-stage

- **Generated:** 2026-09-21T23:45:25.717732+00:00  ·  3 repeats (first discarded)
- **Benchmarks:** 1 -- radiology

## Benchmark: radiology  (cross-modal (structured + NLP-derived JSON))

fact_radiology_note_nlp (disorders, JSON UNNEST) x fact_admission -> non-negated disorder mentions by admission type  ·  548,560 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **3,423 ms** (±740) | 160,236 rows/s | $0.00001 | scans 2,531 KiB at $5/TiB |
| **External** — export + DuckDB join | 6,637 ms (export 6,608 + join 28) | 82,656 rows/s | $0.00001+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 28 ms (±2) | 19,298,843 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

