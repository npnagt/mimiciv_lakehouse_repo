"""Build demo_lakehouse.duckdb: a small SYNTHETIC lakehouse with the same table shapes as the book's MIMIC-IV
reference implementation (no real patient data). Tables: obt_admission_features (Computed Structured Fact),
fact_discharge_note (Unstructured Data Fact), fact_discharge_note_nlp (Unstructured Features Fact), and a view
v_admission_outcomes with the 30-day readmission label."""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def build(path=HERE / "demo_lakehouse.duckdb", n_patients=800, seed=7):
    rng = np.random.default_rng(seed)
    rows, notes, nlp = [], [], []
    hadm = 20_000_000
    for pid in range(10_000_001, 10_000_001 + n_patients):
        smoker = rng.choice(["current", "former", "never"], p=[0.2, 0.3, 0.5])
        alcohol = rng.choice(["current", "none"], p=[0.25, 0.75])
        obese = rng.choice(["obese", "not obese"], p=[0.3, 0.7])
        chf = rng.random() < 0.25
        t = pd.Timestamp("2023-01-01") + pd.Timedelta(days=int(rng.integers(0, 300)))
        for _ in range(int(rng.choice([1, 1, 1, 2, 2, 3]))):
            hadm += 1
            atype = rng.choice(["EMERGENCY", "URGENT", "ELECTIVE"], p=[0.6, 0.15, 0.25])
            dx = int(np.clip(rng.poisson(10 + 4 * chf), 1, None))
            los_h = float(np.clip(rng.gamma(2.2, 40 + 20 * chf), 6, None))
            age = int(np.clip(rng.normal(66, 14), 18, 95))
            disch = t + pd.Timedelta(hours=los_h)
            rows.append(dict(hadm_id=hadm, subject_id=pid, admit_time=t, disch_time=disch, admission_type=atype,
                             age_at_admission=age, diagnosis_count=dx, heart_failure=int(chf),
                             abnormal_lab_rate=round(float(np.clip(rng.beta(2, 5) + 0.1 * chf, 0, 1)), 3),
                             hospital_los_hours=round(los_h, 1),
                             discharge_location=rng.choice(["HOME", "HOME HEALTH CARE", "SKILLED NURSING FACILITY"], p=[0.6, 0.25, 0.15])))
            hx = "history of congestive heart failure (CHF), " if chf else ""
            sm = {"current": "Current smoker, 1 ppd.", "former": "Former smoker, quit 5 years ago.", "never": "Denies tobacco use."}[smoker]
            al = "Reports daily alcohol use." if alcohol == "current" else "Denies alcohol use."
            notes.append(dict(hadm_id=hadm, subject_id=pid, last_storetime=disch + pd.Timedelta(hours=float(rng.uniform(1, 30))),
                              text=f"Discharge summary. {age}-year-old patient with {hx}admitted via {atype.lower()}. "
                                   f"{sm} {al} BMI {'34' if obese == 'obese' else '24'}. Discharged to "
                                   f"{rows[-1]['discharge_location'].lower()} with follow-up in 7 days."))
            nlp.append(dict(hadm_id=hadm, subject_id=pid, tobacco_use=smoker, alcohol_use=alcohol, obesity_level=obese))
            gap = rng.exponential(25 if chf else 70)
            t = disch + pd.Timedelta(days=float(gap))
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    for name, data in [("obt_admission_features", rows), ("fact_discharge_note", notes), ("fact_discharge_note_nlp", nlp)]:
        con.register("tmp", pd.DataFrame(data))
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
    con.execute("""CREATE VIEW v_admission_outcomes AS
        SELECT *, CASE WHEN LEAD(admit_time) OVER (PARTITION BY subject_id ORDER BY admit_time)
                       <= disch_time + INTERVAL 30 DAY THEN 1 ELSE 0 END AS readmit_30d
        FROM obt_admission_features""")
    n = con.execute("SELECT COUNT(*), AVG(readmit_30d) FROM v_admission_outcomes").fetchone()
    con.close()
    return n


if __name__ == "__main__":
    print("admissions, 30-day readmission rate:", build())
