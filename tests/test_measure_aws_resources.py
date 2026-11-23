"""Tests for measure_aws_resources.py's --by-run mode: reading etl_process_log,
grouping into per-full_run_id summaries, and the cross-run mean/median/stdev stats."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import measure_aws_resources as mar


class FakeAthena:
    """Enough of the Athena client surface for _athena_query_all: one page of results,
    header row included, matching what get_query_results actually returns."""

    def __init__(self, columns, rows, state="SUCCEEDED"):
        self.columns = columns
        self.rows = rows
        self.state = state

    def start_query_execution(self, **kw):
        return {"QueryExecutionId": "q1"}

    def get_query_execution(self, **kw):
        return {"QueryExecution": {"Status": {"State": self.state, "StateChangeReason": "boom"}}}

    def get_query_results(self, **kw):
        header = {"Data": [{"VarCharValue": c} for c in self.columns]}
        data_rows = [{"Data": [{"VarCharValue": v} for v in row]} for row in self.rows]
        return {"ResultSet": {"Rows": [header, *data_rows]}}


ETL_LOG_COLUMNS = [
    "full_run_id", "run_id", "job_name", "process_name", "process_type", "phase", "dataset",
    "start_ts", "end_ts", "execution_seconds", "dpu_seconds", "raw_row_count", "gold_row_count",
    "status", "error_message",
]


def _row(full_run_id, job_name, process_name, process_type, start, end, exec_s, dpu_s,
        raw=None, gold=None, status="SUCCEEDED"):
    return [
        str(full_run_id), f"jr_{job_name}", job_name, process_name, process_type, "C", "full",
        start, end, str(exec_s), str(dpu_s),
        "" if raw is None else str(raw), "" if gold is None else str(gold),
        status, "",
    ]


def test_athena_query_all_parses_header_and_rows():
    athena = FakeAthena(["a", "b"], [["1", "x"], ["2", "y"]])
    rows = mar._athena_query_all(athena, "SELECT a, b FROM t", "s3://x/")
    assert rows == [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}]


def test_athena_query_all_raises_on_failed_query():
    athena = FakeAthena(["a"], [], state="FAILED")
    try:
        mar._athena_query_all(athena, "bad sql", "s3://x/")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "FAILED" in str(exc)


def test_collect_runs_groups_by_full_run_id_and_sums_metrics():
    rows = [
        _row(1, "dim-load-dim_patient-full", "dim_patient", "dim",
             "2026-01-01T00:00:00.000", "2026-01-01T00:01:00.000", 60, 2, raw=364627, gold=364627),
        _row(1, "fact-load-fact_admission-full", "fact_admission", "fact",
             "2026-01-01T00:01:05.000", "2026-01-01T00:05:05.000", 240, 4, raw=546028, gold=546028),
        _row(2, "dim-load-dim_patient-full", "dim_patient", "dim",
             "2026-02-01T00:00:00.000", "2026-02-01T00:02:00.000", 120, 4, raw=364627, gold=364627),
    ]
    athena = FakeAthena(ETL_LOG_COLUMNS, rows)
    runs = mar.collect_runs(athena, "s3://x/", "mimic4_db_business_full")

    assert [r["full_run_id"] for r in runs] == [1, 2]
    run1 = runs[0]
    assert run1["job_count"] == 2
    assert run1["succeeded_count"] == 2
    assert run1["failed_count"] == 0
    assert run1["total_dpu_seconds"] == 6.0
    assert run1["total_raw_rows"] == 364627 + 546028
    assert run1["total_gold_rows"] == 364627 + 546028
    assert run1["started_at"] == "2026-01-01T00:00:00.000"
    assert run1["completed_at"] == "2026-01-01T00:05:05.000"
    assert run1["wall_clock_seconds"] == 305.0
    assert set(run1["by_process_type"]) == {"dim", "fact"}
    assert run1["by_process_type"]["dim"]["count"] == 1

    run2 = runs[1]
    assert run2["job_count"] == 1
    assert run2["total_dpu_seconds"] == 4.0


def test_collect_runs_handles_missing_row_counts_and_failed_jobs():
    rows = [
        _row(5, "agg-refresh-agg_admission_daily-full", "agg_admission_daily", "agg",
             "2026-01-01T00:00:00.000", "2026-01-01T00:01:00.000", 60, 2, raw=None, gold=1200),
        _row(5, "agg-refresh-agg_icu_fluid_balance_daily-full", "agg_icu_fluid_balance_daily", "agg",
             "2026-01-01T00:01:00.000", "2026-01-01T00:16:00.000", 900, 30, status="FAILED"),
    ]
    athena = FakeAthena(ETL_LOG_COLUMNS, rows)
    runs = mar.collect_runs(athena, "s3://x/", "mimic4_db_business_full")

    assert len(runs) == 1
    r = runs[0]
    assert r["failed_count"] == 1
    assert r["succeeded_count"] == 1
    assert r["total_raw_rows"] is None  # neither row has a raw_row_count
    assert r["total_gold_rows"] == 1200  # only the succeeded row has one


def test_stats_mean_median_stdev():
    d = mar._stats([10.0, 20.0, 30.0])
    assert d["n"] == 3
    assert d["mean"] == 20.0
    assert d["median"] == 20.0
    assert d["stdev"] == 10.0
    assert d["min"] == 10.0
    assert d["max"] == 30.0


def test_stats_single_value_has_no_stdev():
    d = mar._stats([42.0])
    assert d["n"] == 1
    assert d["mean"] == 42.0
    assert d["stdev"] is None


def test_stats_empty_list():
    d = mar._stats([])
    assert d["n"] == 0
    assert d["mean"] is None


def test_stats_ignores_none_values():
    d = mar._stats([10.0, None, 30.0])
    assert d["n"] == 2
    assert d["mean"] == 20.0


def test_compute_run_statistics_covers_every_headline_metric():
    runs = [
        {"wall_clock_seconds": 100.0, "total_dpu_seconds": 10.0, "total_execution_seconds": 90.0,
         "glue_cost_usd": 0.001, "job_count": 5, "failed_count": 0,
         "total_raw_rows": 1000, "total_gold_rows": 1000},
        {"wall_clock_seconds": 200.0, "total_dpu_seconds": 20.0, "total_execution_seconds": 180.0,
         "glue_cost_usd": 0.002, "job_count": 6, "failed_count": 1,
         "total_raw_rows": 2000, "total_gold_rows": 1900},
    ]
    stats = mar.compute_run_statistics(runs)
    assert stats["n_runs"] == 2
    assert stats["wall_clock_seconds"]["mean"] == 150.0
    assert stats["job_count"]["median"] == 5.5
    assert stats["total_gold_rows"]["max"] == 1900


def test_render_runs_md_includes_detail_and_statistics_sections():
    report = {
        "generated_utc": "2026-01-01T00:00:00+00:00",
        "dataset": "fulldataset",
        "gold_database": "mimic4_db_business_full",
        "runs": [{
            "full_run_id": 1, "started_at": "2026-01-01T00:00:00.000",
            "completed_at": "2026-01-01T00:05:00.000", "wall_clock_seconds": 300.0,
            "job_count": 2, "succeeded_count": 2, "failed_count": 0,
            "total_dpu_seconds": 6.0, "total_execution_seconds": 300.0, "glue_cost_usd": 0.0007,
            "total_raw_rows": 910655, "total_gold_rows": 910655,
            "by_process_type": {"dim": {"count": 1, "dpu_seconds": 2.0, "execution_seconds": 60.0, "cost_usd": 0.0002},
                                "fact": {"count": 1, "dpu_seconds": 4.0, "execution_seconds": 240.0, "cost_usd": 0.0005}},
            "jobs": [],
        }],
        "summary_statistics": mar.compute_run_statistics([{
            "wall_clock_seconds": 300.0, "total_dpu_seconds": 6.0, "total_execution_seconds": 300.0,
            "glue_cost_usd": 0.0007, "job_count": 2, "failed_count": 0,
            "total_raw_rows": 910655, "total_gold_rows": 910655,
        }]),
    }
    md = mar.render_runs_md(report)
    assert "# Lakehouse pipeline -- resource usage by full run" in md
    assert "## Detailed data" in md
    assert "## Statistical analysis across runs" in md
    assert "full_run_id 1" in md
    assert "910,655" in md
    # single run -> stdev column should read as an em dash, not a fabricated 0
    assert "—" in md


def test_human_seconds_formats_by_magnitude():
    assert mar.human_seconds(45) == "45s"
    assert mar.human_seconds(125) == "2m05s"
    assert mar.human_seconds(3725) == "1h02m"
    assert mar.human_seconds(None) == "?"
