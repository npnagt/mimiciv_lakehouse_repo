#!/usr/bin/env python3
"""Inventory + cost estimate for every AWS resource the multimodal lakehouse
pipeline provisions and consumes -- the lakehouse counterpart to the data-
warehouse repo's scripts/measure_aws_resources.py ("Aurora Pipeline Manifest").

Read-only. Pulls exact API values where AWS exposes them (Glue DPU-seconds,
crawler run time, CloudWatch storedBytes, Glue Data Catalog counts, Athena
DataScannedInBytes) and the S3 figures from the most recent
measure_storage_footprint.py run. Applies public us-east-2 on-demand prices
(edit PRICES below) to turn consumption into a cost estimate covering ONE-TIME
build/debug cost, one clean pipeline run, STEADY-STATE monthly cost, and a
combined "load the environment once + run it for a year" projection.

Two modes:

  Point-in-time snapshot (default) -- account-wide resource inventory + cost
  estimate as of right now. Outputs docs/cost/<demo|full>/aws_resources_<UTC>.
  {json,md} + latest.{json,md}.

  --by-run -- per-full_run_id resource/timing detail from
  <gold_database>.etl_process_log instead, restricted to the last --last-n runs,
  plus mean/median/stdev/min/max across them and a current-footprint snapshot
  (storage, CloudWatch, Data Catalog, cost) for context. Outputs
  docs/cost/<demo|full>/runs_<UTC>.{json,md} + latest_runs.{json,md}.

Usage:
    python measure_aws_resources.py [OPTIONS]

Options:
    --dataset {demodataset,fulldataset}
                        Dataset + resource set to use (default: demodataset, or
                        the DATASET env var / .env value). Selects which
                        -demo/-full-suffixed Glue jobs, crawler, IAM roles,
                        buckets, and Glue Data Catalog databases are inventoried.
    --region REGION     AWS region (default: AWS_REGION env var / .env value,
                        else us-east-2).
    --skip-athena       Don't page the account's Athena query-execution history
                        (point-in-time snapshot mode only; that history can be
                        long and slow to page through). No effect with --by-run.
    --out-dir DIR       Output directory (default: docs/cost/<demo|full> for
                        the resolved --dataset).
    --by-run            Report resource usage per full_run_id from
                        <gold_database>.etl_process_log instead of the
                        point-in-time account-wide snapshot -- see "Two modes"
                        above.
    --last-n N          With --by-run: restrict the detailed rows and summary
                        statistics to the most recent N full_run_ids (default:
                        5). Pass 0 for every run found.
    --since TIMESTAMP   With --by-run: exclude any full_run_id that started
                        before this timestamp ('YYYY-MM-DD HH:MM:SS[.ffffff]'
                        or ISO 8601; naive values are treated as UTC, matching
                        etl_process_log.start_ts). Applied before --last-n, so
                        you get the last N runs *after* this cutoff -- e.g. to
                        exclude runs affected by a bug that has since been fixed.

Examples:
    python measure_aws_resources.py                              # demodataset snapshot
    python measure_aws_resources.py --dataset fulldataset         # fulldataset snapshot
    python measure_aws_resources.py --skip-athena                 # snapshot, skip Athena history
    python measure_aws_resources.py --dataset fulldataset --by-run --last-n 5
    python measure_aws_resources.py --dataset fulldataset --by-run --last-n 0  # every run ever
    python measure_aws_resources.py --dataset fulldataset --by-run --last-n 5 \
        --since "2026-09-20 02:21:50.915000"                      # exclude pre-fix runs

Outputs docs/cost/<demo|full>/aws_resources_<UTC>.{json,md} + latest.{json,md}
(snapshot mode), or runs_<UTC>.{json,md} + latest_runs.{json,md} (--by-run).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from mimic_lakehouse import config as _cfg  # noqa: E402


def env(key, default=None):
    return _cfg.get(key, default)

GB = 10 ** 9   # AWS bills storage in decimal GB
TB = 10 ** 12

# ---- public on-demand prices, US East (Ohio) us-east-2, 2026 ----
PRICES = {
    "glue_dpu_hour": 0.44,             # Glue ETL + crawler, per DPU-hour, per-second billing
    "s3_standard_gb_month": 0.023,     # first 50 TB tier
    "s3_put_per_1k": 0.005,
    "s3_get_per_1k": 0.0004,
    "athena_per_tb_scanned": 5.00,
    "cw_logs_ingest_per_gb": 0.50,
    "cw_logs_storage_gb_month": 0.03,
    "glue_catalog_per_100k_objects_month": 1.00,   # after the first 1M objects free
}

# Resources this pipeline owns -- from src/mimic_lakehouse/cleanup.py.
# The dataset-independent *base* names; main() suffixes them per --dataset
# (-demo / -full) and rebinds the module-level names below via _apply_profile().
JOB_PREFIXES = ("dim-load-", "fact-load-", "agg-refresh-")
_JOB_EXACT_BASE = (
    "dim-date-seed-job", "notes-ingest-job",
    "medspacy-nlp-job", "radiology-nlp-job", "radiology-nlp-variant-job",
)
_IAM_ROLES_BASE = (
    "MimicGlueCrawlerRole", "MimicGlueDimDateSeedRole", "MimicGlueDimLoadRole",
    "MimicGlueFactLoadRole", "MimicGlueAggRefreshRole", "MimicGlueNotesIngestRole",
    "MimicGlueMedspacyNlpRole", "MimicGlueRadiologyNlpRole",
)

# Defaults for the demo dataset; _apply_profile() overwrites these in main().
DATASET_SUFFIX = "-demo"
JOB_EXACT = {n + DATASET_SUFFIX for n in _JOB_EXACT_BASE}
CRAWLERS = ("mimic4-data-v3-2-crawler-demo",)
IAM_ROLES = tuple(n + DATASET_SUFFIX for n in _IAM_ROLES_BASE)
BUCKETS = ("mimic4-datalake-v3-2-demo", "mimic4-lakehouse-v3-2-demo",
           "mimic4-glue-scripts-v3-2-bucket", "mimic4-nlp-v3-2-demo")
GLUE_LOG_GROUPS = (
    "/aws-glue/jobs/error", "/aws-glue/jobs/logs-v2", "/aws-glue/jobs/output",
    "/aws-glue/python-jobs/error", "/aws-glue/python-jobs/output",
    "/aws-glue/sessions/error", "/aws-glue/sessions/output",
    "/aws-glue/crawlers", "/aws-glue/column-statistics",
)
CATALOG_DATABASES = ("mimic4_db_business_demo", "mimic4_db_raw_demo")

DPU_PER_WORKER = {"G.1X": 1, "G.2X": 2, "G.4X": 4, "G.8X": 8, "G.025X": 0.25, "Standard": 1}


def human(n):
    n = float(n or 0)
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or u == "TiB":
            return f"{n:,.1f} {u}" if u != "B" else f"{int(n):,} B"
        n /= 1024


def usd(x):
    return round(float(x), 4)


def _parse_ts(s):
    """Parse a timestamp that may come from Athena ('YYYY-MM-DD HH:MM:SS[.ffffff]',
    space-separated, always UTC-naive) or a --since CLI value in either that format or
    ISO ('T'-separated, optionally with a timezone). Returns a naive UTC datetime."""
    if not s:
        return None
    s = s.strip()
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def job_owner(name):
    if name in JOB_EXACT:
        return "lakehouse"
    if any(name.startswith(p) for p in JOB_PREFIXES) and name.endswith(DATASET_SUFFIX):
        return "lakehouse"
    if name.startswith("mimic4-dw-etl-"):
        return "warehouse"
    return "other"


def _apply_profile(p) -> None:
    """Rebind the resource-name globals to the --dataset profile's suffixed names."""
    global DATASET_SUFFIX, JOB_EXACT, CRAWLERS, IAM_ROLES, BUCKETS, CATALOG_DATABASES
    DATASET_SUFFIX = p.suffix
    JOB_EXACT = {n + p.suffix for n in _JOB_EXACT_BASE}
    CRAWLERS = (p.crawler_name,)
    IAM_ROLES = tuple(n + p.suffix for n in _IAM_ROLES_BASE)
    BUCKETS = (p.raw_bucket, p.gold_bucket, p.scripts_bucket, p.nlp_bucket)
    CATALOG_DATABASES = (p.gold_database, p.raw_database)


