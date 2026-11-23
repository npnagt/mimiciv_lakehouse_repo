#!/usr/bin/env python3
"""Consolidated lakehouse vs data-warehouse comparison.

Merges the measurement reports both repos produce into one proposition scorecard:

  lakehouse (this repo)                 warehouse (mimic_datawarehouse_repo)
  --------------------------------      -----------------------------------------
  docs/storage_footprint/latest.json    docs/storage_footprint/aurora_baseline.json
  docs/cost/latest.json                 (Aurora Pipeline Manifest -- ACU-hrs etc.)
  docs/tti/tti_<...>.json               docs/tti/latest_pg.json
  docs/p5/latest.json                   --

Analysis-only propositions (P1 workflow coverage, P2 integration points) carry
hand-curated numbers with a pointer to their standalone doc; everything else is
pulled live from the JSON above.

    python compare_environments.py
    python compare_environments.py --warehouse-repo ../mimic_datawarehouse_repo --run

Writes docs/comparison/comparison_<UTC>.{json,md} + latest.{json,md}.
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
from mimic_lakehouse import config  # noqa: E402


def _make_console_utf8_safe() -> None:
    """Report files are always written as UTF-8; only the console echo is limited by
    the terminal's encoding (cp1252 on a default Windows console, which can't encode
    some glyphs used in these reports, e.g. an approx-equals sign)."""
    enc = (sys.stdout.encoding or "").lower()
    if enc and enc != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def load_first(*paths: Path, default=None):
    """First readable JSON among candidate paths (per-dataset dir, then legacy top-level)."""
    for p in paths:
        d = load(p)
        if d is not None:
            return d
    return default


def newest(pattern: str):
    files = sorted(glob.glob(pattern))
    return load(Path(files[-1])) if files else None


GB = 10 ** 9   # AWS bills storage/transfer in decimal GB, matching measure_aws_resources.py


def mib(b):
    return round((b or 0) / 1048576, 1)


# Metrics both repos' measure_aws_resources.py --by-run produce (see each script's
# compute_run_statistics) -- the shared vocabulary the run-level comparison is built on.
# propositions is informational, mapping each metric to the P1-P7 cluster it's evidence
# for -- P1-P4 architectural integrity, P5-P7 processing efficiency (see the dissertation's
# proposition table); it does not claim the metric alone proves the proposition.
_RUN_METRICS = [
    ("wall_clock_seconds", "Wall clock per run (s)", "P5"),
    ("total_dpu_seconds", "Total Glue DPU-seconds per run", "P5, P7"),
    ("total_dpu_hours", "Total Glue DPU-hours per run", "P5, P7"),
    ("glue_cost_usd", "Glue compute cost per run (USD)", "P5, P7"),
    ("cloudwatch_bytes_ingested", "CloudWatch bytes ingested per run", "P3, P5"),
    ("job_count", "Jobs / tables loaded per run", "P1, P2"),
    ("failed_count", "Failed jobs per run", "P5, P7"),
    ("total_raw_rows", "Total raw rows processed per run", "P5"),
    ("total_gold_rows", "Total gold rows produced per run", "P3, P4"),
]


def build_by_run_comparison(lh_repo: Path, wh_repo: Path, mode: str = "demo") -> dict:
    """Side-by-side last-N-run resource statistics from both repos' own
    `measure_aws_resources.py --by-run --last-n` reports -- the run-level counterpart to
    build()'s point-in-time proposition scorecard. Needs both repos to have run that
    command at least once for the given --dataset (mode)."""
    lh = load_first(lh_repo / f"docs/cost/{mode}/latest_runs.json", default={})
    wh = load_first(wh_repo / f"docs/cost/{mode}/latest_runs.json", default={})
    lh_stats, wh_stats = lh.get("summary_statistics", {}), wh.get("summary_statistics", {})

    metrics = [
        {
            "metric": key, "label": label, "propositions": props,
            "lakehouse": lh_stats.get(key, {}), "warehouse": wh_stats.get(key, {}),
        }
        for key, label, props in _RUN_METRICS
    ]

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "sources": {
            "lakehouse_by_run_generated": lh.get("generated_utc"),
            "lakehouse_n_runs_reported": lh_stats.get("n_runs"),
            "lakehouse_n_runs_available": lh.get("n_runs_available"),
            "warehouse_by_run_generated": wh.get("generated_utc"),
            "warehouse_n_runs_reported": wh_stats.get("n_runs"),
            "warehouse_n_runs_available": wh.get("n_runs_available"),
        },
        "lakehouse_runs": lh.get("runs", []),
        "warehouse_runs": wh.get("runs", []),
        "lakehouse_current_footprint": lh.get("current_footprint"),
        "warehouse_current_footprint": wh.get("current_footprint"),
        "metrics": metrics,
    }


def _fmt_stat(v):
    if v is None:
        return "—"
    return f"{v:,.3f}" if isinstance(v, float) else f"{v:,}"


def render_by_run_md(r: dict) -> str:
    w = []
    P = w.append
    P("# Lakehouse vs Data Warehouse — resource usage across the last N runs")
    P("")
    s = r["sources"]
    P(f"Generated {r['generated_utc']}.")
    P(f"- **Lakehouse**: {s['lakehouse_n_runs_reported'] or 0} run(s) reported "
      f"(of {s['lakehouse_n_runs_available'] or '?'} available), "
      f"source generated {s['lakehouse_by_run_generated'] or '?'}.")
    P(f"- **Warehouse**: {s['warehouse_n_runs_reported'] or 0} run(s) reported "
      f"(of {s['warehouse_n_runs_available'] or '?'} available), "
      f"source generated {s['warehouse_by_run_generated'] or '?'}.")
    P("")
    P("Supports propositions P1-P7 (see the proposition column per metric). Each statistic "
      "is mean / median / stdev / min / max across that side's last-N full pipeline runs, "
      "computed by each repo's own `measure_aws_resources.py --by-run --last-n <N>` -- "
      "run that in both repos first (same --dataset) to refresh these numbers.")
    P("")
    P("## Detailed data -- one row per full_run_id, both sides")
    P("")
    P("The raw per-run rows behind the statistics below, captured here alongside them so "
      "the detailed data and the cross-run statistics live in one document instead of two "
      "separate per-repo reports. \"CW bytes (group total)\" is every byte the account's "
      "shared Glue log groups ingested during that run's wall-clock window, from any job in "
      "the account; \"CW bytes (attributed)\" is the CloudWatch Logs Insights-computed "
      "subset attributable specifically to that run's own Glue JobRunIds -- see either "
      "repo's measure_aws_resources.py --by-run output for the full attribution "
      "methodology note.")
    P("")
    P("### Lakehouse")
    P("")
    lh_runs = r.get("lakehouse_runs") or []
    if lh_runs:
        w.extend(_render_runs_table(lh_runs))
    else:
        P("No lakehouse run data found -- run `measure_aws_resources.py --by-run` in the "
          "lakehouse repo first.")
    P("")
    P("### Warehouse")
    P("")
    wh_runs = r.get("warehouse_runs") or []
    if wh_runs:
        w.extend(_render_runs_table(wh_runs))
    else:
        P("No warehouse run data found -- run `scripts/measure_aws_resources.py --by-run` "
          "in the warehouse repo first.")
    P("")
    P("## Per-run statistics, lakehouse vs warehouse")
    for m in r["metrics"]:
        P("")
        P(f"### {m['label']}  (`{m['metric']}` — {m['propositions']})")
        P("")
        P("| Environment | n | Mean | Median | Stdev | Min | Max |")
        P("|---|--:|--:|--:|--:|--:|--:|")
        for env_name, d in (("Lakehouse", m["lakehouse"]), ("Warehouse", m["warehouse"])):
            n = d.get("n", 0) or 0
            if not n:
                P(f"| {env_name} | 0 | — | — | — | — | — |")
                continue
            P(f"| {env_name} | {n} | {_fmt_stat(d.get('mean'))} | {_fmt_stat(d.get('median'))} | "
              f"{_fmt_stat(d.get('stdev'))} | {_fmt_stat(d.get('min'))} | {_fmt_stat(d.get('max'))} |")
        lm, wm = m["lakehouse"].get("mean"), m["warehouse"].get("mean")
        if lm is not None and wm not in (None, 0):
            P("")
            P(f"Ratio (lakehouse mean / warehouse mean): {lm / wm:.3f}×")
    P("")
    P("## Current resource footprint (point-in-time, not per-run)")
    P("")
    P("Storage, catalog, and log-retention totals don't have a clean per-run reading on "
      "either side (the underlying AWS metrics are daily-to-hourly and lag) -- these are "
      "each side's current state, for context alongside the per-run statistics above.")
    lf, wf = r.get("lakehouse_current_footprint"), r.get("warehouse_current_footprint")
    if lf:
        P("")
        P(f"**Lakehouse** (measured {lf['measured_at']}):")
        P(f"- S3 physical (all): {human_bytes(lf['s3_physical_bytes'])}  ·  "
          f"Gold live: {human_bytes(lf['s3_gold_live_bytes'])} ({lf['s3_gold_objects']} objects)")
        P(f"- CloudWatch log groups: {human_bytes(lf['cloudwatch_log_bytes_total'])} across "
          f"{len(lf['cloudwatch_log_groups'])} group(s)")
        P(f"- Glue Data Catalog: {lf['glue_data_catalog_objects']} tables  ·  "
          f"Crawlers: {len(lf['glue_crawlers'])}  ·  IAM roles: {lf['iam_role_count']}")
        lf_ac = lf.get("cost_estimate_usd", {}).get("annual_cost_estimate")
        if lf_ac:
            P(f"- Load + 1 year running: ${lf_ac['first_year_total_usd_as_deployed']:.2f} as-deployed "
              f"(load ${lf_ac['load_cost_usd']:.2f} + annual ${lf_ac['annual_steady_state_usd_as_deployed']:.2f})")
    if wf:
        a, s3, cw, iam = wf["aurora"], wf["s3"], wf["cloudwatch_logs"], wf["iam"]
        P("")
        P(f"**Warehouse** (measured {wf['measured_at']}):")
        vol = a["current_volume_bytes"]
        P(f"- Aurora `{a['cluster_id']}` volume: {human_bytes(vol) if vol is not None else 'no datapoints'}  ·  "
          f"ACU-hr since {a['window_start'][:10]}: {a['acu_hours_in_window']:.3f}")
        acu_io = a.get("compute_and_io_cost_usd_in_window")
        storage_cost = a.get("storage_cost_usd_per_month")
        if acu_io is not None:
            P(f"- Aurora cost: ${acu_io:.4f} compute+I/O (${a['acu_cost_usd_in_window']:.4f} ACU + "
              f"${a['io_cost_usd_in_window']:.4f} I/O, {a['io_operations_in_window']:,.0f} requests) "
              f"since {a['window_start'][:10]}, plus "
              + (f"${storage_cost:.4f}/month storage" if storage_cost is not None else "storage cost n/a"))
        P(f"- S3: {human_bytes(s3['total_bytes'])} across {s3['total_objects']} objects")
        P(f"- CloudWatch log groups: {human_bytes(cw['total_bytes'])} across {len(cw['log_groups'])} group(s)")
        P(f"- IAM roles: {len(iam['roles'])}")
        wf_ac = wf.get("cost_estimate_usd", {}).get("annual_cost_estimate")
        if wf_ac:
            P(f"- Load + 1 year running: ${wf_ac['first_year_total_usd']:.2f} "
              f"(load ${wf_ac['load_cost_usd']:.4f} + annual ${wf_ac['annual_steady_state_usd']:.2f})")
    lf_ac = (lf or {}).get("cost_estimate_usd", {}).get("annual_cost_estimate")
    wf_ac = (wf or {}).get("cost_estimate_usd", {}).get("annual_cost_estimate")
    if lf_ac and wf_ac:
        lh_year = lf_ac["first_year_total_usd_as_deployed"]
        wh_year = wf_ac["first_year_total_usd"]
        P("")
        P(f"**Load + 1 year running, side by side**: lakehouse ${lh_year:.2f} vs warehouse "
          f"${wh_year:.2f}" + (f" ({wh_year / lh_year:.2f}× the lakehouse figure)." if lh_year else "."))
    P("")
    return "\n".join(w) + "\n"


def human_bytes(n):
    n = float(n or 0)
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or u == "TiB":
            return f"{n:,.1f} {u}" if u != "B" else f"{int(n):,} B"
        n /= 1024


def human_seconds(s):
    if s is None:
        return "?"
    s = int(s)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _render_runs_table(runs: list[dict]) -> list[str]:
    """One row per full_run_id, mirroring each side's own measure_aws_resources.py
    --by-run detail table -- kept here too so the combined comparison document carries
    the raw per-run data alongside the cross-run statistics, in one place."""
    lines = [
        "| full_run_id | started_at | wall clock | jobs | failed | DPU-s | Cost $ | "
        "CW bytes (group total) | CW bytes (attributed) | raw rows | gold rows |",
        "|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in runs:
        raw_rows = f"{r['total_raw_rows']:,}" if r.get("total_raw_rows") is not None else "—"
        gold_rows = f"{r['total_gold_rows']:,}" if r.get("total_gold_rows") is not None else "—"
        dpu = r.get("total_dpu_seconds")
        dpu_s = f"{dpu:,.1f}" if dpu is not None else "—"
        cost = r.get("glue_cost_usd")
        cost_s = f"${cost:.4f}" if cost is not None else "—"
        cw = r.get("cloudwatch_bytes_ingested")
        cw_s = human_bytes(cw) if cw is not None else "—"
        cw_attr = r.get("cloudwatch_bytes_attributed")
        cw_attr_s = human_bytes(cw_attr) if cw_attr is not None else "—"
        lines.append(
            f"| {r['full_run_id']} | {r.get('started_at') or '?'} | "
            f"{human_seconds(r.get('wall_clock_seconds'))} | {r.get('job_count','?')} | "
            f"{r.get('failed_count','?')} | {dpu_s} | {cost_s} | {cw_s} | {cw_attr_s} | "
            f"{raw_rows} | {gold_rows} |"
        )
    return lines


def _warehouse_cost(wh_runs: dict) -> dict:
    """Warehouse cost figures for the scorecard's Pipeline cost section. Prefers the
    warehouse's own `measure_aws_resources.py --by-run` current_footprint.cost_estimate_usd
    (computed live from real CloudWatch/Aurora metrics -- see that repo's
    build_cost_estimate), falling back to a hand-computed approximation if the warehouse
    hasn't produced that report yet for this dataset."""
    fp = (wh_runs or {}).get("current_footprint") or {}
    live_cost = fp.get("cost_estimate_usd")
    if not live_cost:
        return {
            "one_time_build_debug_usd_approx": 2.04,
            "one_time_components": "APPROXIMATE -- no live warehouse --by-run report found for this "
                                   "dataset (run `scripts/measure_aws_resources.py --by-run` in the "
                                   "warehouse repo for a live figure). Hand-computed: ACU-hrs "
                                   "10.7×$0.12=$1.28 + Glue 1.90 DPU-hr×$0.44=$0.84 + billed I/O "
                                   "1.24M ops×$0.20/M=$0.25 + CW logs ~$0.02",
            "steady_state_monthly_usd": "~$0.07 if Serverless v2 auto-pauses to 0 ACU  /  "
                                        "~$43.9 at a 0.5-ACU floor",
            "one_clean_rebuild_usd_approx": 0.57,
            "annual_cost_estimate": None,
            "live": False,
        }
    ot, orr, sm = live_cost["one_time_cumulative"], live_cost["one_clean_pipeline_run"], live_cost["steady_state_monthly"]
    return {
        "one_time_build_debug_usd": ot["total"],
        "one_time_components": (
            f"LIVE (measured {fp['measured_at']}): Aurora compute+I/O ${ot['aurora_compute_and_io']:.4f} "
            f"+ Glue ${ot['glue_etl_all_runs']:.2f} + CloudWatch ingest ${ot['cloudwatch_log_ingestion']:.4f}"
        ),
        "steady_state_monthly_usd": sm["total"],
        "one_clean_rebuild_usd_approx": orr["total_min"],
        "annual_cost_estimate": live_cost["annual_cost_estimate"],
        "live": True,
    }


