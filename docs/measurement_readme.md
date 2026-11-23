# Measurement & comparison runbook

Commands to (re-)generate every P1–P7 measurement artifact — lakehouse storage/cost/
query-latency, warehouse storage/cost/query-latency, and the merged side-by-side
comparison — against a given `--dataset`, after a pipeline run has populated that
dataset's tables on both sides.

## Prerequisites

- `mimic_lakehouse_repo` pipeline has run for the target `--dataset` (`run_lakehouse_pipeline.py`).
- `mimic_datawarehouse_repo` pipeline has run for the same `--dataset` (`scripts/run_end_to_end.py`).
- Both repos' virtualenvs exist (`.venv/`) with `pip install -e .` done.
- AWS credentials configured (`aws configure`) with access to both repos' resources.
- Run from Git Bash (uses `$()`, `tee`).

## Recommended: one command

`run_measurement_suite.py` runs every step below in the right order, streams each
step's output live, and saves it to `logs/<job_name>_<local-timestamp>.log` in
whichever repo the step ran from -- the same per-job log naming as the manual
sequence further down. Before running anything it checks that no Glue job for this
`--dataset` is currently `RUNNING`/`STARTING`/`WAITING` on either side, so it can't
repeat the 2026-09-20 incident (see Notes) where the suite was run mid-`--fresh-reload`
and captured a half-loaded Gold layer.

```bash
cd /c/MIMICIV/gitmimic/mimic_lakehouse_repo
./.venv/Scripts/python.exe run_measurement_suite.py --dataset fulldataset
```

- `--only storage,tti` — run a subset (keys: `storage`, `join`, `tti`, `lh_cost_by_run`,
  `lh_cost_snapshot`, `wh_size`, `wh_cost_by_run`, `wh_cost_snapshot`,
  `compare_by_run`, `compare`).
