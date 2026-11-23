#!/usr/bin/env python3
"""One-shot driver for the P1-P7 measurement/comparison suite (docs/measurement_readme.md).

Runs every script in that runbook, in the order compare_environments.py needs (it reads
the other scripts' latest*.json output, so it must run last), across both this repo and
the sibling mimic_datawarehouse_repo. Each step's console output is streamed live here
AND saved to logs/<job_name>_<local-timestamp>.log -- lakehouse steps in this repo's
logs/, warehouse steps in the warehouse repo's logs/ -- matching the per-job log
convention in docs/measurement_readme.md. The driver's own combined output (preflight,
every step's banner and output, final summary) is also saved, to this repo's
logs/run_measurement_suite_<local-timestamp>.log.

Before running anything, checks that no Glue job for this --dataset is currently
RUNNING/STARTING/WAITING on either side. Measuring mid-pipeline silently captures a
half-loaded Gold layer / warehouse schema (see the 2026-09-20 incident in
docs/measurement_readme.md, where this exact thing produced a DuckDB crash and several
hours of unusable numbers). --force skips this check.

Steps (see --only):
  storage           measure_storage_footprint.py            (P3)
  fmt_measure       measure_parquet_comparison.py           (Iceberg vs Parquet vs CSV, per table)
  fmt_compare       compare_parquet_iceberg.py               (reads fmt_measure's JSON; needs fmt_measure first)
  raw_compare       compare_iceberg_raw_csv.py               (all Gold tables: rows, Iceberg vs raw source
                                                              .csv.gz, + fmt_compare's Parquet/CSV figures;
                                                              reads storage's and fmt_compare's JSON)
  join              measure_native_vs_external_join.py      (P5)
  tti               measure_time_to_insight.py               (P6 -- standalone, no baseline)
  lh_cost_by_run    measure_aws_resources.py --by-run        (P1/P2/P4/P7)
  lh_cost_snapshot  measure_aws_resources.py                 (P1-P4 cost)
  wh_size           scripts/measure_warehouse_size.py --json (P3/P4; prints only --
                    aurora_baseline.json stays hand-maintained, see the runbook)
  wh_cost_by_run    scripts/measure_aws_resources.py --by-run
  wh_cost_snapshot  scripts/measure_aws_resources.py
  compare_by_run    compare_environments.py --by-run         (P1-P7 resource/cost stats)
  compare           compare_environments.py                  (P1-P9 scorecard)

Note: scripts/measure_time_to_insight_pg.py (warehouse-side TTI) is intentionally NOT a
step here. P6 (dissertation Ch.1 Table 2) is a standalone threshold test of the
lakehouse's own unified BI layer with no baseline comparison, so no warehouse-side
counterpart is needed. That script still exists in the warehouse repo as a supplementary,
non-P6 tool if you want the context anyway.

Duration note: measure_native_vs_external_join.py (join) and measure_time_to_insight.py
(tti) both default to 200 repetitions -- a confirmatory sample size exceeding the
pre-registered power analysis, not a quick check. tti at 200 repetitions x 19 queries x 2
passes has taken upward of 8 hours in practice; join is much cheaper (minutes) since it
has no per-repetition pipeline cost. Pass --repeats N (a smaller value, e.g. 5-12) to
either step via this driver for a fast exploratory pass instead of a confirmatory one.

Usage:
    python run_measurement_suite.py --dataset fulldataset
    python run_measurement_suite.py --dataset fulldataset --only storage,tti
    python run_measurement_suite.py --dataset fulldataset --stop-on-failure
    python run_measurement_suite.py --dataset fulldataset --force   # skip the running-pipeline check

    # last-5-runs resource/cost comparison only, excluding runs before a fix landed
    # (--lh-since / --wh-since apply before --last-n, so you get the last N runs AFTER
    # the cutoff -- see --lh-since/--wh-since above)
    python run_measurement_suite.py --dataset fulldataset \\
        --only lh_cost_by_run,wh_cost_by_run,compare_by_run --last-n 5 \\
        --lh-since "2026-09-20 02:21:50.915000" --wh-since "2026-09-19 17:41:02.235776"

    # the combined console output is saved automatically to
    # logs/run_measurement_suite_<local-timestamp>.log -- no `| tee` needed
    ./.venv/Scripts/python.exe run_measurement_suite.py --dataset fulldataset --lh-since "2026-09-20 02:21:50.915000" --wh-since "2026-09-19 17:41:02.235776"
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import boto3

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
from mimic_lakehouse import config as _cfg  # noqa: E402

_RUNNING_STATES = ("RUNNING", "STARTING", "WAITING")


def _make_console_utf8_safe() -> None:
    enc = (sys.stdout.encoding or "").lower()
    if enc and enc != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class _Tee:
    """Write-through copy of sys.stdout into the suite's own combined log file."""

    def __init__(self, stream, log_file):
        self._stream, self._log = stream, log_file

    def write(self, text):
        self._stream.write(text)
        self._log.write(text)
        self._log.flush()
        return len(text)

    def flush(self):
        self._stream.flush()
        self._log.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _start_suite_log() -> Path:
    """Tee everything this driver prints (preflight, per-step banners and streamed output,
    final summary) to logs/run_measurement_suite_<local-timestamp>.log, so the combined
    record exists without remembering to pipe through `tee`."""
    logs_dir = REPO / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"run_measurement_suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    sys.stdout = _Tee(sys.stdout, open(path, "w", encoding="utf-8"))
    print(f"suite log: {path}\n$ {' '.join([Path(sys.executable).name, *sys.argv])}")
    return path


