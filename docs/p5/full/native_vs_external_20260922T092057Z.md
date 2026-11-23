# P5 -- native in-lake join vs externalized two-stage

- **Generated:** 2026-09-22T09:20:57.804120+00:00  ·  3 repeats (first discarded)
- **Benchmarks:** 1 -- lab

## Benchmark: lab  (structured)

fact_lab_result x dim_lab_item x fact_admission -> abnormal-rate agg  ·  1,547,679 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **3,572 ms** (±180) | 433,318 rows/s | $0.00004 | scans 9,354 KiB at $5/TiB |
| **External** — export + DuckDB join | 10,386 ms (export 10,317 + join 70) | 149,010 rows/s | $0.00004+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 70 ms (±0) | 22,284,406 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

