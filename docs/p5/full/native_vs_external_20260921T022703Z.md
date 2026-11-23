# P5 -- native in-lake join vs externalized two-stage

- **Generated:** 2026-09-21T02:27:03.640458+00:00  ·  200 repeats (first discarded)
- **Benchmark:** fact_lab_result x dim_lab_item x fact_admission -> abnormal-rate agg  ·  1,547,679 input rows

| Arm | Wall (median) | Throughput | $ cost | Notes |
|---|--:|--:|--:|---|
| **Native** — one Athena query over Iceberg | **3,073 ms** (±990) | 503,573 rows/s | $0.00004 | scans 9,354 KiB at $5/TiB |
| **External** — export + DuckDB join | 11,704 ms (export 11,642 + join 62) | 132,241 rows/s | $0.00004+ | DuckDB runs on the local machine; on a dedicated EC2/EMR box add its instance-hour cost. |
| External — DuckDB join **alone** | 62 ms (±2) | 24,992,632 rows/s | ~$0 | the compute step once the data is already extracted |

**Acceptance (native wall < external mean + 1 SD): PASS.**

The external arm's cost is the *extract hop* — the Athena scan to pull the tables out — plus, on a real deployment, the instance-hours of whatever box runs the second stage. DuckDB's join itself is fast once the data is local; the two-stage penalty is the extract-and-reload, not the processing engine.