def build(lh_repo: Path, wh_repo: Path, mode: str = "demo") -> dict:
    cost = load_first(lh_repo / f"docs/cost/{mode}/latest.json",
                      lh_repo / "docs/cost/latest.json", default={})
    sf = load_first(lh_repo / f"docs/storage_footprint/{mode}/latest.json",
                    lh_repo / "docs/storage_footprint/latest.json", default={})
    p5 = load_first(lh_repo / f"docs/p5/{mode}/latest.json",
                    lh_repo / "docs/p5/latest.json", default={})
    ivr = load(lh_repo / f"docs/iceberg_vs_raw/{mode}/latest.json", {})
    # lakehouse TTI: prefer a report that carries both cold + warm passes
    lh_tti = None
    tti_globs = (sorted(glob.glob(str(lh_repo / f"docs/tti/{mode}/tti_*.json")), reverse=True)
                 + sorted(glob.glob(str(lh_repo / "docs/tti/tti_*.json")), reverse=True))
    for f in tti_globs:
        d = load(Path(f))
        if d and d.get("warm"):
            lh_tti = d
            break
    # warehouse TTI (scripts/measure_time_to_insight_pg.py) is NOT loaded here -- P6 (Ch.1
    # Table 2) is a standalone threshold test of the lakehouse's own unified BI layer with
    # no baseline comparison, so the warehouse side plays no role in this scorecard.
    aurora = load(lh_repo / "docs/storage_footprint/aurora_baseline.json", {})
    wh_runs = load_first(wh_repo / f"docs/cost/{mode}/latest_runs.json", default={})

    ce = cost.get("cost_estimate_usd", {})
    sv = sf.get("structured_vs_unstructured", {})
    lh_struct_live = sv.get("structured", {}).get("live_bytes")
    lh_struct_phys = sv.get("structured", {}).get("physical_bytes")
    wh_struct = aurora.get("structured", {})

    lh_roll = (lh_tti or {}).get("rollup_cold", {})

    def band_line(roll, cold_or_warm):
        a, b, c = roll.get("band_A_flow", 0), roll.get("band_B_attention", 0), roll.get("band_C_lost", 0)
        return f"{a} A / {b} B / {c} C  (p90 {roll.get('overall_p90_ms','?')} ms)"

    props = [
        dict(id="P1", claim="Layered architecture supports more end-to-end workflows",
             metric="workflow coverage (Supported + ½·Partial) / 45",
             lakehouse="88.9%  (35 S / 10 P / 0 U)",
             warehouse="72.2%  (26 S / 13 P / 6 U)",
             verdict="holds — the gap is entirely in the 18 cross-modal workflows",
             evidence="analysis — atlas_P1_workflow_taxonomy.docx (lakehouse repo-verified; "
                      "decoupled baseline scored as-designed, not built)"),
        dict(id="P2", claim="Fewer integration points for cross-modal queries",
             metric="mean onboarding integration points, cross-modal rows",
             lakehouse="≈ 3.3", warehouse="≈ 6.1",
             verdict="holds — mechanism is the shared Glue catalog",
             evidence="analysis — counted from Glue job DAGs + Athena joins in both repos"),
        dict(id="P3", claim="Less physical data duplication (redundancy ratio)",
             metric="structured layer: live bytes / physical bytes / redundancy ratio",
             lakehouse=f"{mib(lh_struct_live)} MiB live / {mib(lh_struct_phys)} MiB phys / 1.0× compacted "
                       f"(gold is the only copy)",
             warehouse=f"{wh_struct.get('live_mib','?')} MiB live / {wh_struct.get('physical_mib','?')} MiB phys / "
                       f"{wh_struct.get('redundancy_multiple','?')}× (staging + warehouse)",
             verdict="holds architecturally — lakehouse eliminates the staging materialization "
                     "(external tables = 0 bytes); on information content it is ~0.15× the warehouse",
             evidence="✅ measured both sides — measure_storage_footprint.py + measure_warehouse_size.py"),
        dict(id="P4", claim="More ad-hoc queries combining structured data with AI outputs",
             metric="45-query catalogue coverage",
             lakehouse="97.8%  (43 answerable, 2 partial, 0 no)",
             warehouse="7.8%  (0 answerable, 7 structured proxy, 38 no path)",
             verdict="holds decisively — NLP tables are in the shared catalog vs absent from Postgres",
             evidence="analysis — atlas_P4_adhoc_query_catalog.docx (2 queries verified live in Athena)"),
        dict(id="P5", claim="Native in-lake join beats externalized two-stage pipeline",
             metric="wall-clock + throughput for a 3-way join + aggregate",
             lakehouse=f"native (Athena/Iceberg): {p5.get('native',{}).get('wall_median_ms','?'):,.0f} ms, "
                       f"{p5.get('native',{}).get('throughput_rows_per_s','?'):,} rows/s",
             warehouse=f"external (Athena UNLOAD + DuckDB): "
                       f"{p5.get('external',{}).get('total_wall_ms_export_plus_one_join','?'):,.0f} ms "
                       f"({p5.get('external',{}).get('throughput_total_rows_per_s','?'):,} rows/s); "
                       f"DuckDB join alone {p5.get('external',{}).get('duckdb_join_median_ms','?'):.0f} ms",
             verdict=("holds — native ~%.1f× faster end to end; the whole penalty is the extract hop, "
                      "not the engine" % ((p5.get('external',{}).get('total_wall_ms_export_plus_one_join', 1) or 1) /
                                          (p5.get('native',{}).get('wall_median_ms', 1) or 1)))
                     if p5 else "not measured",
             evidence="✅ measured — measure_native_vs_external_join.py (12 reps)"),
        dict(id="P6", claim="Unified abstraction layer renders results inside Nielsen's "
                            "sustained-attention band (1-10 s), not the >10 s attention-lost band",
             metric="19-query battery; % within 10 s (sustained attention or faster), p90",
             lakehouse=f"cold {band_line(lh_roll,'cold')}; {lh_roll.get('pct_within_attention','?')}% "
                       f"within 10 s; warm 100% band A (~0.8 s)",
             warehouse="n/a — proposition has no baseline comparison",
             verdict=("PASS -- every query lands at or under 10 s" if lh_roll.get("p6_acceptance_test_passed")
                     else "FAIL -- one or more queries exceeded 10 s") if lh_roll else "not measured",
             evidence="✅ measured — measure_time_to_insight.py (standalone; no baseline required)"),
        dict(id="P7", claim="Less effort to re-execute models when new data arrives",
             metric="incremental refresh vs full reload, re-run wall time",
             lakehouse="agg/OBT + NLP jobs incremental via etl_control — re-run 100–125 s "
                       "(platform floor) vs 183–1,846 s backfill; 2–16× faster",
             warehouse="no incremental mechanism — every refresh is a full TRUNCATE+reload "
                       "(~954 DPU-s, README: “that mechanism isn’t implemented here”)",
             verdict="holds — lakehouse cost scales with what changed, warehouse with total volume",
             evidence="✅ lakehouse verified via Glue run stats; warehouse from its manifest + README"),
        dict(id="P8", claim="Engineers complete tasks faster + lower NASA-TLX with multimodal schemas",
             metric="task completion time + raw NASA-TLX, within-subject",
             lakehouse="—", warehouse="—", verdict="not tested — human study",
             evidence="needs a 5-task battery, a digital NASA-TLX form, counterbalanced design, "
                      "paired t-tests + Cohen's d"),
        dict(id="P9", claim="Practitioners perceive gains outweigh complexity (TAM), high intent to adopt",
             metric="Davis TAM instrument (PU / PEOU / BI) + net-benefit item",
             lakehouse="—", warehouse="—", verdict="not tested — human study",
             evidence="needs the validated TAM survey; ~N=34 per condition for d=0.5 at power 0.8"),
    ]

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "lakehouse_cost": cost.get("generated_utc"),
            "lakehouse_storage": (sf.get("meta") or {}).get("generated_utc") or sf.get("generated_utc"),
            "lakehouse_tti": (lh_tti or {}).get("generated_utc"),
            "lakehouse_p5": p5.get("generated_utc"),
            "lakehouse_iceberg_vs_raw": (ivr.get("meta") or {}).get("generated_utc"),
            "aurora_baseline": aurora.get("measured_utc"),
            "warehouse_by_run": wh_runs.get("generated_utc"),
        },
        "cost": {
            "lakehouse": {
                "one_time_build_debug_usd": ce.get("one_time_build_and_debug", {}).get("total"),
                "one_clean_rebuild_usd": ce.get("one_clean_pipeline_run", {}).get("total_min"),
                "steady_state_monthly_usd": ce.get("steady_state_monthly", {}).get("total_as_deployed"),
                "steady_state_monthly_after_cleanup_usd": ce.get("steady_state_monthly", {}).get("total_after_cleanup"),
                "annual_cost_estimate": ce.get("annual_cost_estimate"),
            },
            "warehouse": _warehouse_cost(wh_runs),
        },
        "propositions": props,
        "iceberg_vs_raw": ivr.get("summary"),
    }