def dpu_of_run(r):
    """(billed DPU-seconds, exec seconds) for one job run -- prefer the API value."""
    et = r.get("ExecutionTime", 0) or 0
    if r.get("DPUSeconds"):
        return float(r["DPUSeconds"]), et
    per = DPU_PER_WORKER.get(r.get("WorkerType"))
    nw = r.get("NumberOfWorkers") or 0
    if per and nw:
        return et * per * nw, et
    return et * (r.get("MaxCapacity") or 0), et


def collect_glue_jobs(glue):
    names = []
    for pg in glue.get_paginator("get_jobs").paginate():
        names += [j["Name"] for j in pg["Jobs"]]
    rows = []
    for n in sorted(names):
        if job_owner(n) != "lakehouse":
            continue
        cfg = glue.get_job(JobName=n)["Job"]
        states, ok, failed, dpu_sec, exec_sec, dpu_ok, ok_secs = [], 0, 0, 0.0, 0, 0.0, []
        token = None
        while True:
            kw = {"JobName": n, "MaxResults": 200}
            if token:
                kw["NextToken"] = token
            resp = glue.get_job_runs(**kw)
            for r in resp["JobRuns"]:
                d, e = dpu_of_run(r)
                dpu_sec += d
                exec_sec += e
                st = r["JobRunState"]
                states.append(st)
                if st == "SUCCEEDED":
                    ok += 1
                    dpu_ok += d
                    ok_secs.append(d)
                elif st in ("FAILED", "TIMEOUT", "ERROR"):
                    failed += 1
            token = resp.get("NextToken")
            if not token:
                break
        rows.append({
            "job": n,
            "glue_version": cfg.get("GlueVersion"),
            "worker": (f"{cfg.get('NumberOfWorkers')} x {cfg.get('WorkerType')}"
                       if cfg.get("WorkerType") else f"{cfg.get('MaxCapacity')} DPU"),
            "command": cfg.get("Command", {}).get("Name"),
            "runs": len(states), "ok": ok, "failed": failed,
            "exec_seconds": exec_sec,
            "dpu_seconds_total": round(dpu_sec, 1),
            "dpu_seconds_successful": round(dpu_ok, 1),
            "dpu_seconds_one_clean_run": round(min(ok_secs), 1) if ok_secs else None,
        })
    return rows


def collect_crawlers(glue):
    out = []
    for name in CRAWLERS:
        try:
            m = glue.get_crawler_metrics(CrawlerNameList=[name])["CrawlerMetricsList"]
        except ClientError:
            m = []
        info = m[0] if m else {}
        elapsed, runs = 0.0, 0
        try:
            token = None
            while True:
                kw = {"CrawlerName": name, "MaxResults": 100}
                if token:
                    kw["NextToken"] = token
                resp = glue.list_crawls(**kw)
                for cr in resp.get("Crawls", []):
                    runs += 1
                    s, e = cr.get("StartTime"), cr.get("EndTime")
                    if s and e:
                        elapsed += (e - s).total_seconds()
                token = resp.get("NextToken")
                if not token:
                    break
        except ClientError:
            runs = None
        out.append({
            "crawler": name,
            "runs": runs,
            "last_runtime_seconds": info.get("LastRuntimeSeconds"),
            "median_runtime_seconds": info.get("MedianRuntimeSeconds"),
            "tables_in_catalog": info.get("TablesCreated"),
            "total_elapsed_seconds": round(elapsed, 1),
        })
    return out


def collect_logs(logs):
    out = []
    for g in logs.get_paginator("describe_log_groups").paginate():
        for lg in g["logGroups"]:
            if lg["logGroupName"] in GLUE_LOG_GROUPS:
                out.append({"log_group": lg["logGroupName"], "stored_bytes": lg.get("storedBytes", 0)})
    return sorted(out, key=lambda x: -x["stored_bytes"])


def collect_catalog(glue):
    out = []
    for d in CATALOG_DATABASES:
        try:
            n = 0
            for pg in glue.get_paginator("get_tables").paginate(DatabaseName=d):
                n += len(pg["TableList"])
            out.append({"database": d, "tables": n})
        except ClientError:
            out.append({"database": d, "tables": None})
    return out


def collect_athena(ath, skip):
    if skip:
        return None
    total, n, engine_ms = 0, 0, 0
    token = None
    try:
        while True:
            kw = {"MaxResults": 50}
            if token:
                kw["NextToken"] = token
            resp = ath.list_query_executions(**kw)
            ids = resp.get("QueryExecutionIds", [])
            if not ids:
                break
            for i in range(0, len(ids), 50):
                for qe in ath.batch_get_query_execution(QueryExecutionIds=ids[i:i + 50])["QueryExecutions"]:
                    st = qe.get("Statistics", {})
                    total += st.get("DataScannedInBytes", 0)
                    engine_ms += st.get("EngineExecutionTimeInMillis", 0)
                    n += 1
            token = resp.get("NextToken")
            if not token:
                break
    except ClientError as e:
        return {"queries": n, "total_scanned_bytes": total, "total_engine_ms": engine_ms,
                "note": f"listing stopped early: {e}"}
    return {"queries": n, "total_scanned_bytes": total, "total_engine_ms": engine_ms}


