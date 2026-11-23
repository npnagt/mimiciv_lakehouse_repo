# Time-to-insight (P6) -- unified Gold-schema BI layer

- **Generated:** 2026-10-01T07:44:04.299342+00:00
- **Layer under test:** Athena over the Glue Data Catalog (`mimic4_db_business_full`), workgroup `mimic4-lakehouse`, us-east-2
- **time_to_insight** = TotalExecutionTimeInMillis + client result fetch + 500 ms render allowance
- **Repeats:** 200 per query, first discarded; median / p90 / max of the rest
- **Nielsen bands:** A < 1000 ms (flow) · B 1000-10000 ms (sustained attention) · C >= 10000 ms (attention lost)
- **P6 acceptance test:** results land in A or B, i.e. <= 10 s (sustained attention or faster), not C (>10 s, attention lost). Standalone test of the lakehouse's unified BI layer -- **no baseline comparison** is part of this proposition.

## Result (cold pass -- result reuse OFF, the honest number for a novel question)

| Metric | Value |
|---|--:|
| **P6 acceptance test** | **PASS** |
| Queries scored | 19 |
| Band A -- flow (< 1 s) | **0** |
| Band B -- sustained attention (1-10 s) | **19** |
| Band C -- attention lost (>= 10 s) | **0** |
| Within sustained-attention band or faster (A or B, <=10 s) | **100.0%** |
| Within flow band (A) | 0.0% |
| Overall p90 | 2104 ms |
| Athena fixed floor (`SELECT 1`) | 901 ms |

Slowest three: `T5b` LOS by note-derived obesity_level (structured x NLP) (2306 ms); `T2b` Abnormal-lab burden per admission type (raw join) (2232 ms); `T4a` Patient-360 cohort filter + rollup (pre-joined OBT) (2104 ms).

## Cold pass -- per query

| id | tier | insight | band | tti median | p90 | queue | plan | engine | fetch | scanned | rows |
|---|---|---|:--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `floor` | T0 (Athena floor) | Athena fixed floor (no table) | **A** | 901 ms | 952 | 0 | 0 | 175 | 117 | 0 B | 1 |
| `T1a` | T1 (structured, single table) | Admission volume trend by month | **B** | 1849 ms | 2818 | 0 | 203 | 1012 | 139 | 90.8 KiB | 999 |
| `T1b` | T1 (structured, single table) | Case mix by admission type | **B** | 1381 ms | 2363 | 0 | 69 | 575 | 118 | 179.8 KiB | 10 |
| `T2a` | T2 (structured join) | 30-day readmission rate by DRG severity (raw join) | **B** | 1911 ms | 2806 | 0 | 142 | 1107 | 119 | 4.8 MiB | 4 |
| `T2b` | T2 (structured join) | Abnormal-lab burden per admission type (raw join) | **B** | 2232 ms | 3297 | 0 | 139 | 1417 | 118 | 3.4 MiB | 9 |
| `T3a` | T3 (event-fact aggregation) | Abnormal vs normal lab counts (108k-row scan) | **B** | 1699 ms | 2260 | 0 | 67 | 884 | 118 | 231.3 KiB | 3 |
| `T3b` | T3 (event-fact aggregation) | Medication-administration volume + reach (36k-row scan) | **B** | 1419 ms | 2080 | 0 | 71 | 618 | 118 | 2.0 MiB | 1 |
| `T3c` | T3 (event-fact aggregation) | Positive blood-culture rate by month | **B** | 1599 ms | 2463 | 0 | 82 | 770 | 146 | 2.7 MiB | 999 |
| `T4a` | T4 (wide pre-joined OBT) | Patient-360 cohort filter + rollup (pre-joined OBT) | **B** | 2104 ms | 3160 | 0 | 303 | 1297 | 122 | 984.2 KiB | 4 |
| `T4b` | T4 (wide pre-joined OBT) | Readmission by DRG severity (via OBT -- compare to T2a) | **B** | 1971 ms | 2800 | 0 | 279 | 1160 | 120 | 420.5 KiB | 4 |
| `T4c` | T4 (wide pre-joined OBT) | ICU stay features summary (pre-joined OBT) | **B** | 1862 ms | 3222 | 0 | 215 | 1051 | 119 | 1.1 MiB | 17 |
| `T5a` | T5 (structured x NLP) | 30-day readmission by discharge-note tobacco_use (structured x NLP) | **B** | 1982 ms | 2896 | 0 | 279 | 1182 | 120 | 3.7 MiB | 4 |
| `T5b` | T5 (structured x NLP) | LOS by note-derived obesity_level (structured x NLP) | **B** | 2306 ms | 3354 | 0 | 443 | 1497 | 120 | 3.5 MiB | 3 |
| `T5c` | T5 (structured x NLP) | SDOH burden cross-tab (structured x NLP) | **B** | 1880 ms | 2774 | 0 | 264 | 1075 | 121 | 1.8 MiB | 16 |
| `T6a` | T6 (cross-modal JSON) | Radiology-reported disorders, ranked (cross-modal JSON UNNEST) | **B** | 1604 ms | 2720 | 0 | 177 | 788 | 121 | 171.0 KiB | 25 |
| `T6b` | T6 (cross-modal JSON) | Imaging modality mix per admission (cross-modal JSON x structured) | **B** | 1890 ms | 2819 | 0 | 240 | 1076 | 121 | 2.0 MiB | 7 |
| `T6c` | T6 (cross-modal JSON) | Radiology ICD codes vs coded diagnoses (cross-modal concordance) | **B** | 2027 ms | 2976 | 0 | 250 | 1195 | 123 | 3.8 MiB | 25 |
| `T7a` | T7 (big event-fact scan) | Chart-observation volume + reach (669k-row scan) | **B** | 1529 ms | 2546 | 0 | 75 | 710 | 123 | 1.1 MiB | 1 |
| `T7b` | T7 (big event-fact scan) | Charted-value abnormality rate by month (669k-row scan + group) | **B** | 1500 ms | 2179 | 0 | 83 | 673 | 128 | 855.8 KiB | 191 |
| `T7c` | T7 (big event-fact scan) | Instability proxy: non-null numeric vitals per ICU stay (669k-row scan) | **B** | 1485 ms | 2184 | 0 | 82 | 672 | 122 | 1.1 MiB | 25 |