def render_md(r):
    w = []
    P = w.append
    P("# Lakehouse vs Data Warehouse — consolidated comparison")
    P("")
    P(f"Generated {r['generated_utc']}. Sources: " + ", ".join(
        f"{k} {v[:10] if v else '?'}" for k, v in r["sources"].items()))
    P("")
    P("## Proposition scorecard")
    P("")
    P("| P | Claim | Lakehouse | Warehouse | Verdict |")
    P("|---|---|---|---|---|")
    for p in r["propositions"]:
        P(f"| **{p['id']}** | {p['claim']} | {p['lakehouse']} | {p['warehouse']} | {p['verdict']} |")
    P("")
    P("## Evidence status")
    P("")
    P("| P | Metric | Evidence |")
    P("|---|---|---|")
    for p in r["propositions"]:
        P(f"| {p['id']} | {p['metric']} | {p['evidence']} |")
    P("")
    P("## Pipeline cost")
    P("")
    c = r["cost"]
    wc = c["warehouse"]
    wh_live = wc.get("live", False)
    wh_one_time = wc.get("one_time_build_debug_usd", wc.get("one_time_build_debug_usd_approx"))
    wh_rebuild = wc.get("one_clean_rebuild_usd_approx")
    wh_prefix = "" if wh_live else "~"
    P("| | Lakehouse | Warehouse |")
    P("|---|--:|--:|")
    wh_one_time_str = f"{wh_prefix}${wh_one_time:.2f}" if wh_one_time is not None else "n/a"
    P(f"| One-time build + debug | ${c['lakehouse']['one_time_build_debug_usd']:.2f} | "
      f"{wh_one_time_str} |")
    if wh_rebuild is not None:
        P(f"| One clean rebuild | ${c['lakehouse']['one_clean_rebuild_usd']:.2f} | "
          f"{wh_prefix}${wh_rebuild:.4f} |")
    else:
        P(f"| One clean rebuild | ${c['lakehouse']['one_clean_rebuild_usd']:.2f} | "
          f"n/a — not separable from cumulative ACU-hrs without a per-rebuild window |")
    steady = wc["steady_state_monthly_usd"]
    steady_str = f"${steady:.3f}" if isinstance(steady, (int, float)) else str(steady)
    P(f"| Steady-state / month (idle) | ${c['lakehouse']['steady_state_monthly_usd']:.3f} "
      f"(→ ${c['lakehouse']['steady_state_monthly_after_cleanup_usd']:.3f} cleaned) | "
      f"{steady_str} |")
    lh_annual = c["lakehouse"].get("annual_cost_estimate")
    wh_annual = wc.get("annual_cost_estimate")
    if lh_annual:
        lh_year_str = f"${lh_annual['first_year_total_usd_as_deployed']:.2f}"
    else:
        lh_year_str = "n/a"
    if wh_annual:
        wh_year_str = f"{wh_prefix}${wh_annual['first_year_total_usd']:.2f}"
    else:
        wh_year_str = "n/a — no live warehouse --by-run report found"
    P(f"| **Load + 1 year running** | **{lh_year_str}** | **{wh_year_str}** |")
    P("")
    P(f"Warehouse one-time detail ({'live' if wh_live else 'approximate'}): {wc['one_time_components']}")
    P("")
    _render_iceberg_vs_raw(P, r.get("iceberg_vs_raw"))
    return "\n".join(w) + "\n"