@dataclass
class Step:
    key: str
    job_name: str
    repo: Path
    args: list[str]


def _python_for(repo: Path) -> str:
    venv_py = repo / ".venv" / "Scripts" / "python.exe"
    return str(venv_py) if venv_py.exists() else sys.executable


def run_step(step: Step) -> bool:
    logs_dir = step.repo / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{step.job_name}_{ts}.log"
    cmd = [_python_for(step.repo), *step.args]
    print(f"\n{'=' * 100}\n$ {' '.join(cmd)}   (cwd={step.repo})\nlog: {log_path}\n{'=' * 100}")

    t0 = time.time()
    # Force UTF-8 on the child regardless of whether it reconfigures its own stdout --
    # belt-and-suspenders against the console-encoding crash documented above.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            cmd, cwd=str(step.repo), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        for line in proc.stdout:
            sys.stdout.write(line)
            logf.write(line)
        proc.wait()
    dt = time.time() - t0
    ok = proc.returncode == 0
    print(f"-- {step.job_name}: {'OK' if ok else f'FAILED (exit {proc.returncode})'} in {dt:.0f}s --")
    return ok


def _jobs_in_state(glue, names: list[str]) -> list[str]:
    problems = []
    for name in names:
        try:
            runs = glue.get_job_runs(JobName=name, MaxResults=1).get("JobRuns", [])
        except Exception as exc:  # noqa: BLE001
            print(f"[preflight] could not read job runs for '{name}': {exc}")
            continue
        if runs and runs[0]["JobRunState"] in _RUNNING_STATES:
            problems.append(f"'{name}' is {runs[0]['JobRunState']}")
    return problems


def check_no_pipeline_running(region: str, mode: str, force: bool) -> None:
    if force:
        return
    glue = boto3.client("glue", region_name=region)
    all_jobs = [j["Name"] for j in glue.get_jobs(MaxResults=1000)["Jobs"]]

    lh_jobs = [n for n in all_jobs if n.endswith(f"-{mode}")]
    problems = [f"lakehouse job {p}" for p in _jobs_in_state(glue, lh_jobs)]

    # mirrors mimic_datawarehouse.config.DatasetProfile.glue_job_name_prefix
    # ("mimic4-dw-etl-<mode>") -- not imported directly to avoid needing the
    # warehouse repo's own venv/dependencies (e.g. python-dotenv) inside this process.
    wh_prefix = f"mimic4-dw-etl-{mode}"
    wh_jobs = [n for n in all_jobs if n.startswith(wh_prefix)]
    problems += [f"warehouse job {p}" for p in _jobs_in_state(glue, wh_jobs)]

    if problems:
        print("\nRefusing to start -- a pipeline run looks IN PROGRESS for this dataset:")
        for p in problems:
            print(f"  - {p}")
        print(
            "\nMeasuring now would capture a half-loaded environment (see the 2026-09-20 "
            "incident notes in docs/measurement_readme.md). Wait for it to finish, or pass "
            "--force to measure anyway."
        )
        raise SystemExit(1)
    print(f"[preflight] no {mode}-dataset Glue job is currently running on either side -- proceeding.")