## Warm pass -- per query

| id | tier | insight | band | tti median | p90 | queue | plan | engine | fetch | scanned | rows |
|---|---|---|:--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `floor` | T0 (Athena floor) | Athena fixed floor (no table) | **A** | 908 ms | 967 | 0 | 0 | 178 | 120 | 0 B | 1 |
| `T1a` | T1 (structured, single table) | Admission volume trend by month | **A** | 843 ms | 893 | 0 | 0 | 82 | 144 | 0 B | 999  ↺ |
| `T1b` | T1 (structured, single table) | Case mix by admission type | **A** | 822 ms | 857 | 0 | 0 | 82 | 121 | 0 B | 10  ↺ |
| `T2a` | T2 (structured join) | 30-day readmission rate by DRG severity (raw join) | **A** | 823 ms | 869 | 0 | 0 | 87 | 122 | 0 B | 4  ↺ |
| `T2b` | T2 (structured join) | Abnormal-lab burden per admission type (raw join) | **A** | 830 ms | 879 | 0 | 0 | 89 | 123 | 0 B | 9  ↺ |
| `T3a` | T3 (event-fact aggregation) | Abnormal vs normal lab counts (108k-row scan) | **A** | 818 ms | 854 | 0 | 0 | 80 | 122 | 0 B | 3  ↺ |
| `T3b` | T3 (event-fact aggregation) | Medication-administration volume + reach (36k-row scan) | **A** | 817 ms | 861 | 0 | 0 | 80 | 118 | 0 B | 1  ↺ |
| `T3c` | T3 (event-fact aggregation) | Positive blood-culture rate by month | **A** | 842 ms | 878 | 0 | 0 | 79 | 146 | 0 B | 999  ↺ |
| `T4a` | T4 (wide pre-joined OBT) | Patient-360 cohort filter + rollup (pre-joined OBT) | **A** | 818 ms | 850 | 0 | 0 | 83 | 117 | 0 B | 4  ↺ |
| `T4b` | T4 (wide pre-joined OBT) | Readmission by DRG severity (via OBT -- compare to T2a) | **A** | 815 ms | 860 | 0 | 0 | 83 | 116 | 0 B | 4  ↺ |
| `T4c` | T4 (wide pre-joined OBT) | ICU stay features summary (pre-joined OBT) | **A** | 820 ms | 857 | 0 | 0 | 84 | 118 | 0 B | 17  ↺ |
| `T5a` | T5 (structured x NLP) | 30-day readmission by discharge-note tobacco_use (structured x NLP) | **A** | 823 ms | 859 | 0 | 0 | 88 | 116 | 0 B | 4  ↺ |
| `T5b` | T5 (structured x NLP) | LOS by note-derived obesity_level (structured x NLP) | **A** | 824 ms | 872 | 0 | 0 | 91 | 116 | 0 B | 3  ↺ |
| `T5c` | T5 (structured x NLP) | SDOH burden cross-tab (structured x NLP) | **A** | 821 ms | 854 | 0 | 0 | 87 | 118 | 0 B | 16  ↺ |
| `T6a` | T6 (cross-modal JSON) | Radiology-reported disorders, ranked (cross-modal JSON UNNEST) | **A** | 821 ms | 860 | 0 | 0 | 86 | 117 | 0 B | 25  ↺ |
| `T6b` | T6 (cross-modal JSON) | Imaging modality mix per admission (cross-modal JSON x structured) | **A** | 823 ms | 865 | 0 | 0 | 89 | 117 | 0 B | 7  ↺ |
| `T6c` | T6 (cross-modal JSON) | Radiology ICD codes vs coded diagnoses (cross-modal concordance) | **A** | 823 ms | 864 | 0 | 0 | 89 | 117 | 0 B | 25  ↺ |
| `T7a` | T7 (big event-fact scan) | Chart-observation volume + reach (669k-row scan) | **A** | 811 ms | 855 | 0 | 0 | 82 | 116 | 0 B | 1  ↺ |
| `T7b` | T7 (big event-fact scan) | Charted-value abnormality rate by month (669k-row scan + group) | **A** | 818 ms | 853 | 0 | 0 | 82 | 124 | 0 B | 191  ↺ |
| `T7c` | T7 (big event-fact scan) | Instability proxy: non-null numeric vitals per ICU stay (669k-row scan) | **A** | 819 ms | 866 | 0 | 0 | 82 | 119 | 0 B | 25  ↺ |