def load_storage(mode: str = "demo"):
    for p in (REPO_ROOT / "docs" / "storage_footprint" / mode / "latest.json",
              REPO_ROOT / "docs" / "storage_footprint" / "latest.json"):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def build_cost(r):
    c = r["consumption"]
    p = PRICES
    dpu_all = c["glue_dpu_seconds_total"]
    dpu_ok = c["glue_dpu_seconds_successful"]
    dpu_clean = c["glue_dpu_seconds_one_clean_pipeline"]
    crawler_sec = c["crawler_elapsed_seconds"] or 0
    log_bytes = c["cloudwatch_log_bytes"]
    cat_obj = c["glue_catalog_objects"]
    scanned = c["athena_scanned_bytes"] or 0
    s3_phys = c["s3_physical_bytes"] or 0
    s3_live = c["s3_gold_live_bytes"] or 0
    s3_raw = c["s3_raw_bytes"] or 0

    glue_all = usd(dpu_all / 3600 * p["glue_dpu_hour"])
    glue_ok = usd(dpu_ok / 3600 * p["glue_dpu_hour"])
    glue_clean = usd(dpu_clean / 3600 * p["glue_dpu_hour"])
    crawler_run = usd(max(crawler_sec / max(c["crawler_runs"] or 1, 1), 600) / 3600 * 2 * p["glue_dpu_hour"])
    crawler_all = usd(max(crawler_sec, 600) / 3600 * 2 * p["glue_dpu_hour"])
    athena_all = usd(scanned / TB * p["athena_per_tb_scanned"])
    cw_ingest = usd(log_bytes / GB * p["cw_logs_ingest_per_gb"])
    cw_store_m = usd(log_bytes / GB * p["cw_logs_storage_gb_month"])
    s3_store_m = usd(s3_phys / GB * p["s3_standard_gb_month"])
    s3_clean_m = usd((s3_raw + s3_live) / GB * p["s3_standard_gb_month"])
    cat_m = 0.0 if cat_obj < 1_000_000 else usd((cat_obj - 1_000_000) / 100_000 * p["glue_catalog_per_100k_objects_month"])

    one_time = usd(glue_all + athena_all + cw_ingest)
    one_run = usd(glue_clean + crawler_run)
    steady = usd(s3_store_m + cw_store_m + cat_m)
    steady_clean = usd(s3_clean_m + cw_store_m + cat_m)

    return {
        "one_time_build_and_debug": {
            "glue_etl_all_runs": glue_all,
            "athena_all_queries": athena_all,
            "cloudwatch_log_ingestion": cw_ingest,
            "total": one_time,
        },
        "one_clean_pipeline_run": {
            "glue_etl_min_successful_run_per_job": glue_clean,
            "glue_etl_all_successful_runs": glue_ok,
            "glue_crawler_one_run": crawler_run,
            "total_min": one_run,
        },
        "steady_state_monthly": {
            "s3_storage_as_deployed": s3_store_m,
            "s3_storage_after_orphan_cleanup": s3_clean_m,
            "cloudwatch_log_storage": cw_store_m,
            "glue_data_catalog": cat_m,
            "total_as_deployed": steady,
            "total_after_cleanup": steady_clean,
        },
        # Cost to build the environment once (one_clean_pipeline_run) plus a year of
        # sitting populated and queryable with no further loads (12 x steady_state_monthly)
        # -- the "stand it up and keep it around" number, as distinct from the cumulative
        # one_time_build_and_debug figure above (which includes every debugging run/query
        # ever executed against this environment, not a single clean load).
        "annual_cost_estimate": {
            "load_cost_usd": one_run,
            "annual_steady_state_usd_as_deployed": usd(steady * 12),
            "annual_steady_state_usd_after_cleanup": usd(steady_clean * 12),
            "first_year_total_usd_as_deployed": usd(one_run + steady * 12),
            "first_year_total_usd_after_cleanup": usd(one_run + steady_clean * 12),
            "notes": [
                "load_cost_usd = one_clean_pipeline_run.total_min (one successful Glue ETL run per job "
                "+ one crawler run) -- the cost to populate an empty environment once.",
                "annual_steady_state = 12 x steady_state_monthly -- assumes no further pipeline runs "
                "during the year (build once, query many); add load_cost_usd again per additional "
                "full reload during the year.",
            ],
        },
        "notes": [
            f"Glue Data Catalog: {cat_obj} objects < 1,000,000 free tier -> $0/month.",
            f"IAM roles ({len(IAM_ROLES)}), Lake Formation, SSE-S3 encryption: no charge.",
            "CloudWatch /aws-glue/jobs/* groups are account-wide, shared with the 5 warehouse "
            "Glue jobs -- attributed in full here as an upper bound.",
            "Athena figure is ALL query history in the region (compaction + measurement + NLP "
            "dev); a steady-state month scans ~0 ($files reads are metadata, not data).",
            "S3 'after cleanup' = raw bucket + Gold live snapshot, i.e. once a Spark "
            "remove_orphan_files pass removes the superseded pre-compaction files.",
        ],
    }


