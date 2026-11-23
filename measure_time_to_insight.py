#!/usr/bin/env python3
"""Time-to-insight (P6) test harness for the unified Gold-schema BI layer.

P6 (dissertation Ch.1 Table 2): "Unified abstraction layer supports rendering of
results inside Nielsen's 'sustained attention' band (1-10 seconds), rather than the
>10-second 'attention lost' band." Acceptance: queries return within the 1-10 s
sustained-attention band (or faster). This is a standalone threshold test of the
lakehouse's own unified BI layer -- there is no baseline comparison for this
proposition (no warehouse-side counterpart is measured or required).

This measures the query side of that -- every representative analytical question
run as ONE statement through Athena over the Glue catalog (the unified layer the
repo actually provides), with the full server-side phase breakdown, the client
result fetch, and a fixed render allowance:

    time_to_insight = TotalExecutionTimeInMillis    (queue + planning + engine + service)
                    + client GetQueryResults fetch
                    + --render-budget-ms            (fixed BI render allowance, default 500)

Each query runs --repeats times (default 200, a confirmatory sample size exceeding the
pre-registered power analysis); the first run is discarded (metadata warm) and the
median / p90 / max of the rest is bucketed into a Nielsen band. A cold pass (result
reuse OFF) and a warm pass (reuse ON) are both measured. A bare "SELECT 1" gives the
Athena fixed floor.

    python measure_time_to_insight.py                 # cold + warm, 200 repeats
    python measure_time_to_insight.py --repeats 8 --reuse off   # quick exploratory check
    python measure_time_to_insight.py --only T5,T6    # just the cross-modal tiers

Run it 3x at different times of day -- Athena is multi-tenant and execution time
swings 2-3x. Outputs docs/tti/tti_<UTC>.{json,md} + latest.{json,md}.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from botocore.exceptions import ClientError

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from mimic_lakehouse import config as _cfg  # noqa: E402


def _make_console_utf8_safe() -> None:
    """Report files are always written as UTF-8; only the console echo is limited by
    the terminal's encoding (cp1252 on a default Windows console, which can't encode
    some glyphs used in this report, e.g. the reuse-cycle arrow)."""
    enc = (sys.stdout.encoding or "").lower()
    if enc and enc != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def env(key, default=None):
    return _cfg.get(key, default)

DB = "mimic4_db_business"

# Nielsen 1993 response-time limits
BAND_FLOW = 1000       # < 1 s   -- flow of thought uninterrupted
BAND_ATTENTION = 10000  # < 10 s  -- sustained attention; >= 10 s attention lost

# ---------------------------------------------------------------------------------------
# The battery: representative "insights" from the P1 taxonomy / P4 catalogue, tiered by
# query shape. Every one returns a small (<= a few hundred row) aggregate -- what a BI
# visual actually binds to.
# ---------------------------------------------------------------------------------------
QUERIES = [
    ("floor", "T0", "Athena fixed floor (no table)",
     "SELECT 1"),

    ("T1a", "T1", "Admission volume trend by month",
     f"SELECT year_month, sum(admit_count) admits FROM {DB}.agg_admission_monthly GROUP BY 1 ORDER BY 1"),
    ("T1b", "T1", "Case mix by admission type",
     f"SELECT admission_type, count(*) n FROM {DB}.fact_admission GROUP BY 1 ORDER BY 2 DESC"),

    ("T2a", "T2", "30-day readmission rate by DRG severity (raw join)",
     f"SELECT d.drg_severity, count(*) n, round(avg(CAST(a.is_readmission_flag AS double)), 3) readmit "
     f"FROM {DB}.fact_admission a JOIN {DB}.fact_drg_assignment d USING (hadm_id) "
     f"WHERE d.drg_severity IS NOT NULL GROUP BY 1 ORDER BY 1"),
    ("T2b", "T2", "Abnormal-lab burden per admission type (raw join)",
     f"SELECT a.admission_type, count(*) labs, round(avg(CAST(l.is_abnormal_flag AS double)), 3) abn_rate "
     f"FROM {DB}.fact_lab_result l JOIN {DB}.fact_admission a USING (hadm_id) GROUP BY 1 ORDER BY 3 DESC"),

    ("T3a", "T3", "Abnormal vs normal lab counts (108k-row scan)",
     f"SELECT is_abnormal_flag, count(*) n FROM {DB}.fact_lab_result GROUP BY 1"),
    ("T3b", "T3", "Medication-administration volume + reach (36k-row scan)",
     f"SELECT count(*) admins, count(DISTINCT hadm_id) admissions FROM {DB}.fact_medication_administration"),
    ("T3c", "T3", "Positive blood-culture rate by month",
     f"SELECT chart_date_key / 100 AS ym, count(*) tests, "
     f"round(avg(CAST(is_positive_culture_flag AS double)), 3) pos_rate "
     f"FROM {DB}.fact_microbiology_result GROUP BY 1 ORDER BY 1"),

    ("T4a", "T4", "Patient-360 cohort filter + rollup (pre-joined OBT)",
     f"SELECT gender, had_icu_stay, count(*) patients, round(avg(age_at_admission), 1) mean_age "
     f"FROM {DB}.obt_admission_features GROUP BY 1, 2 ORDER BY 1, 2"),
    ("T4b", "T4", "Readmission by DRG severity (via OBT -- compare to T2a)",
     f"SELECT max_drg_severity, count(*) n, round(avg(CAST(is_readmission_flag AS double)), 3) readmit "
     f"FROM {DB}.obt_admission_features WHERE max_drg_severity IS NOT NULL GROUP BY 1 ORDER BY 1"),
    ("T4c", "T4", "ICU stay features summary (pre-joined OBT)",
     f"SELECT first_careunit, count(*) stays, round(avg(los), 2) mean_los_days, "
     f"round(avg(abnormal_chart_rate), 3) abn_chart FROM {DB}.obt_icu_stay_features GROUP BY 1 ORDER BY 2 DESC"),

    ("T5a", "T5", "30-day readmission by discharge-note tobacco_use (structured x NLP)",
     f"SELECT n.tobacco_use, count(*) admits, round(avg(CAST(a.is_readmission_flag AS double)), 3) readmit "
     f"FROM {DB}.fact_discharge_note_nlp n JOIN {DB}.fact_admission a USING (subject_id, hadm_id) "
     f"GROUP BY 1 ORDER BY 2 DESC"),
    ("T5b", "T5", "LOS by note-derived obesity_level (structured x NLP)",
     f"SELECT n.obesity_level, count(*) admits, round(avg(o.hospital_los_hours), 1) mean_los_hr "
     f"FROM {DB}.fact_discharge_note_nlp n JOIN {DB}.obt_admission_features o USING (hadm_id) "
     f"GROUP BY 1 ORDER BY 1"),
    ("T5c", "T5", "SDOH burden cross-tab (structured x NLP)",
     f"SELECT n.tobacco_use, n.alcohol_use, count(*) n FROM {DB}.fact_discharge_note_nlp n "
     f"JOIN {DB}.fact_admission a USING (hadm_id) GROUP BY 1, 2 ORDER BY 3 DESC"),

    ("T6a", "T6", "Radiology-reported disorders, ranked (cross-modal JSON UNNEST)",
     f"SELECT json_extract_scalar(dj, '$.text') disorder, "
     f"json_extract_scalar(dj, '$.negated') negated, count(*) n "
     f"FROM {DB}.fact_radiology_note_nlp r "
     f"CROSS JOIN UNNEST(CAST(json_parse(r.disorders) AS ARRAY(JSON))) AS t(dj) "
     f"GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 25"),
    ("T6b", "T6", "Imaging modality mix per admission (cross-modal JSON x structured)",
     f"SELECT json_extract_scalar(pj, '$.modality') modality, count(DISTINCT r.hadm_id) admits, count(*) exams "
     f"FROM {DB}.fact_radiology_note_nlp r "
     f"CROSS JOIN UNNEST(CAST(json_parse(r.radiology_procedure_types) AS ARRAY(JSON))) AS t(pj) "
     f"JOIN {DB}.fact_admission a ON a.hadm_id = r.hadm_id GROUP BY 1 ORDER BY 3 DESC"),
    ("T6c", "T6", "Radiology ICD codes vs coded diagnoses (cross-modal concordance)",
     f"SELECT json_extract_scalar(ij, '$.code') rad_code, "
     f"count(DISTINCT r.hadm_id) rad_admits, count(DISTINCT fd.hadm_id) also_coded "
     f"FROM {DB}.fact_radiology_note_nlp r "
     f"CROSS JOIN UNNEST(CAST(json_parse(r.icd_codes) AS ARRAY(JSON))) AS t(ij) "
     f"LEFT JOIN {DB}.fact_diagnosis fd ON fd.hadm_id = r.hadm_id "
     f"AND fd.icd_code = replace(json_extract_scalar(ij, '$.code'), '.', '') "
     f"GROUP BY 1 ORDER BY 2 DESC LIMIT 25"),

    ("T7a", "T7", "Chart-observation volume + reach (669k-row scan)",
     f"SELECT count(*) rows, count(DISTINCT hadm_id) admissions, count(DISTINCT subject_id) patients "
     f"FROM {DB}.fact_chart_observation"),
    ("T7b", "T7", "Charted-value abnormality rate by month (669k-row scan + group)",
     f"SELECT chart_date_key / 100 AS ym, count(*) obs, "
     f"round(avg(CAST(is_abnormal_flag AS double)), 3) abn_rate "
     f"FROM {DB}.fact_chart_observation GROUP BY 1 ORDER BY 1"),
    ("T7c", "T7", "Instability proxy: non-null numeric vitals per ICU stay (669k-row scan)",
     f"SELECT stay_id, count(*) numeric_obs FROM {DB}.fact_chart_observation "
     f"WHERE value_num IS NOT NULL AND stay_id IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 25"),
]

TIER_LABEL = {
    "T0": "Athena floor", "T1": "structured, single table", "T2": "structured join",
    "T3": "event-fact aggregation", "T4": "wide pre-joined OBT", "T5": "structured x NLP",
    "T6": "cross-modal JSON", "T7": "big event-fact scan",
}


def human(n):
    n = float(n or 0)
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or u == "TiB":
            return f"{n:,.0f} {u}" if u == "B" else f"{n:,.1f} {u}"
        n /= 1024


def band(ms):
    if ms < BAND_FLOW:
        return "A"
    if ms < BAND_ATTENTION:
        return "B"
    return "C"


def run_once(ath, sql, output, workgroup, reuse):
    """One execution. Returns per-phase ms + fetch ms + scan + reused flag."""
    kw = dict(QueryString=sql, ResultConfiguration={"OutputLocation": output}, WorkGroup=workgroup)
    if reuse:
        kw["ResultReuseConfiguration"] = {"ResultReuseByAgeConfiguration": {"Enabled": True, "MaxAgeInMinutes": 60}}
    else:
        kw["ResultReuseConfiguration"] = {"ResultReuseByAgeConfiguration": {"Enabled": False}}
    qid = ath.start_query_execution(**kw)["QueryExecutionId"]
    while True:
        ex = ath.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        st = ex["Status"]["State"]
        if st in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.4)
    if st != "SUCCEEDED":
        return {"ok": False, "reason": ex["Status"].get("StateChangeReason")}
    s = ex.get("Statistics", {})
    t0 = time.time()
    try:
        res = ath.get_query_results(QueryExecutionId=qid, MaxResults=1000)
        n_rows = len(res["ResultSet"]["Rows"]) - 1
    except ClientError:
        n_rows = None
    fetch_ms = int((time.time() - t0) * 1000)
    reused = (ex.get("Statistics", {}).get("ResultReuseInformation") or {}).get("ReusedPreviousResult", False)
    return {
        "ok": True,
        "queue_ms": s.get("QueryQueueTimeInMillis", 0),
        "planning_ms": s.get("QueryPlanningTimeInMillis", 0),
        "engine_ms": s.get("EngineExecutionTimeInMillis", 0),
        "service_ms": s.get("ServiceProcessingTimeInMillis", 0),
        "total_ms": s.get("TotalExecutionTimeInMillis", 0),
        "fetch_ms": fetch_ms,
        "scanned_bytes": s.get("DataScannedInBytes", 0),
        "rows": n_rows,
        "reused": reused,
    }


def measure_query(ath, qid, sql, output, workgroup, reuse, repeats, render_ms):
    runs = []
    for i in range(repeats):
        r = run_once(ath, sql, output, workgroup, reuse)
        r["run"] = i
        if not r["ok"]:
            return {"error": r["reason"], "runs": runs}
        r["tti_ms"] = r["total_ms"] + r["fetch_ms"] + render_ms
        runs.append(r)
    scored = runs[1:] if len(runs) > 1 else runs  # drop metadata-warm first run
    tti = sorted(x["tti_ms"] for x in scored)

    def pctl(vals, p):  # nearest-rank on a 0-indexed sorted list
        return vals[min(len(vals) - 1, round(p * (len(vals) - 1)))]

    return {
        "runs": runs,
        "scored_runs": len(scored),
        "tti_median_ms": int(statistics.median(tti)),
        "tti_p90_ms": int(pctl(tti, 0.9)),
        "tti_max_ms": int(tti[-1]),
        "total_median_ms": int(statistics.median(sorted(x["total_ms"] for x in scored))),
        "engine_median_ms": int(statistics.median(sorted(x["engine_ms"] for x in scored))),
        "queue_median_ms": int(statistics.median(sorted(x["queue_ms"] for x in scored))),
        "planning_median_ms": int(statistics.median(sorted(x["planning_ms"] for x in scored))),
        "fetch_median_ms": int(statistics.median(sorted(x["fetch_ms"] for x in scored))),
        "scanned_bytes": scored[-1]["scanned_bytes"],
        "rows": scored[-1]["rows"],
        "any_reused": any(x["reused"] for x in scored),
        "band": band(int(statistics.median(tti))),
    }


def main() -> int:
    _make_console_utf8_safe()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _cfg.add_dataset_arg(ap)
    ap.add_argument("--region", default=env("AWS_REGION", "us-east-2"))
    ap.add_argument("--workgroup", default=env("ATHENA_WORKGROUP", "primary"))
    ap.add_argument("--athena-output", default=None, help="default s3://<gold-bucket>/athena-results/")
    ap.add_argument("--gold-bucket", default=None, help="Iceberg gold bucket (default: from --dataset)")
    ap.add_argument("--gold-database", default=None, help="Iceberg gold database (default: from --dataset)")
    ap.add_argument("--repeats", type=int, default=200,
                    help="executions per query, first discarded (default: 200, "
                         "confirmatory; pass a smaller value, e.g. 5, for a quick "
                         "exploratory check)")
    ap.add_argument("--reuse", choices=["off", "on", "both"], default="both",
                    help="cold (reuse off), warm (reuse on), or both passes")
    ap.add_argument("--render-budget-ms", type=int, default=500,
                    help="fixed BI render allowance added to data-ready time (default 500)")
    ap.add_argument("--only", default=None, help="comma-separated tier or query ids (e.g. T5,T6 or T6b)")
    ap.add_argument("--out-dir", default=None,
                    help="output dir (default: docs/tti/<demo|full> for the --dataset)")
    ap.add_argument("--label", default=None, help="tag for this run (e.g. 'morning')")
    args = ap.parse_args()

    profile = _cfg.dataset_profile(args.dataset)
    gold_db = args.gold_database or profile.gold_database
    args.gold_bucket = args.gold_bucket or profile.gold_bucket
    if args.out_dir is None:
        args.out_dir = str(REPO_ROOT / "docs" / "tti" / profile.mode)

    ath = _cfg.RefreshingClient("athena", args.region)
    output = args.athena_output or f"s3://{args.gold_bucket}/athena-results/"

    want = None
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
    # the QUERIES templates use the token DB; retarget them at this dataset's gold DB
    battery = [
        (qid, tier, label, sql.replace(DB, gold_db))
        for (qid, tier, label, sql) in QUERIES
        if not want or qid in want or tier in want or qid == "floor"
    ]

    passes = ["off", "on"] if args.reuse == "both" else [args.reuse]
    print(f"time-to-insight :: {gold_db} via Athena/{args.workgroup} :: {len(battery)} queries "
          f"x {args.repeats} repeats x {len(passes)} pass(es) :: render budget {args.render_budget_ms} ms")
    print(f"Nielsen bands   :: A < {BAND_FLOW} ms (flow)  |  B {BAND_FLOW}-{BAND_ATTENTION} ms (sustained attention)  "
          f"|  C >= {BAND_ATTENTION} ms (attention lost)")
    print("P6 acceptance   :: queries land in A or B (<=10 s) -- standalone test, no baseline comparison\n")

    results = {"cold": [], "warm": []}
    for pass_name, reuse in [("cold", False)] if passes == ["off"] else \
            ([("warm", True)] if passes == ["on"] else [("cold", False), ("warm", True)]):
        print(f"=== {pass_name} pass (result reuse {'ON' if reuse else 'OFF'}) ===")
        for qid, tier, label, sql in battery:
            m = measure_query(ath, qid, sql, output, args.workgroup, reuse, args.repeats, args.render_budget_ms)
            if "error" in m:
                print(f"  {qid:6} {tier}  FAILED  {m['error']}")
                results[pass_name].append({"id": qid, "tier": tier, "label": label, "error": m["error"]})
                continue
            m.update(id=qid, tier=tier, label=label, sql=sql)
            results[pass_name].append(m)
            print(f"  {qid:6} {tier}  {m['band']}  tti med {m['tti_median_ms']:>6} ms  "
                  f"(p90 {m['tti_p90_ms']:>6})  total {m['total_median_ms']:>5}  fetch {m['fetch_median_ms']:>4}  "
                  f"scan {human(m['scanned_bytes']):>10}  {m['rows']} rows"
                  + ("  [reused]" if m["any_reused"] else ""))
        print()

    # rollup on the cold pass (the honest number for a novel question)
    primary = results["cold"] or results["warm"]
    ins = [r for r in primary if "band" in r and r["id"] != "floor"]
    floor = next((r for r in primary if r["id"] == "floor"), None)
    counts = {b: sum(1 for r in ins if r["band"] == b) for b in ("A", "B", "C")}
    p90_all = sorted(r["tti_median_ms"] for r in ins)
    rollup = {
        "queries_scored": len(ins),
        "band_A_flow": counts["A"],
        "band_B_attention": counts["B"],
        "band_C_lost": counts["C"],
        "pct_within_attention": round(100 * (counts["A"] + counts["B"]) / len(ins), 1) if ins else None,
        "pct_within_flow": round(100 * counts["A"] / len(ins), 1) if ins else None,
        "worst_query_p90_ms": max((r["tti_p90_ms"] for r in ins), default=None),
        "overall_p90_ms": p90_all[min(len(p90_all) - 1, round(0.9 * (len(p90_all) - 1)))] if p90_all else None,
        "slowest": sorted(((r["tti_median_ms"], r["id"], r["label"]) for r in ins), reverse=True)[:3],
        "athena_floor_ms": floor["tti_median_ms"] if floor and "tti_median_ms" in floor else None,
        "p6_acceptance_test_passed": counts["C"] == 0 if ins else None,
    }

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": args.dataset,
        "region": args.region, "workgroup": args.workgroup, "database": gold_db,
        "label": args.label,
        "params": {"repeats": args.repeats, "render_budget_ms": args.render_budget_ms,
                   "band_flow_ms": BAND_FLOW, "band_attention_ms": BAND_ATTENTION},
        "rollup_cold": rollup,
        "cold": results["cold"],
        "warm": results["warm"],
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out_dir / f"tti_{ts}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = render_md(report)
    (out_dir / f"tti_{ts}.md").write_text(md, encoding="utf-8")
    (out_dir / "latest.md").write_text(md, encoding="utf-8")

    print("=" * 64)
    print(f"cold pass: {rollup['pct_within_attention']}% within Nielsen's sustained-attention band (<=10 s), "
          f"{rollup['pct_within_flow']}% within flow (<1 s); overall p90 {rollup['overall_p90_ms']} ms")
    print(f"Athena floor (SELECT 1): {rollup['athena_floor_ms']} ms")
    print(f"P6 acceptance test: {'PASS' if rollup['p6_acceptance_test_passed'] else 'FAIL'} "
          f"({rollup['band_C_lost']} of {rollup['queries_scored']} quer{'y' if rollup['queries_scored']==1 else 'ies'} "
          f"lost the attention band, >10 s)")
    print(f"report: {out_dir / 'latest.md'}")
    return 0 if rollup["p6_acceptance_test_passed"] else 1


def render_md(r):
    w = []
    P = w.append
    ro = r["rollup_cold"]
    P("# Time-to-insight (P6) -- unified Gold-schema BI layer")
    P("")
    P(f"- **Generated:** {r['generated_utc']}"
      + (f"  ·  label `{r['label']}`" if r["label"] else ""))
    P(f"- **Layer under test:** Athena over the Glue Data Catalog (`{r['database']}`), "
      f"workgroup `{r['workgroup']}`, {r['region']}")
    P(f"- **time_to_insight** = TotalExecutionTimeInMillis + client result fetch + "
      f"{r['params']['render_budget_ms']} ms render allowance")
    P(f"- **Repeats:** {r['params']['repeats']} per query, first discarded; median / p90 / max of the rest")
    P(f"- **Nielsen bands:** A < {r['params']['band_flow_ms']} ms (flow) · "
      f"B {r['params']['band_flow_ms']}-{r['params']['band_attention_ms']} ms (sustained attention) · "
      f"C >= {r['params']['band_attention_ms']} ms (attention lost)")
    P(f"- **P6 acceptance test:** results land in A or B, i.e. <= 10 s (sustained attention or faster), "
      f"not C (>10 s, attention lost). Standalone test of the lakehouse's unified BI layer -- "
      f"**no baseline comparison** is part of this proposition.")
    P("")
    P("## Result (cold pass -- result reuse OFF, the honest number for a novel question)")
    P("")
    P(f"| Metric | Value |")
    P(f"|---|--:|")
    P(f"| **P6 acceptance test** | **{'PASS' if ro['p6_acceptance_test_passed'] else 'FAIL'}** |")
    P(f"| Queries scored | {ro['queries_scored']} |")
    P(f"| Band A -- flow (< 1 s) | **{ro['band_A_flow']}** |")
    P(f"| Band B -- sustained attention (1-10 s) | **{ro['band_B_attention']}** |")
    P(f"| Band C -- attention lost (>= 10 s) | **{ro['band_C_lost']}** |")
    P(f"| Within sustained-attention band or faster (A or B, <=10 s) | **{ro['pct_within_attention']}%** |")
    P(f"| Within flow band (A) | {ro['pct_within_flow']}% |")
    P(f"| Overall p90 | {ro['overall_p90_ms']} ms |")
    P(f"| Athena fixed floor (`SELECT 1`) | {ro['athena_floor_ms']} ms |")
    P("")
    if ro["slowest"]:
        P("Slowest three: " + "; ".join(f"`{i}` {lbl} ({ms} ms)" for ms, i, lbl in ro["slowest"]) + ".")
        P("")
    for pass_name in ("cold", "warm"):
        rows = r.get(pass_name) or []
        if not rows:
            continue
        P(f"## {pass_name.capitalize()} pass -- per query")
        P("")
        P("| id | tier | insight | band | tti median | p90 | queue | plan | engine | fetch | scanned | rows |")
        P("|---|---|---|:--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        for m in rows:
            if "error" in m:
                P(f"| `{m['id']}` | {m['tier']} | {m['label']} | FAIL | | | | | | | | |")
                continue
            P(f"| `{m['id']}` | {m['tier']} ({TIER_LABEL.get(m['tier'],'')}) | {m['label']} | "
              f"**{m['band']}** | {m['tti_median_ms']} ms | {m['tti_p90_ms']} | {m['queue_median_ms']} | "
              f"{m['planning_median_ms']} | {m['engine_median_ms']} | {m['fetch_median_ms']} | "
              f"{human(m['scanned_bytes'])} | {m['rows']}"
              + ("  ↺" if m.get("any_reused") else "") + " |")
        P("")
    P("## Method & caveats")
    P("")
    P("- **Cold vs warm.** The cold pass sets `ResultReuseByAgeConfiguration.Enabled=false` so every "
      "run recomputes -- this is what a genuinely novel ad-hoc question costs. The warm pass turns "
      "reuse on; an identical repeat then returns from cache (marked ↺) in well under a second.")
    P("- **Athena floor.** `SELECT 1` measures unavoidable queue + planning + service overhead. Simple "
      "queries land in band B largely because of this floor, not the data volume.")
    P("- **Render allowance.** A fixed 500 ms stands in for BI-tool render of a small (<= a few "
      "hundred row) aggregate; real chart libraries draw that in 10-50 ms, so 500 ms is conservative "
      "and covers tool/network overhead. Swap in a measured number if a BI tool is instrumented.")
    P("- **Multi-tenancy.** Athena execution time varies 2-3x with cluster load; run this battery at "
      "3 different times and compare the distributions.")
    P("- **Compaction state.** Small-file fragmentation (many small Parquet files per partition, "
      "before an `OPTIMIZE ... REWRITE DATA USING BIN_PACK` pass) adds scan latency independent of "
      "row count -- these numbers are only comparable to another run against a Gold layer in the "
      "same compaction state. Check `docs/storage_footprint/<demo|full>/latest.md`, generated "
      f"against the same `{r['dataset']}` dataset, for the physical file count/layout this run's "
      "numbers were measured against; re-run against a freshly compacted vs. un-compacted table to "
      "quantify the tax directly.")
    P("- **No baseline comparison.** P6 is a standalone threshold test of this repo's unified BI "
      "layer against the fixed 10 s Nielsen sustained-attention bound -- it does not claim or require "
      "that a decoupled warehouse is slower. (For context only, `mimic_datawarehouse_repo` ships its "
      "own `scripts/measure_time_to_insight_pg.py`, kept as a separate, non-P6 supplementary tool "
      "since T5-T7's NLP-derived tiers have no equivalent there at all.)")
    P("")
    P("## Reproduce")
    P("")
    P("```")
    P("python measure_time_to_insight.py                      # cold + warm, 200 repeats")
    P("python measure_time_to_insight.py --only T5,T6 --repeats 8   # quick exploratory check")
    P("```")
    P("")
    return "\n".join(w) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