## Method & caveats

- **Cold vs warm.** The cold pass sets `ResultReuseByAgeConfiguration.Enabled=false` so every run recomputes -- this is what a genuinely novel ad-hoc question costs. The warm pass turns reuse on; an identical repeat then returns from cache (marked ↺) in well under a second.
- **Athena floor.** `SELECT 1` measures unavoidable queue + planning + service overhead. Simple queries land in band B largely because of this floor, not the data volume.
- **Render allowance.** A fixed 500 ms stands in for BI-tool render of a small (<= a few hundred row) aggregate; real chart libraries draw that in 10-50 ms, so 500 ms is conservative and covers tool/network overhead. Swap in a measured number if a BI tool is instrumented.
- **Multi-tenancy.** Athena execution time varies 2-3x with cluster load; run this battery at 3 different times and compare the distributions.
- **Compaction state.** Small-file fragmentation (many small Parquet files per partition, before an `OPTIMIZE ... REWRITE DATA USING BIN_PACK` pass) adds scan latency independent of row count -- these numbers are only comparable to another run against a Gold layer in the same compaction state. Check `docs/storage_footprint/<demo|full>/latest.md`, generated against the same `fulldataset` dataset, for the physical file count/layout this run's numbers were measured against; re-run against a freshly compacted vs. un-compacted table to quantify the tax directly.
- **No baseline comparison.** P6 is a standalone threshold test of this repo's unified BI layer against the fixed 10 s Nielsen sustained-attention bound -- it does not claim or require that a decoupled warehouse is slower. (For context only, `mimic_datawarehouse_repo` ships its own `scripts/measure_time_to_insight_pg.py`, kept as a separate, non-P6 supplementary tool since T5-T7's NLP-derived tiers have no equivalent there at all.)

## Reproduce

```
python measure_time_to_insight.py                      # cold + warm, 200 repeats
python measure_time_to_insight.py --only T5,T6 --repeats 8   # quick exploratory check
```