def render_md(r):
    c, ce = r["consumption"], r["cost_estimate_usd"]
    ot = ce["one_time_build_and_debug"]
    orr = ce["one_clean_pipeline_run"]
    sm = ce["steady_state_monthly"]
    w = []
    P = w.append
    P("# Lakehouse Pipeline Manifest — AWS resources & cost")
    P("")
    P(f"- **Generated:** {r['generated_utc']}  ·  region `{r['region']}`")
    P(f"- **Source:** `measure_aws_resources.py` + `measure_storage_footprint.py` (S3 figures)")
    P(f"- Exact API values for Glue DPU-seconds, crawler runtime, CloudWatch `storedBytes`, "
      f"catalog counts, Athena `DataScannedInBytes`. Prices: public on-demand, us-east-2.")
    P("")
    P("## Consumption")
    P("")
    P("| Resource | Quantity |")
    P("|---|--:|")
    P(f"| Glue ETL jobs (this pipeline) | {c['glue_job_count']} |")
    P(f"| Glue job runs (all, incl. failed) | {c['glue_run_count']} |")
    P(f"| Glue compute — all runs | {c['glue_dpu_hours_total']:.2f} DPU-hr ({c['glue_dpu_seconds_total']:,.0f} DPU-s) |")
    P(f"| Glue compute — successful runs only | {c['glue_dpu_hours_successful']:.2f} DPU-hr |")
    P(f"| Glue compute — one clean pipeline (min ok run/job) | {c['glue_dpu_seconds_one_clean_pipeline']/3600:.2f} DPU-hr |")
    P(f"| Glue crawler runs / elapsed | {c['crawler_runs']} / {c['crawler_elapsed_seconds']:,.0f} s |")
    P(f"| Glue Data Catalog objects | {c['glue_catalog_objects']:,} |")
    P(f"| Athena queries / data scanned (all history) | {(r['athena'] or {}).get('queries','?')} / {human(c['athena_scanned_bytes'])} |")
    P(f"| CloudWatch Logs (Glue groups, shared) | {human(c['cloudwatch_log_bytes'])} |")
    P(f"| S3 physical — total (as deployed) | {human(c['s3_physical_bytes'])} |")
    P(f"| S3 — Gold live snapshot | {human(c['s3_gold_live_bytes'])} |")
    P(f"| S3 — Gold objects | {c['s3_gold_objects']:,} |")
    P(f"| IAM roles | {len(IAM_ROLES)} (no charge) |")
    P("")
    P("## Glue ETL jobs")
    P("")
    P("| Job | Glue | Workers | Runs | ok / fail | DPU-s all | DPU-s 1 run |")
    P("|---|---|---|--:|--:|--:|--:|")
    for j in sorted(r["glue_jobs"], key=lambda x: -x["dpu_seconds_total"]):
        P(f"| `{j['job']}` | {j['glue_version']} | {j['worker']} | {j['runs']} | "
          f"{j['ok']} / {j['failed']} | {j['dpu_seconds_total']:,.0f} | "
          f"{j['dpu_seconds_one_clean_run'] or '—'} |")
    P("")
    P("## Glue crawler · CloudWatch · Catalog")
    P("")
    for cr in r["glue_crawlers"]:
        P(f"- **Crawler `{cr['crawler']}`** — {cr['runs']} runs, "
          f"{cr['total_elapsed_seconds']:,.0f} s elapsed, last {cr['last_runtime_seconds']} s.")
    P("")
    P("| CloudWatch log group | Stored |")
    P("|---|--:|")
    for g in r["cloudwatch_log_groups"]:
        P(f"| `{g['log_group']}` | {human(g['stored_bytes'])} |")
    P("")
    P("| Catalog database | Tables |")
    P("|---|--:|")
    for cat in r["glue_data_catalog"]:
        P(f"| `{cat['database']}` | {cat['tables']} |")
    P("")
    P("## Cost estimate (USD)")
    P("")
    P("### One-time — build + debugging history (already spent)")
    P("")
    P("| Item | Cost |")
    P("|---|--:|")
    P(f"| Glue ETL — every run ever ({c['glue_dpu_hours_total']:.2f} DPU-hr) | ${ot['glue_etl_all_runs']:.2f} |")
    P(f"| Athena — all query history ({human(c['athena_scanned_bytes'])}) | ${ot['athena_all_queries']:.2f} |")
    P(f"| CloudWatch Logs — ingestion of {human(c['cloudwatch_log_bytes'])} | ${ot['cloudwatch_log_ingestion']:.2f} |")
    P(f"| **Total one-time** | **${ot['total']:.2f}** |")
    P("")
    P("### One clean end-to-end pipeline run (repeatable unit cost)")
    P("")
    P("| Item | Cost |")
    P("|---|--:|")
    P(f"| Glue ETL — one successful run of each of {c['glue_job_count']} jobs "
      f"({c['glue_dpu_seconds_one_clean_pipeline']/3600:.2f} DPU-hr) | ${orr['glue_etl_min_successful_run_per_job']:.2f} |")
    P(f"| Glue crawler — one run | ${orr['glue_crawler_one_run']:.2f} |")
    P(f"| **Total per full rebuild** | **${orr['total_min']:.2f}** |")
    P("")
    P("### Steady-state — monthly, no pipeline runs")
    P("")
    P("| Item | As deployed | After orphan cleanup |")
    P("|---|--:|--:|")
    P(f"| S3 storage | ${sm['s3_storage_as_deployed']:.3f} | ${sm['s3_storage_after_orphan_cleanup']:.3f} |")
    P(f"| CloudWatch log storage | ${sm['cloudwatch_log_storage']:.3f} | ${sm['cloudwatch_log_storage']:.3f} |")
    P(f"| Glue Data Catalog | ${sm['glue_data_catalog']:.3f} | ${sm['glue_data_catalog']:.3f} |")
    P(f"| **Monthly total** | **${sm['total_as_deployed']:.3f}** | **${sm['total_after_cleanup']:.3f}** |")
    P("")
    P("### Load the environment once, keep it running for a year")
    P("")
    ac = ce["annual_cost_estimate"]
    P("| Item | As deployed | After orphan cleanup |")
    P("|---|--:|--:|")
    P(f"| Load cost (one clean pipeline run) | ${ac['load_cost_usd']:.2f} | ${ac['load_cost_usd']:.2f} |")
    P(f"| Annual steady-state (12 × monthly) | ${ac['annual_steady_state_usd_as_deployed']:.2f} | "
      f"${ac['annual_steady_state_usd_after_cleanup']:.2f} |")
    P(f"| **First-year total** | **${ac['first_year_total_usd_as_deployed']:.2f}** | "
      f"**${ac['first_year_total_usd_after_cleanup']:.2f}** |")
    P("")
    for note in ac["notes"]:
        P(f"- {note}")
    P("")
    P("### Notes")
    for note in ce["notes"]:
        P(f"- {note}")
    P("")
    P("## Prices used (us-east-2 on-demand)")
    P("")
    for k, v in PRICES.items():
        P(f"- `{k}` = {v}")
    P("")
    return "\n".join(w) + "\n"


def _athena_query_all(athena, sql: str, output_location: str) -> list[dict]:
    """Run one Athena SELECT to completion and return every row as a
    {column_name: value_or_None} dict (VarCharValue's own string typing --
    callers int()/float() the columns they need). Raises on a genuine query failure;
    callers of the --by-run report decide how to handle that (there's no data to report
    without it, unlike the best-effort per-job counts in run_lakehouse_pipeline.py)."""
    qid = athena.start_query_execution(
        QueryString=sql, ResultConfiguration={"OutputLocation": output_location},
        WorkGroup=env("ATHENA_WORKGROUP", "primary"),
    )["QueryExecutionId"]
    while True:
        ex = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = ex["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena query failed ({state}): {ex['Status'].get('StateChangeReason')}")

    rows: list[dict] = []
    columns = None
    token = None
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        res = athena.get_query_results(**kw)
        raw_rows = res["ResultSet"]["Rows"]
        if columns is None:
            columns = [c.get("VarCharValue") for c in raw_rows[0]["Data"]]
            raw_rows = raw_rows[1:]  # drop the header row, only present on the first page
        for r in raw_rows:
            values = [c.get("VarCharValue") for c in r["Data"]]
            rows.append(dict(zip(columns, values)))
        token = res.get("NextToken")
        if not token:
            break
    return rows


def _num(v, cast=float):
    # Athena omits VarCharValue entirely for a SQL NULL (-> None from .get() already),
    # but treat an empty string the same way defensively rather than let int('')/float('')
    # raise on a column that's blank for any other reason.
    return None if v is None or v == "" else cast(v)


def _parse_ts(ts):
    if not ts:
        return None
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cloudwatch_bytes_ingested(cloudwatch, log_groups, start_iso, end_iso):
    """Total AWS/Logs IncomingBytes summed across `log_groups` for [start_iso, end_iso] --
    the CloudWatch log volume ONE run actually generated. Deliberately not storedBytes
    (a point-in-time total for the whole log group's retention, with no notion of "as of
    run N") -- IncomingBytes is a genuine per-period metric available within minutes, so
    it's safe to use even for a run that just finished, unlike S3/EBS daily storage
    metrics which lag by up to a day. Returns None if the run has no recorded window."""
    start, end = _parse_ts(start_iso), _parse_ts(end_iso)
    if not start or not end:
        return None
    end = end + timedelta(minutes=5)  # Glue's log delivery lags job completion slightly
    total = 0.0
    for lg in log_groups:
        try:
            resp = cloudwatch.get_metric_statistics(
                Namespace="AWS/Logs", MetricName="IncomingBytes",
                Dimensions=[{"Name": "LogGroupName", "Value": lg}],
                StartTime=start, EndTime=end, Period=300, Statistics=["Sum"],
            )
            total += sum(p["Sum"] for p in resp.get("Datapoints", []))
        except ClientError:
            continue
    return total


