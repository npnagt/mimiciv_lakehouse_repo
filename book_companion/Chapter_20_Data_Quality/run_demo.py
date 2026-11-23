"""Chapter 20 demo: build the synthetic lakehouse, then try to publish a clean batch and a defective batch.
Writes scorecard_clean.csv and scorecard_defective.csv."""
import shutil
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
for p in ("agent_demo", "Chapter_17_Lakehouse_Agent"):   # make_demo_lakehouse.py lives with Chapter 17
    sys.path.insert(0, str(HERE.parent / p))
import make_demo_lakehouse  # noqa: E402

from quality_checks import RULES, write_audit_publish  # noqa: E402

DB = str(HERE / "dq_lakehouse.duckdb")


def new_batch(defects: bool, seed=3):
    """Next month's admissions: real-looking rows copied forward, optionally with injected defects."""
    con = duckdb.connect(DB, read_only=True)
    obt = con.execute("SELECT * FROM obt_admission_features USING SAMPLE 200 ROWS (reservoir, 7)").fetchdf()
    ids = tuple(obt["hadm_id"])
    note = con.execute(f"SELECT * FROM fact_discharge_note WHERE hadm_id IN {ids}").fetchdf()
    nlp = con.execute(f"SELECT * FROM fact_discharge_note_nlp WHERE hadm_id IN {ids}").fetchdf()
    con.close()
    for df in (obt, note, nlp):
        df["hadm_id"] += 1_000_000
    shift = pd.Timedelta(days=400)
    obt["admit_time"] += shift; obt["disch_time"] += shift; note["last_storetime"] += shift
    if defects:
        rng = np.random.default_rng(seed)
        obt.loc[rng.choice(200, 6, replace=False), "age_at_admission"] = np.nan        # missing ages
        obt.loc[[10, 11, 12], "age_at_admission"] = 150                                # impossible ages
        obt = pd.concat([obt, obt.iloc[:4]], ignore_index=True)                        # duplicate admissions
        obt.loc[[20, 21], "disch_time"] = obt.loc[[20, 21], "admit_time"] - pd.Timedelta(hours=5)
        orphan = note.iloc[:5].copy(); orphan["hadm_id"] += 5_000_000                  # notes with no admission
        note = pd.concat([note, orphan], ignore_index=True)
        note.loc[[30, 31, 32], "text"] = ""                                            # empty notes
        nlp.loc[[40, 41, 42, 43], "tobacco_use"] = "smoker"                            # invalid category
    return {"obt_admission_features": obt, "fact_discharge_note": note, "fact_discharge_note_nlp": nlp}


if __name__ == "__main__":
    make_demo_lakehouse.build(Path(DB))
    for label, defects in [("defective", True), ("clean", False)]:
        card, published = write_audit_publish(DB, new_batch(defects))
        card.to_csv(HERE / f"scorecard_{label}.csv", index=False)
        print(f"\n=== {label} batch: {'PUBLISHED' if published else 'BLOCKED, main tables unchanged'} ===")
        print(card[["rule", "dimension", "failed", "total", "pass_rate", "threshold", "status"]].to_string(index=False))
    con = duckdb.connect(DB, read_only=True)
    print("\nadmissions in main after both runs:", con.execute("SELECT COUNT(*) FROM obt_admission_features").fetchone()[0])
    print("rules:", len(RULES))
