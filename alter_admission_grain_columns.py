#!/usr/bin/env python3
"""One-off schema-evolution backfill: ADD COLUMNS (admit_provider_id, admit_date_key) to the
five Athena-visible Gold tables that were created (or last --fresh-reload'd) from a version
of ddl/gold/mimic_iv_ddl_gold_combined_v4.sql that predates those grain-consistency columns.

Iceberg's ALTER TABLE ... ADD COLUMNS is additive and metadata-only (no data rewrite):
existing rows read back NULL for the new columns until the next write of that table
repopulates them. This script ALSO deletes obt_admission_features' etl_control watermark
row: that job refreshes incrementally off etl_control (only admissions whose source rows
changed since the watermark), and the watermark was just advanced by the pipeline run that
created this table with the OLD schema -- a plain re-run right after this ALTER would see
"nothing changed" and touch zero rows, leaving admit_provider_id NULL for the entire table
forever. Deleting the watermark row makes the next run treat it as a first run (full
backfill of every admission). fact_discharge_note / fact_radiology_note need no such reset
-- fact_note_concat.py is a plain full-reload write, not watermarked. medspacy_nlp.py /
radiology_nlp.py need `--refresh-mode full` on their NEXT run instead (not an etl_control
reset -- see run_lakehouse_pipeline.py's follow-up command list): their capped
--nlp-row-limit run never advanced their own watermark, but resume-skip would otherwise
skip the admissions the in-flight run already wrote (with the old, column-less schema)
rather than repopulating them.

fact_radiology_note_nlp_v (Iceberg format-version 3) is NOT included here -- Athena engine
v3 cannot ALTER a format-v3 table at all. radiology_nlp_variant.py now does its own
self-healing ADD COLUMNS via Spark the next time that job runs (see its module code).

Safe to re-run: an "already exists" error from Athena for a column that was already added
is caught and reported, not treated as a fatal failure.

Usage:
    python alter_admission_grain_columns.py --dataset fulldataset
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))
from mimic_lakehouse import config as _cfg  # noqa: E402
from mimic_lakehouse.aws_workflow import run_athena_statement  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _cfg.add_dataset_arg(ap)
    ap.add_argument("--region", default=_cfg.get("AWS_REGION", "us-east-2"))
    ap.add_argument("--athena-workgroup", default=_cfg.get("ATHENA_WORKGROUP", "primary"))
    ap.add_argument("--athena-poll-interval", type=int, default=2)
    args = ap.parse_args()

    profile = _cfg.dataset_profile(args.dataset)
    gold_db = profile.gold_database
    output_location = f"s3://{profile.gold_bucket}/athena-results/"
    athena = boto3.client("athena", region_name=args.region) if args.region else boto3.client("athena")

    statements = [
        f"ALTER TABLE {gold_db}.obt_admission_features ADD COLUMNS (admit_provider_id string)",
        f"ALTER TABLE {gold_db}.fact_discharge_note ADD COLUMNS (admit_provider_id string, admit_date_key int)",
        f"ALTER TABLE {gold_db}.fact_radiology_note ADD COLUMNS (admit_provider_id string, admit_date_key int)",
        f"ALTER TABLE {gold_db}.fact_discharge_note_nlp ADD COLUMNS (admit_provider_id string, admit_date_key int)",
        f"ALTER TABLE {gold_db}.fact_radiology_note_nlp ADD COLUMNS (admit_provider_id string, admit_date_key int)",
        # Force obt_admission_features' next run to see every admission as "touched" --
        # see the module docstring for why a plain re-run would otherwise leave the new
        # column NULL for the whole table.
        f"DELETE FROM {gold_db}.etl_control WHERE aggregate_table = 'obt_admission_features'",
    ]

    print(f"Gold database: {gold_db}")
    ok, failed = 0, 0
    for i, sql in enumerate(statements, 1):
        print(f"[{i}/{len(statements)}] {sql}")
        try:
            run_athena_statement(athena, sql, output_location, args.athena_workgroup, args.athena_poll_interval)
            print("      OK")
            ok += 1
        except SystemExit:
            print("      FAILED or columns already present -- see the ERROR line above.")
            failed += 1

    print(f"\n{ok}/{len(statements)} succeeded, {failed} failed/already-applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