def cloudwatch_bytes_attributed(logs_client, log_groups, run_ids, start_iso, end_iso):
    """Proportional share of a shared Glue log group's ingested bytes that belongs to a
    specific set of Glue JobRunIds, via CloudWatch Logs Insights.

    The 7 Glue-managed log groups in this account (/aws-glue/jobs/*, /aws-glue/crawlers,
    /aws-glue/python-jobs/*, /aws-glue/sessions/error) are shared infrastructure -- every
    Glue job in the account, lakehouse or warehouse, writes into the same small set of
    groups, and DescribeLogStreams' storedBytes field is deprecated (always 0 in this
    account), so there is no per-job byte count available from stream metadata alone.
    What IS available: every log stream Glue creates is named `jr_<JobRunId>[-<task>|
    -driver|-progress-bar]`, so a job's own JobRunId (already logged per job in
    etl_process_log / run_id) can be matched against @logStream via a Logs Insights query,
    giving an exact per-job-run attribution instead of an account-wide blanket total.

    This is an approximation of true ingested bytes -- it sums log MESSAGE length
    (strlen(@message)), not the wire-format bytes CloudWatch's own IncomingBytes metric
    counts (which adds a small fixed per-event overhead) -- adequate for proportioning a
    shared total between architectures, not for an absolute byte-for-byte cost figure.
    Returns None if run_ids is empty or every query fails (e.g. a permissions gap)."""
    if not run_ids:
        return None
    start, end = _parse_ts(start_iso), _parse_ts(end_iso)
    if not start or not end:
        return None
    end = end + timedelta(minutes=5)  # Glue's log delivery lags job completion slightly
    pattern = "|".join(sorted(run_ids))
    query = f"filter @logStream like /^({pattern})(-|$)/ | stats sum(strlen(@message)) as bytes"
    total = 0.0
    any_ok = False
    for lg in log_groups:
        try:
            qid = logs_client.start_query(
                logGroupName=lg, startTime=int(start.timestamp()), endTime=int(end.timestamp()),
                queryString=query, limit=1,
            )["queryId"]
        except ClientError:
            continue
        for _ in range(30):
            res = logs_client.get_query_results(queryId=qid)
            if res["status"] in ("Complete", "Failed", "Cancelled"):
                break
            time.sleep(1)
        else:
            continue
        if res["status"] != "Complete" or not res.get("results"):
            continue
        any_ok = True
        for field in res["results"][0]:
            if field["field"] == "bytes":
                try:
                    total += float(field["value"])
                except (TypeError, ValueError):
                    pass
    return total if any_ok else None


def collect_current_footprint(glue, logs, mode: str) -> dict:
    """Point-in-time context attached to a --by-run report: current storage, Glue Data
    Catalog size, and CloudWatch log group totals -- NOT per-run (S3's own storage
    metrics are daily and lag up to 24h, so retroactively attributing "storage as of run
    N" would be fabricated precision). Reuses the snapshot-mode collectors so there's one
    source of truth for what a "table count" or "log group" means."""
    storage = load_storage(mode)
    s3_phys = s3_live = s3_raw = s3_objects = None
    if storage:
        raw = storage.get("raw_bucket", {})
        gp = storage.get("gold_bucket", {})
        s3_raw = raw.get("total_bytes")
        s3_objects = gp.get("physical_objects")
        s3_live = gp.get("live_snapshot_bytes")
        sv = storage.get("structured_vs_unstructured", {})
        s3_phys = (sv.get("grand_total_physical_bytes")
                   or storage.get("total_lakehouse_physical_bytes")
                   or ((s3_raw or 0) + (gp.get("physical_bytes") or 0)))
    log_groups = collect_logs(logs)
    catalog = collect_catalog(glue)
    crawlers = collect_crawlers(glue)
    jobs = collect_glue_jobs(glue)
    log_bytes = sum(g["stored_bytes"] for g in log_groups)
    catalog_objects = sum((c["tables"] or 0) for c in catalog)
    crawler_sec = sum(c["total_elapsed_seconds"] or 0 for c in crawlers)

    # Reuses build_cost()'s pricing model with a minimal {"consumption": {...}} shape --
    # Athena scan history is left at 0 here (an account-wide history scan on every --by-run
    # call would be slow and is already covered by the point-in-time snapshot mode's own
    # --skip-athena-gated collection), so the "one_time_build_and_debug" figure below omits
    # Athena's contribution; everything else (Glue, crawler, storage, CloudWatch, catalog)
    # is real.
    cost = build_cost({"consumption": {
        "glue_dpu_seconds_total": sum(j["dpu_seconds_total"] for j in jobs),
        "glue_dpu_seconds_successful": sum(j["dpu_seconds_successful"] for j in jobs),
        "glue_dpu_seconds_one_clean_pipeline": sum((j["dpu_seconds_one_clean_run"] or 0) for j in jobs),
        "crawler_elapsed_seconds": crawler_sec,
        "crawler_runs": sum((c["runs"] or 0) for c in crawlers),
        "cloudwatch_log_bytes": log_bytes,
        "glue_catalog_objects": catalog_objects,
        "athena_scanned_bytes": 0,
        "s3_physical_bytes": s3_phys,
        "s3_raw_bytes": s3_raw,
        "s3_gold_live_bytes": s3_live,
    }})

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "s3_physical_bytes": s3_phys,
        "s3_raw_bytes": s3_raw,
        "s3_gold_live_bytes": s3_live,
        "s3_gold_objects": s3_objects,
        "storage_footprint_ref": f"docs/storage_footprint/{mode}/latest.json",
        "cloudwatch_log_groups": log_groups,
        "cloudwatch_log_bytes_total": log_bytes,
        "glue_data_catalog": catalog,
        "glue_data_catalog_objects": catalog_objects,
        "glue_crawlers": crawlers,
        "iam_roles": list(IAM_ROLES),
        "iam_role_count": len(IAM_ROLES),
        "cost_estimate_usd": cost,
    }