def _render_iceberg_vs_raw(P, s: dict | None) -> None:
    """Lakehouse-only section: Gold Iceberg tables vs the raw source .csv.gz archives
    (compare_iceberg_raw_csv.py -- full per-table detail in docs/iceberg_vs_raw/)."""
    P("## Gold Iceberg vs raw source CSV archives (lakehouse)")
    P("")
    if not s:
        P("No report found -- run `compare_iceberg_raw_csv.py` (suite step `raw_compare`).")
        P("")
        return

    def x(v, suffix=""):
        return "n/a" if v is None else f"{v}{suffix}"

    P("Per-row comparison (fact tables over 1M rows hold a 1M-row sample; the raw archive holds "
      "every row). Full per-table detail: `docs/iceberg_vs_raw/<mode>/latest.md`.")
    P("")
    P("| Group | Tables | Raw .csv.gz | Iceberg, full-row equivalent | Iceberg / raw | Iceberg smaller per row |")
    P("|---|--:|--:|--:|--:|--:|")
    for label, key in (("Fact tables", "facts"), ("Dimensions", "dimensions"),
                       ("**All source-loaded**", "all_source_loaded")):
        g = s[key]
        P(f"| {label} | {g['tables']} | {human_bytes(g['raw_csv_gz_bytes'])} | "
          f"{human_bytes(g['iceberg_full_row_equivalent_bytes'])} | {x(g['full_row_ratio_iceberg_over_raw'], '×')} "
          f"({x(g['full_row_change_pct'], '%')}) | {g['tables_iceberg_smaller_per_row']} of "
          f"{g['tables_per_row_comparable']} |")
    nt = s["note_text"]
    P(f"| Note text (as loaded, bytes only) | 2 | {human_bytes(nt['raw_csv_gz_bytes'])} | "
      f"{human_bytes(nt['iceberg_live_bytes'])} | {x(nt['as_loaded_ratio_iceberg_over_raw'], '×')} | -- |")
    gl = s["gold_layer"]
    P("")
    P(f"Whole Gold layer: {gl['tables']} tables, {human_bytes(gl['iceberg_live_bytes'])} live / "
      f"{human_bytes(gl['iceberg_physical_bytes'])} physical. Not a pure format benchmark -- the Gold "
      f"schema adds keys, derived measures and audit columns (see the detail report).")
    if s.get("row_mismatches"):
        P("")
        P(f"Row-count mismatch on {len(s['row_mismatches'])} fully loaded table(s): "
          + ", ".join(f"`{m['table']}` {m['row_delta']:+,}" for m in s["row_mismatches"]) + ".")
    P("")