def build_steps(dataset: str, last_n: int, repeats: int | None, wh_repo: Path,
                lh_since: str | None = None, wh_since: str | None = None) -> list[Step]:
    ds = ["--dataset", dataset]
    lh_by_run = ["--by-run", "--last-n", str(last_n)] + (["--since", lh_since] if lh_since else [])
    wh_by_run = ["--by-run", "--last-n", str(last_n)] + (["--since", wh_since] if wh_since else [])
    rep = ["--repeats", str(repeats)] if repeats else []
    return [
        Step("storage", "measure_storage_footprint", REPO,
             ["measure_storage_footprint.py", *ds]),
        Step("fmt_measure", "measure_parquet_comparison", REPO,
             ["measure_parquet_comparison.py", *ds]),
        Step("fmt_compare", "compare_parquet_iceberg", REPO,
             ["compare_parquet_iceberg.py", *ds]),
        Step("raw_compare", "compare_iceberg_raw_csv", REPO,
             ["compare_iceberg_raw_csv.py", *ds]),
        Step("join", "measure_native_vs_external_join", REPO,
             ["measure_native_vs_external_join.py", *ds, *rep]),
        Step("tti", "measure_time_to_insight", REPO,
             ["measure_time_to_insight.py", *ds, *rep]),
        Step("lh_cost_by_run", "measure_aws_resources_by_run", REPO,
             ["measure_aws_resources.py", *ds, *lh_by_run]),
        Step("lh_cost_snapshot", "measure_aws_resources_snapshot", REPO,
             ["measure_aws_resources.py", *ds]),
        Step("wh_size", "measure_warehouse_size", wh_repo,
             ["scripts/measure_warehouse_size.py", *ds, "--json"]),
        Step("wh_cost_by_run", "measure_aws_resources_by_run", wh_repo,
             ["scripts/measure_aws_resources.py", *ds, *wh_by_run]),
        Step("wh_cost_snapshot", "measure_aws_resources_snapshot", wh_repo,
             ["scripts/measure_aws_resources.py", *ds]),
        Step("compare_by_run", "compare_environments_by_run", REPO,
             ["compare_environments.py", *ds, "--by-run", "--last-n", str(last_n)]),
        Step("compare", "compare_environments", REPO,
             ["compare_environments.py", *ds]),
    ]


def main() -> int:
    _make_console_utf8_safe()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _cfg.add_dataset_arg(ap)
    ap.add_argument("--warehouse-repo", default=str(REPO.parent / "mimic_datawarehouse_repo"))
    ap.add_argument("--region", default=_cfg.get("AWS_REGION", "us-east-2"))
    ap.add_argument("--last-n", type=int, default=None,
                    help="passed to every --by-run step (default: 5, or unlimited -- every eligible "
                         "run -- if --lh-since/--wh-since is given without an explicit --last-n).")
    ap.add_argument("--repeats", type=int, default=None,
                    help="override --repeats for the tti/join scripts (default: each script's own default)")
    ap.add_argument("--lh-since", default=None,
                    help="lh_cost_by_run: exclude lakehouse full_run_ids started before this timestamp "
                         "('YYYY-MM-DD HH:MM:SS[.ffffff]' or ISO 8601, UTC) -- e.g. to exclude runs "
                         "affected by a bug that has since been fixed. Applied before --last-n.")
    ap.add_argument("--wh-since", default=None,
                    help="wh_cost_by_run: same as --lh-since, for the warehouse side's full_run_ids.")
    ap.add_argument("--force", action="store_true",
                    help="skip the pre-flight check for a currently-running pipeline")
    ap.add_argument("--stop-on-failure", action="store_true",
                    help="abort on the first failed step (default: run every step and report a summary)")
    ap.add_argument("--only", default=None,
                    help="comma-separated step keys to run (default: all -- see the module docstring)")
    args = ap.parse_args()
    suite_log = _start_suite_log()

    profile = _cfg.dataset_profile(args.dataset)
    wh_repo = Path(args.warehouse_repo).resolve()

    check_no_pipeline_running(args.region, profile.mode, args.force)

    last_n = args.last_n if args.last_n is not None else (0 if (args.lh_since or args.wh_since) else 5)
    steps = build_steps(args.dataset, last_n, args.repeats, wh_repo,
                        lh_since=args.lh_since, wh_since=args.wh_since)
    if args.only:
        wanted = [k.strip() for k in args.only.split(",")]
        known = {s.key for s in steps}
        unknown = [k for k in wanted if k not in known]
        if unknown:
            ap.error(f"unknown --only key(s): {', '.join(unknown)}. Known: {', '.join(sorted(known))}")
        steps = [s for s in steps if s.key in wanted]

    results: list[tuple[Step, bool]] = []
    for step in steps:
        ok = run_step(step)
        results.append((step, ok))
        if not ok and args.stop_on_failure:
            print(f"\nStopping: {step.job_name} failed and --stop-on-failure was set.")
            break

    print("\n" + "=" * 100)
    print(f"Measurement suite summary -- {args.dataset}")
    print("=" * 100)
    for step, ok in results:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {step.key:18} {step.job_name}")

    failed = [s for s, ok in results if not ok]
    if failed:
        print(f"\n{len(failed)} step(s) failed: {', '.join(s.key for s in failed)}")
    else:
        print("\nAll steps succeeded.")
    print(f"suite log: {suite_log}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