def collect_runs(athena, output_location: str, gold_database: str, cloudwatch=None,
                 logs_client=None) -> list[dict]:
    """Every job row from <gold_database>.etl_process_log, grouped into one summary dict
    per full_run_id -- the resource/timing footprint of one end-to-end
    run_lakehouse_pipeline.py invocation, straight from what it logged as it ran (no
    live Glue API calls -- etl_process_log outlives Glue's own job-run history)."""
    job_rows = _athena_query_all(
        athena,
        f"SELECT full_run_id, run_id, job_name, process_name, process_type, phase, dataset, "
        f"start_ts, end_ts, execution_seconds, dpu_seconds, raw_row_count, gold_row_count, "
        f"status, error_message FROM {gold_database}.etl_process_log "
        f"WHERE full_run_id IS NOT NULL ORDER BY full_run_id, start_ts",
        output_location,
    )

    by_run: dict[int, dict] = {}
    for jr in job_rows:
        fid = int(jr["full_run_id"])
        run = by_run.setdefault(fid, {"full_run_id": fid, "dataset": jr.get("dataset"), "jobs": []})
        run["jobs"].append({
            "job_name": jr["job_name"], "process_name": jr["process_name"],
            "process_type": jr["process_type"], "phase": jr["phase"], "run_id": jr.get("run_id"),
            "start_ts": jr["start_ts"], "end_ts": jr["end_ts"],
            "execution_seconds": _num(jr["execution_seconds"]),
            "dpu_seconds": _num(jr["dpu_seconds"]),
            "raw_row_count": _num(jr["raw_row_count"], int),
            "gold_row_count": _num(jr["gold_row_count"], int),
            "status": jr["status"], "error_message": jr.get("error_message"),
        })

    runs = []
    for fid, run in sorted(by_run.items()):
        jobs = run["jobs"]
        starts = [j["start_ts"] for j in jobs if j["start_ts"]]
        ends = [j["end_ts"] for j in jobs if j["end_ts"]]
        started_at, completed_at = (min(starts) if starts else None), (max(ends) if ends else None)
        wall_seconds = None
        if started_at and completed_at:
            wall_seconds = (datetime.fromisoformat(completed_at) -
                            datetime.fromisoformat(started_at)).total_seconds()
        total_dpu = sum(j["dpu_seconds"] or 0 for j in jobs)
        by_type: dict[str, dict] = {}
        for j in jobs:
            t = by_type.setdefault(j["process_type"], {"count": 0, "dpu_seconds": 0.0, "execution_seconds": 0.0})
            t["count"] += 1
            t["dpu_seconds"] += j["dpu_seconds"] or 0
            t["execution_seconds"] += j["execution_seconds"] or 0
        for t in by_type.values():
            t["dpu_seconds"] = round(t["dpu_seconds"], 1)
            t["execution_seconds"] = round(t["execution_seconds"], 1)
            t["cost_usd"] = usd(t["dpu_seconds"] / 3600 * PRICES["glue_dpu_hour"])

        cw_bytes = (cloudwatch_bytes_ingested(cloudwatch, GLUE_LOG_GROUPS, started_at, completed_at)
                   if cloudwatch is not None else None)
        run_ids = {j["run_id"] for j in jobs if j.get("run_id")}
        cw_bytes_attributed = (
            cloudwatch_bytes_attributed(logs_client, GLUE_LOG_GROUPS, run_ids, started_at, completed_at)
            if logs_client is not None else None
        )

        runs.append({
            "full_run_id": fid,
            "dataset": run["dataset"],
            "started_at": started_at,
            "completed_at": completed_at,
            "wall_clock_seconds": wall_seconds,
            "job_count": len(jobs),
            "succeeded_count": sum(1 for j in jobs if j["status"] == "SUCCEEDED"),
            "failed_count": sum(1 for j in jobs if j["status"] not in ("SUCCEEDED", None)),
            "total_dpu_seconds": round(total_dpu, 1),
            "total_dpu_hours": round(total_dpu / 3600, 4),
            "total_execution_seconds": round(sum(j["execution_seconds"] or 0 for j in jobs), 1),
            "glue_cost_usd": usd(total_dpu / 3600 * PRICES["glue_dpu_hour"]),
            "cloudwatch_bytes_ingested": round(cw_bytes, 0) if cw_bytes is not None else None,
            "cloudwatch_bytes_attributed": round(cw_bytes_attributed, 0) if cw_bytes_attributed is not None else None,
            "total_raw_rows": sum(j["raw_row_count"] for j in jobs if j["raw_row_count"] is not None) or None,
            "total_gold_rows": sum(j["gold_row_count"] for j in jobs if j["gold_row_count"] is not None) or None,
            "by_process_type": by_type,
            "jobs": jobs,
        })
    return runs