- `--stop-on-failure` — abort on the first failed step (default: run every step
  regardless and print a pass/fail summary at the end; `compare_environments.py`
  degrades gracefully when an earlier step's output is missing).
- `--force` — skip the pre-flight running-pipeline check.
- `--last-n` / `--repeats` — passed through to the `--by-run` / tti / join steps.
  **`tti` and `join` now default to 200 repetitions** (confirmatory, matching the
  pre-registered power analysis) rather than a quick check — `tti` at 200 reps x 19
  queries x 2 passes has taken upward of 8 hours in practice; `join` is minutes, since it
  has no per-repetition pipeline cost. Pass `--repeats 5` (tti) or `--repeats 12` (join)
  for a fast exploratory pass instead.
- `--lh-since` / `--wh-since` — exclude full_run_ids that started before a cutoff timestamp,
  applied before `--last-n` (so you get the last N runs *after* the cutoff). Use this after
  fixing a bug that was inflating run duration/cost, so the old buggy runs don't pollute the
  comparison:

  ```bash
  ./.venv/Scripts/python.exe run_measurement_suite.py --dataset fulldataset \
      --only lh_cost_by_run,wh_cost_by_run,compare_by_run --last-n 5 \
      --lh-since "2026-09-20 02:21:50.915000" --wh-since "2026-09-19 17:41:02.235776"
  ```

The manual, step-by-step commands below do the same thing without the pre-flight
check or the single-command convenience -- useful for re-running one step in
isolation, or debugging a failure with output going only to your terminal.

## What each script supports

| Script | Repo | Proposition(s) | Writes to |
|---|---|---|---|
| `measure_storage_footprint.py` | lakehouse | P3, P4 | `docs/storage_footprint/<demo\|full>/` |
| `measure_native_vs_external_join.py` | lakehouse | P5 | `docs/p5/<demo\|full>/` |
| `measure_time_to_insight.py` | lakehouse | P6 (standalone, no baseline) | `docs/tti/<demo\|full>/` |
| `measure_aws_resources.py --by-run` | lakehouse | P1, P2, P4, P7 | `docs/cost/<demo\|full>/runs_<UTC>.{json,md}` |
| `measure_aws_resources.py` | lakehouse | P1–P4 (cost) | `docs/cost/<demo\|full>/latest.json` |
| `scripts/measure_warehouse_size.py` | warehouse | P3, P4 | stdout only — see note below |
| `scripts/measure_aws_resources.py --by-run` | warehouse | P1, P2, P4, P7 | `docs/cost/<demo\|full>/latest_runs.json` |
| `scripts/measure_aws_resources.py` | warehouse | P1–P4 (cost) | `docs/cost/<demo\|full>/latest.json` |
| `compare_environments.py --by-run` | lakehouse | P1–P7 | `docs/comparison/<demo\|full>/latest_by_run_comparison.{json,md}` |
| `compare_environments.py` | lakehouse | P1–P9 scorecard | `docs/comparison/<demo\|full>/latest.{json,md}` |
| `measure_parquet_comparison.py` | lakehouse | paper RQ1 | `docs/parquet_comparison/<demo\|full>/latest.{json,md}` |
| `compare_parquet_iceberg.py` | lakehouse | paper RQ1 | `docs/parquet_comparison/<demo\|full>/latest_comparison.{json,md}` |

`measure_parquet_comparison.py` / `compare_parquet_iceberg.py` are standalone and **not**
run by `run_measurement_suite.py` (they support the paper's RQ1, not a P1–P9 proposition,
and they read the `*_parquet` / `*_parquet_snappy` / `*_csv` comparison tables rather than
anything `run_lakehouse_pipeline.py` loads by default) — run them by hand after applying
`ddl/gold/mimic_iv_ddl_parquet_comparison.sql` / `mimic_iv_ddl_parquet_snappy_comparison.sql`
/ `mimic_iv_ddl_csv_comparison.sql` and their three Glue-6.0 load jobs
(`run_parquet_comparison_load.py`, `run_parquet_snappy_comparison_load.py`,
`run_csv_comparison_load.py`), in that order:

```bash
./.venv/Scripts/python.exe measure_parquet_comparison.py --dataset fulldataset
./.venv/Scripts/python.exe compare_parquet_iceberg.py --dataset fulldataset
```

The paper's RQ2 (query-coverage) result has no corresponding measurement script: it is a
manually-scored catalog, not an AWS-measured metric. See
[docs/query_coverage/README.md](query_coverage/README.md).

`scripts/measure_time_to_insight_pg.py` (warehouse) is **not** in this table: P6
(dissertation Ch.1 Table 2, "Unified abstraction layer supports rendering of results
inside Nielsen's 'sustained attention' band (1–10 s), rather than the >10-second
'attention lost' band") is a standalone threshold test of the lakehouse's own unified BI
layer, with no baseline comparison. That script still exists as an optional,
supplementary tool for context, but it's not run by `run_measurement_suite.py` and not
read by `compare_environments.py`.

Run in the order below: `compare_environments.py` reads the `latest*` files the other
scripts write, so it must run last.

## Commands

Each command displays its output live (`tee`) and also saves it to
`logs/<job_name>_<YYYYMMDD>_<HHMMSS>.log` in whichever repo you're in. Substitute
`--dataset demodataset` throughout for the demo dataset.

```bash
# ===================== 1. LAKEHOUSE measurements =====================
cd /c/MIMICIV/gitmimic/mimic_lakehouse_repo

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe measure_storage_footprint.py --dataset fulldataset \
  2>&1 | tee "logs/measure_storage_footprint_${TS}.log"          # P3

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe measure_native_vs_external_join.py --dataset fulldataset \
  2>&1 | tee "logs/measure_native_vs_external_join_${TS}.log"    # P5

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe measure_time_to_insight.py --dataset fulldataset \
  2>&1 | tee "logs/measure_time_to_insight_${TS}.log"             # P6 (standalone, no baseline)

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe measure_aws_resources.py --dataset fulldataset --by-run --last-n 5 \
  2>&1 | tee "logs/measure_aws_resources_by_run_${TS}.log"        # P1/P2/P4/P7 per-run stats

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe measure_aws_resources.py --dataset fulldataset \
  2>&1 | tee "logs/measure_aws_resources_snapshot_${TS}.log"      # point-in-time cost/annual estimate

# ===================== 2. WAREHOUSE measurements =====================
cd /c/MIMICIV/gitmimic/mimic_datawarehouse_repo

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe scripts/measure_warehouse_size.py --dataset fulldataset --json \
  2>&1 | tee "logs/measure_warehouse_size_${TS}.log"
# NOTE: this only prints JSON -- nothing folds it into
# mimic_lakehouse_repo/docs/storage_footprint/aurora_baseline.json automatically.
# That file is hand-maintained (bytes->MiB conversion + narrative fields); update it manually
# from this run's numbers if you want P3's DW-vs-lakehouse comparison to reflect fulldataset.

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe scripts/measure_aws_resources.py --dataset fulldataset --by-run --last-n 5 \
  2>&1 | tee "logs/measure_aws_resources_by_run_${TS}.log"

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe scripts/measure_aws_resources.py --dataset fulldataset \
  2>&1 | tee "logs/measure_aws_resources_snapshot_${TS}.log"

# ===================== 3. SIDE-BY-SIDE COMPARISON =====================
cd /c/MIMICIV/gitmimic/mimic_lakehouse_repo

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe compare_environments.py --dataset fulldataset --by-run --last-n 5 \
  2>&1 | tee "logs/compare_environments_by_run_${TS}.log"         # resource/cost stats, P1-P7

TS=$(date +%Y%m%d_%H%M%S)
./.venv/Scripts/python.exe compare_environments.py --dataset fulldataset \
  2>&1 | tee "logs/compare_environments_${TS}.log"                # point-in-time proposition scorecard
```

## Notes

- **Aurora baseline is hand-maintained.** `docs/storage_footprint/aurora_baseline.json`
  feeds `measure_storage_footprint.py`'s data-warehouse-vs-lakehouse comparison. No
  script writes it automatically; after running `scripts/measure_warehouse_size.py --json`,
  convert its `categories.structured.{physical_bytes,live_bytes}` (and
  `database_total_bytes`) from bytes to MiB and merge them into that file by hand.
- **P6 has no baseline comparison.** `scripts/measure_time_to_insight_pg.py` (warehouse
  TTI) still exists in the warehouse repo and can be run manually for context, but it's
  intentionally not part of this sequence: P6 is a standalone pass/fail test of the
  lakehouse's own unified BI layer against a fixed 10 s threshold, not a comparison.
- **`compare_environments.py --run`** (not used above) auto-orchestrates all of the
  scripts in one shot instead of running them individually, at the cost of one shared
  log instead of a per-job log per the format used here.
- Order matters: step 3 reads the `latest*.json` files steps 1–2 just wrote.