def main() -> int:
    _make_console_utf8_safe()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    config.add_dataset_arg(ap)
    ap.add_argument("--lakehouse-repo", default=str(REPO))
    ap.add_argument("--warehouse-repo", default=str(REPO.parent / "mimic_datawarehouse_repo"))
    ap.add_argument("--run", action="store_true",
                    help="re-run each side's measurement scripts first (slow; needs both venvs + AWS)")
    ap.add_argument("--out-dir", default=None,
                    help="output dir (default: docs/comparison/<demo|full> for the --dataset)")
    ap.add_argument("--by-run", action="store_true",
                    help="Compare last-N-run RESOURCE statistics (storage/DPU/CloudWatch/cost, from "
                         "each repo's own measure_aws_resources.py --by-run --last-n) instead of the "
                         "point-in-time proposition scorecard -- supports P1-P7. Needs both repos to "
                         "have run that command for this --dataset first. With --run, also re-runs "
                         "both sides' --by-run first.")
    ap.add_argument("--last-n", type=int, default=None,
                    help="With --by-run --run: --last-n passed through to both repos' "
                         "measure_aws_resources.py --by-run (default: 5, or unlimited -- every "
                         "eligible run -- if --since is given without an explicit --last-n).")
    ap.add_argument("--since", default=None,
                    help="With --by-run --run: passed through to both repos' "
                         "measure_aws_resources.py --by-run --since, so only runs that started at "
                         "or after this timestamp are reported (excludes stale/pre-fix runs). "
                         "Accepts the same formats as that flag (e.g. '2026-09-20 02:21:50.915000' "
                         "or an ISO date/datetime). When given without an explicit --last-n, all "
                         "eligible runs are reported instead of being capped at 5.")
    args = ap.parse_args()

    profile = config.dataset_profile(args.dataset)
    if args.out_dir is None:
        args.out_dir = str(REPO / "docs" / "comparison" / profile.mode)

    last_n = args.last_n if args.last_n is not None else (0 if args.since else 5)

    lh, wh = Path(args.lakehouse_repo), Path(args.warehouse_repo)
    if args.by_run:
        if args.run:
            lh_cmd = [sys.executable, "measure_aws_resources.py", "--dataset", profile.dataset,
                      "--by-run", "--last-n", str(last_n)]
            wpy = wh / ".venv" / "Scripts" / "python.exe"
            wpy = str(wpy) if wpy.exists() else sys.executable
            wh_cmd = [wpy, "scripts/measure_aws_resources.py", "--dataset", profile.dataset,
                      "--by-run", "--last-n", str(last_n)]
            if args.since:
                lh_cmd += ["--since", args.since]
                wh_cmd += ["--since", args.since]
            print(f"re-running lakehouse --by-run ({profile.dataset})"
                  f"{' since ' + args.since if args.since else ''} ...")
            subprocess.run(lh_cmd, cwd=lh, check=False)
            print(f"re-running warehouse --by-run{' since ' + args.since if args.since else ''} ...")
            subprocess.run(wh_cmd, cwd=wh, check=False)

        report = build_by_run_comparison(lh, wh, profile.mode)
        report["dataset"] = profile.dataset
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (out / f"by_run_comparison_{ts}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        (out / "latest_by_run_comparison.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        md = render_by_run_md(report)
        (out / f"by_run_comparison_{ts}.md").write_text(md, encoding="utf-8")
        (out / "latest_by_run_comparison.md").write_text(md, encoding="utf-8")
        print(md)
        print(f"written: {out / 'latest_by_run_comparison.md'}")
        return 0

    if args.run:
        print(f"re-running lakehouse measurements ({profile.dataset}) ...")
        for cmd in (["measure_storage_footprint.py", "--dataset", profile.dataset, "--region", "us-east-2",
                     "--aurora-baseline", "docs/storage_footprint/aurora_baseline.json"],
                    ["measure_aws_resources.py", "--dataset", profile.dataset],
                    ["measure_time_to_insight.py", "--dataset", profile.dataset, "--repeats", "5"],
                    ["measure_native_vs_external_join.py", "--dataset", profile.dataset, "--repeats", "12"]):
            subprocess.run([sys.executable, *cmd], cwd=lh, check=False)
        print("re-running warehouse measurements ...")
        wpy = wh / ".venv" / "Scripts" / "python.exe"
        wpy = str(wpy) if wpy.exists() else sys.executable
        # measure_time_to_insight_pg.py is intentionally not re-run here: P6 has no
        # baseline comparison, so build() below doesn't load a warehouse TTI report.
        subprocess.run([wpy, "scripts/measure_warehouse_size.py", "--json", "--dataset", profile.dataset],
                       cwd=wh, check=False)

    report = build(lh, wh, profile.mode)
    report["dataset"] = profile.dataset
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / f"comparison_{ts}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out / "latest.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (out / f"comparison_{ts}.md").write_text(render_md(report), encoding="utf-8")
    (out / "latest.md").write_text(render_md(report), encoding="utf-8")
    print(render_md(report))
    print(f"written: {out / 'latest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