def _stats(values: list[float]) -> dict:
    """mean/median/(sample) stdev/min/max -- stdev needs n>=2 (statistics.stdev raises
    below that), reported as None for a single run rather than a fabricated 0."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "stdev": None, "min": None, "max": None}
    return {
        "n": len(vals),
        "mean": round(statistics.mean(vals), 3),
        "median": round(statistics.median(vals), 3),
        "stdev": round(statistics.stdev(vals), 3) if len(vals) >= 2 else None,
        "min": round(min(vals), 3),
        "max": round(max(vals), 3),
    }


def compute_run_statistics(runs: list[dict]) -> dict:
    """Cross-run mean/median/stdev for the headline metrics in `runs` (one dict per
    full_run_id, from collect_runs) -- the statistical-analysis half of the --by-run
    report; `runs` itself is the detailed half."""
    return {
        "n_runs": len(runs),
        "wall_clock_seconds": _stats([r["wall_clock_seconds"] for r in runs]),
        "total_dpu_seconds": _stats([r["total_dpu_seconds"] for r in runs]),
        "total_dpu_hours": _stats([r.get("total_dpu_hours") for r in runs]),
        "total_execution_seconds": _stats([r["total_execution_seconds"] for r in runs]),
        "glue_cost_usd": _stats([r["glue_cost_usd"] for r in runs]),
        "cloudwatch_bytes_ingested": _stats([r.get("cloudwatch_bytes_ingested") for r in runs]),
        "cloudwatch_bytes_attributed": _stats([r.get("cloudwatch_bytes_attributed") for r in runs]),
        "job_count": _stats([r["job_count"] for r in runs]),
        "failed_count": _stats([r["failed_count"] for r in runs]),
        "total_raw_rows": _stats([r["total_raw_rows"] for r in runs]),
        "total_gold_rows": _stats([r["total_gold_rows"] for r in runs]),
    }


def render_runs_md(report: dict) -> str:
    w = []
    P = w.append
    P("# Lakehouse pipeline -- resource usage by full run")
    P("")
    P(f"Generated {report['generated_utc']}  ·  dataset {report['dataset']}  ·  "
      f"source `{report['gold_database']}.etl_process_log`  ·  "
      f"last {report.get('last_n', report['summary_statistics']['n_runs'])} run(s)")
    if report.get("since"):
        P(f"- **Since cutoff:** `{report['since']}` -- "
          f"{report.get('n_runs_excluded_before_since', 0)} run(s) excluded as started before it "
          f"({report.get('n_runs_eligible', '?')} of {report.get('n_runs_available', '?')} eligible)")
    P("")
    P("## Detailed data -- one row per full_run_id")
    P("")
    P("| full_run_id | started_at | wall clock | jobs | failed | DPU-s | Glue $ | CW bytes (group total) | CW bytes (this run, attributed) | raw rows | gold rows |")
    P("|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for r in report["runs"]:
        raw_rows = f"{r['total_raw_rows']:,}" if r["total_raw_rows"] is not None else "—"
        gold_rows = f"{r['total_gold_rows']:,}" if r["total_gold_rows"] is not None else "—"
        cw_bytes = r.get("cloudwatch_bytes_ingested")
        cw = human(cw_bytes) if cw_bytes is not None else "—"
        cw_attr = r.get("cloudwatch_bytes_attributed")
        cw_attr_s = human(cw_attr) if cw_attr is not None else "—"
        P(f"| {r['full_run_id']} | {r['started_at'] or '?'} | "
          f"{human_seconds(r['wall_clock_seconds'])} | {r['job_count']} | {r['failed_count']} | "
          f"{r['total_dpu_seconds']:,.1f} | ${r['glue_cost_usd']:.4f} | {cw} | {cw_attr_s} | {raw_rows} | {gold_rows} |")
    P("")
    P("\"CW bytes (group total)\" is every byte the account's shared Glue log groups "
      "ingested during this run's wall-clock window, from any job in the account -- "
      "including the warehouse pipeline's jobs if they happened to run concurrently. "
      "\"CW bytes (this run, attributed)\" is the CloudWatch Logs Insights-computed subset "
      "attributable specifically to this run's own Glue JobRunIds (log streams are named "
      "`jr_<JobRunId>[-task]`, so exact per-job-run attribution is possible even in a "
      "shared log group); it approximates ingested bytes via message length "
      "(`strlen(@message)`), not CloudWatch's own per-event wire-format accounting, so "
      "expect it to run slightly under the true IncomingBytes figure. Use the attributed "
      "column when comparing CloudWatch cost between architectures.")
    P("")
    P("### Per-run breakdown by process type")
    P("")
    for r in report["runs"]:
        P(f"**full_run_id {r['full_run_id']}**")
        P("")
        P("| process_type | jobs | DPU-s | Glue $ |")
        P("|---|--:|--:|--:|")
        for ptype, t in sorted(r["by_process_type"].items()):
            P(f"| {ptype} | {t['count']} | {t['dpu_seconds']:,.1f} | ${t['cost_usd']:.4f} |")
        P("")
    P("## Statistical analysis across runs")
    P("")
    s = report["summary_statistics"]
    P(f"n = {s['n_runs']} run(s). stdev is sample stdev (n-1); reported as — for a "
      "single run, not fabricated as 0.")
    P("")
    P("| Metric | Mean | Median | Stdev | Min | Max |")
    P("|---|--:|--:|--:|--:|--:|")
    labels = {
        "wall_clock_seconds": "Wall clock (s)",
        "total_dpu_seconds": "Total DPU-seconds",
        "total_dpu_hours": "Total DPU-hours",
        "total_execution_seconds": "Total execution (s)",
        "glue_cost_usd": "Glue cost (USD)",
        "cloudwatch_bytes_ingested": "CloudWatch bytes ingested (shared log group total)",
        "cloudwatch_bytes_attributed": "CloudWatch bytes attributed (this run's own jobs)",
        "job_count": "Job count",
        "failed_count": "Failed job count",
        "total_raw_rows": "Total raw rows",
        "total_gold_rows": "Total gold rows",
    }
    for key, label in labels.items():
        d = s[key]
        if d["n"] == 0:
            P(f"| {label} | — | — | — | — | — |")
            continue
        stdev = f"{d['stdev']:,.3f}" if d["stdev"] is not None else "—"
        P(f"| {label} | {d['mean']:,.3f} | {d['median']:,.3f} | {stdev} | {d['min']:,.3f} | {d['max']:,.3f} |")
    P("")
    fp = report.get("current_footprint")
    if fp:
        P("## Current resource footprint (point-in-time, not per-run)")
        P("")
        P("S3 storage, the Glue Data Catalog, and CloudWatch log retention don't have a clean "
          "per-run reading (S3's own size metrics are daily and lag up to 24h) -- this is the "
          "current state, for context alongside the per-run compute/logging trend above.")
        P("")
        P(f"- **Measured:** {fp['measured_at']}")
        P(f"- **S3 physical (all)**: {human(fp['s3_physical_bytes'])}  ·  "
          f"**raw**: {human(fp['s3_raw_bytes'])}  ·  "
          f"**Gold live**: {human(fp['s3_gold_live_bytes'])} ({fp['s3_gold_objects']} objects)")
        P(f"- **CloudWatch log groups (Glue, shared w/ warehouse if same account)**: "
          f"{human(fp['cloudwatch_log_bytes_total'])} across {len(fp['cloudwatch_log_groups'])} group(s)")
        P(f"- **Glue Data Catalog**: {fp['glue_data_catalog_objects']:,} tables across "
          f"{len(fp['glue_data_catalog'])} database(s)")
        P(f"- **Glue crawlers**: {len(fp['glue_crawlers'])}  ·  **IAM roles**: {fp['iam_role_count']}")
        fp_ac = fp.get("cost_estimate_usd", {}).get("annual_cost_estimate")
        if fp_ac:
            P(f"- **Load + 1 year running**: ${fp_ac['first_year_total_usd_as_deployed']:.2f} as-deployed "
              f"(load ${fp_ac['load_cost_usd']:.2f} + annual ${fp_ac['annual_steady_state_usd_as_deployed']:.2f})")
        P("")
    return "\n".join(w) + "\n"


def human_seconds(s):
    if s is None:
        return "?"
    s = float(s)
    if s < 60:
        return f"{s:.0f}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{int(m)}m{int(s):02d}s"
    h, m = divmod(m, 60)
    return f"{int(h)}h{int(m):02d}m"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _cfg.add_dataset_arg(ap)
    ap.add_argument("--region", default=env("AWS_REGION", "us-east-2"))
    ap.add_argument("--skip-athena", action="store_true")
    ap.add_argument("--out-dir", default=None,
                    help="output dir (default: docs/cost/<demo|full> for the --dataset)")
    ap.add_argument("--by-run", action="store_true",
                    help="Report resource usage per full_run_id from <gold_database>.etl_process_log "
                         "instead of the point-in-time account-wide snapshot -- detailed per-run data "
                         "plus mean/median/stdev across the last --last-n runs found. Needs "
                         "run_lakehouse_pipeline.py to have been run at least once with process-log on "
                         "(the default).")
    ap.add_argument("--last-n", type=int, default=5,
                    help="With --by-run: restrict the detailed rows and summary statistics to the "
                         "most recent N full_run_ids (default: 5). Pass 0 for every run found.")
    ap.add_argument("--since", default=None,
                    help="With --by-run: exclude any full_run_id that started before this timestamp "
                         "('YYYY-MM-DD HH:MM:SS[.ffffff]' or ISO 8601; naive values are treated as "
                         "UTC, matching etl_process_log.start_ts). Applied before --last-n, so you "
                         "get the last N runs *after* this cutoff -- e.g. to exclude runs affected "
                         "by a bug that has since been fixed.")
    args = ap.parse_args()

    profile = _cfg.dataset_profile(args.dataset)
    _apply_profile(profile)
    if args.out_dir is None:
        args.out_dir = str(REPO_ROOT / "docs" / "cost" / profile.mode)
    print(f"[dataset] {profile.dataset} -> jobs *{profile.suffix}, "
          f"catalog {profile.raw_database}/{profile.gold_database}", flush=True)

    s = boto3.Session(region_name=args.region)

    if args.by_run:
        athena = s.client("athena")
        cloudwatch = s.client("cloudwatch")
        glue_c, logs_c = s.client("glue"), s.client("logs")
        athena_output = f"s3://{profile.gold_bucket}/athena-results/"
        print(f"[by-run] querying {profile.gold_database}.etl_process_log ...", flush=True)
        all_runs = collect_runs(athena, athena_output, profile.gold_database, cloudwatch=cloudwatch,
                                logs_client=logs_c)
        if not all_runs:
            print("No full_run_id rows found -- run run_lakehouse_pipeline.py at least once first.",
                  file=sys.stderr)
            return 1
        since_dt = _parse_ts(args.since) if args.since else None
        eligible = all_runs
        if since_dt is not None:
            eligible = [r for r in all_runs if (_parse_ts(r["started_at"]) or since_dt) >= since_dt]
            excluded = len(all_runs) - len(eligible)
            print(f"[by-run] --since {args.since} -> excluding {excluded} run(s) started before it "
                  f"({len(eligible)} eligible)", flush=True)
        runs = eligible[-args.last_n:] if args.last_n else eligible
        print(f"[by-run] {len(all_runs)} total run(s) found; reporting the last {len(runs)}"
              f"{' since ' + args.since if since_dt is not None else ''}.", flush=True)
        print("[by-run] current resource footprint (storage, catalog, CloudWatch, crawlers) ...", flush=True)
        footprint = collect_current_footprint(glue_c, logs_c, profile.mode)
        report = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "dataset": profile.dataset,
            "gold_database": profile.gold_database,
            "since": args.since,
            "n_runs_excluded_before_since": (len(all_runs) - len(eligible)) if since_dt is not None else 0,
            "last_n": args.last_n or len(eligible),
            "n_runs_available": len(all_runs),
            "n_runs_eligible": len(eligible),
            "runs": runs,
            "summary_statistics": compute_run_statistics(runs),
            "current_footprint": footprint,
        }
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (out_dir / f"runs_{ts}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        (out_dir / "latest_runs.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        md = render_runs_md(report)
        (out_dir / f"runs_{ts}.md").write_text(md, encoding="utf-8")
        (out_dir / "latest_runs.md").write_text(md, encoding="utf-8")
        print(f"\n{len(runs)} full run(s) found.")
        for r in runs:
            print(f"  full_run_id {r['full_run_id']}: {r['job_count']} jobs, "
                  f"{human_seconds(r['wall_clock_seconds'])} wall clock, "
                  f"${r['glue_cost_usd']:.4f} Glue")
        print(f"report: {out_dir / 'latest_runs.md'}")
        return 0

    glue, logs, ath = s.client("glue"), s.client("logs"), s.client("athena")

    print("[1/6] Glue jobs ...", flush=True)
    jobs = collect_glue_jobs(glue)
    print("[2/6] Glue crawler ...", flush=True)
    crawlers = collect_crawlers(glue)
    print("[3/6] CloudWatch Logs ...", flush=True)
    log_groups = collect_logs(logs)
    print("[4/6] Glue Data Catalog ...", flush=True)
    catalog = collect_catalog(glue)
    print("[5/6] Athena history ..." + (" (skipped)" if args.skip_athena else ""), flush=True)
    athena = collect_athena(ath, args.skip_athena)
    print("[6/6] Storage footprint (from latest.json) ...", flush=True)
    storage = load_storage(profile.mode)

    dpu_all = sum(j["dpu_seconds_total"] for j in jobs)
    dpu_ok = sum(j["dpu_seconds_successful"] for j in jobs)
    dpu_clean = sum((j["dpu_seconds_one_clean_run"] or 0) for j in jobs)
    crawler_sec = sum(c["total_elapsed_seconds"] or 0 for c in crawlers)
    crawler_runs = sum((c["runs"] or 0) for c in crawlers)
    log_bytes = sum(g["stored_bytes"] for g in log_groups)
    catalog_objects = sum((c["tables"] or 0) for c in catalog)

    s3_phys = s3_objects = s3_live = s3_raw = None
    if storage:
        raw = storage.get("raw_bucket", {})
        gp = storage.get("gold_bucket", {})
        s3_raw = raw.get("total_bytes")
        s3_objects = gp.get("physical_objects")
        s3_live = gp.get("live_snapshot_bytes")
        sv = storage.get("structured_vs_unstructured", {})
        s3_phys = (sv.get("grand_total_physical_bytes")
                   or storage.get("total_lakehouse_physical_bytes")
                   or ((s3_raw or 0) + (gp.get("physical_bytes") or 0)))

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": profile.dataset,
        "region": args.region,
        "prices_used": PRICES,
        "glue_jobs": jobs,
        "glue_crawlers": crawlers,
        "cloudwatch_log_groups": log_groups,
        "glue_data_catalog": catalog,
        "iam_roles": list(IAM_ROLES),
        "s3_buckets": list(BUCKETS),
        "athena": athena,
        "storage_footprint_ref": f"docs/storage_footprint/{profile.mode}/latest.json",
        "consumption": {
            "glue_job_count": len(jobs),
            "glue_run_count": sum(j["runs"] for j in jobs),
            "glue_dpu_seconds_total": round(dpu_all, 1),
            "glue_dpu_seconds_successful": round(dpu_ok, 1),
            "glue_dpu_seconds_one_clean_pipeline": round(dpu_clean, 1),
            "glue_dpu_hours_total": round(dpu_all / 3600, 3),
            "glue_dpu_hours_successful": round(dpu_ok / 3600, 3),
            "crawler_runs": crawler_runs,
            "crawler_elapsed_seconds": round(crawler_sec, 1),
            "cloudwatch_log_bytes": log_bytes,
            "glue_catalog_objects": catalog_objects,
            "athena_scanned_bytes": (athena or {}).get("total_scanned_bytes", 0),
            "s3_physical_bytes": s3_phys,
            "s3_raw_bytes": s3_raw,
            "s3_gold_objects": s3_objects,
            "s3_gold_live_bytes": s3_live,
        },
    }
    report["cost_estimate_usd"] = build_cost(report)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"aws_resources_{ts}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = render_md(report)
    (out_dir / f"aws_resources_{ts}.md").write_text(md, encoding="utf-8")
    (out_dir / "latest.md").write_text(md, encoding="utf-8")

    ce = report["cost_estimate_usd"]
    print("\n" + "=" * 60)
    print(f"one-time build + debug   : ${ce['one_time_build_and_debug']['total']:.2f}")
    print(f"one clean pipeline run   : ${ce['one_clean_pipeline_run']['total_min']:.2f}")
    print(f"steady-state / month     : ${ce['steady_state_monthly']['total_as_deployed']:.3f} as-deployed"
          f"  /  ${ce['steady_state_monthly']['total_after_cleanup']:.3f} after cleanup")
    ac = ce["annual_cost_estimate"]
    print(f"first year (load + 12mo) : ${ac['first_year_total_usd_as_deployed']:.2f} as-deployed"
          f"  /  ${ac['first_year_total_usd_after_cleanup']:.2f} after cleanup")
    print(f"report                   : {out_dir / 'latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
