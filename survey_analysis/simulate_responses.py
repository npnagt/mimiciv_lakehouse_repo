"""Generate SIMULATED questionnaire responses for testing analyze_survey.py.

Writes a CSV laid out like a Google Forms export of the Final Version v2 instrument
(grid questions as "Section title [ID statement]" columns). Every value is synthetic:
the effect sizes below are assumptions chosen to exercise the analysis, not predictions,
and every free-text answer is prefixed "[SIMULATED]".

    python survey_analysis/simulate_responses.py --n 40 --out survey_analysis/output/simulated/simulated_responses.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

FIT_TEXT = {
    1: "adequately supports end-to-end workflows for multimodal data (structured records, free-text notes).",
    2: "It was straightforward to combine different modalities (ICU tables, labs, clinical notes).",
    3: "I do not need to create redundant copies or data/extracts of the same patient data to complete my tasks.",
    4: "Building an end-to-end pipeline required relatively little \"plumbing\" work (ad hoc scripts, manual exports).",
    5: "I could join and process the data where it is stored, without exporting it to a separate tool or system.",
    6: "Query and dashboard results returned quickly enough (within about 10 seconds) that I stayed focused.",
    7: "When new data arrives, it made it easy to adjust and re-run analytics or AI/ML models without significant rework.",
}
TLX_TEXT = {1: "Mental Demand", 2: "Temporal Demand", 3: "Performance", 4: "Effort", 5: "Frustration"}
# Assumed ATLAS-minus-baseline shifts on the 1-7 scale, per proposition (simulation only).
FIT_SHIFT = {1: 1.2, 2: 1.5, 3: 1.0, 4: 1.1, 5: 1.4, 6: 0.5, 7: 0.8}
TLX_OFFSET = {1: 1.0, 2: 0.0, 3: -1.0, 4: 0.75, 5: -0.5}  # on the 0-10 TLX scale
A_OPTIONS = {
    "A1": (["0–1 year", "2–3 years", "4–5 years", "6–9 years", "10+ years"], [0.05, 0.15, 0.25, 0.25, 0.30]),
    "A2": (["None", "Limited", "Moderate", "Extensive"], [0.10, 0.30, 0.40, 0.20]),
    "A3": (["None", "Limited", "Moderate", "Extensive"], [0.10, 0.35, 0.35, 0.20]),
    "A4": (["Data Engineer/Analyst", "Data Architect", "Data Scientist", "AI Researcher", "Manager / Director / VP / Owner"],
           [0.35, 0.20, 0.20, 0.10, 0.15]),
}
C2_OPTIONS = ["Strongly preferred the baseline architecture", "Somewhat preferred the baseline architecture",
              "No preference", "Somewhat preferred the proposed architecture", "Strongly preferred the proposed architecture"]
OPEN_POOL = {
    "BA3.1": ["Exporting note-derived features and re-joining them to admissions in a separate tool.",
              "Finding which store held the NLP output and matching its identifiers.",
              "Waiting for the extract before the dashboard could be refreshed."],
    "BB3.1": ["Learning which of the five fact types held the feature I needed.",
              "Writing the JSON/Variant path expressions for the inference payload.",
              "Nothing major; the joins were ordinary SQL."],
    "D1": ["Everything joined on the same admission key.", "Fewer moving parts.", "The baseline is more familiar to my team."],
    "D2": ["In the baseline I exported notes features to Python; in ATLAS I did not.", "Only in the baseline, which added a manual step."],
    "D3": ["ATLAS queries came back fast enough to keep going.", "One baseline export made me switch tasks while waiting."],
    "D4": ["The inference fact, because model output stays separate from recorded data.", "The unstructured features fact."],
    "D5": ["Label inferred values and show the model version beside recorded measures.", "Separate dashboard tiles for inferred values."],
    "D6": ["Skills with open table formats.", "Governance sign-off for model output.", "Engine support for Iceberg V3."],
    "D7": ["No further comments."],
}


def clip_round(x, lo, hi):
    return int(np.clip(np.rint(x), lo, hi))


def build(n: int, seed: int):
    rng = np.random.default_rng(seed)
    headers = ["Timestamp", "Consent: I agree to participate in this study"]
    headers += [f"A{i}. {t}" for i, t in [(1, "Years of professional experience in data engineering or data analytics:"),
                                          (2, "Experience working with data lakes:"), (3, "Experience working with AI:"),
                                          (4, "What is your current role?")]]
    for arch, title in (("BA", "Baseline Architecture"), ("BB", "Proposed Multimodal Architecture (ATLAS)")):
        headers += [f"{arch}1. {title} — Architectural Fit and Usability [{arch}1.{k}   {FIT_TEXT[k]} [P{k}]]" for k in FIT_TEXT]
        headers += [f"{arch}2.{k} {name}" for k, name in TLX_TEXT.items()]
        headers += [f"{arch}3.1 Describe the most difficult step(s) you encountered."]
    headers += ["C1   Considering the performance gains observed, the benefits outweigh the added complexity.",
                "C2. Overall preference — please select one option:"]
    headers += [f"D{i}. (open-ended)" for i in range(1, 8)]

    rows = []
    n_decline = max(1, n // 20)
    for i in range(n):
        ts = f"2026/11/{1 + i % 28:02d} 10:{i % 60:02d}:00"
        if i < n_decline:
            rows.append([ts, "I do not agree to participate in this study"] + [""] * (len(headers) - 2))
            continue
        row = [ts, "I agree to participate in this study"]
        for a in ("A1", "A2", "A3", "A4"):
            opts, p = A_OPTIONS[a]
            row.append(str(rng.choice(opts, p=p)))
        pro_atlas = rng.normal(0, 0.6)  # respondent-level openness to the new architecture
        answers = {}
        for arch in ("BA", "BB"):
            person = rng.normal(0, 0.7)  # respondent-level rating tendency -> item correlation
            for k in FIT_TEXT:
                mu = 3.7 + person + (FIT_SHIFT[k] + pro_atlas if arch == "BB" else 0)
                answers[f"{arch}1.{k}"] = clip_round(mu + rng.normal(0, 0.8), 1, 7)
            load = rng.normal(5.75, 1.0) - (1.5 + pro_atlas / 2 if arch == "BB" else 0)
            for k in TLX_TEXT:
                answers[f"{arch}2.{k}"] = clip_round(load + TLX_OFFSET[k] + rng.normal(0, 1.0), 0, 10)
            answers[f"{arch}3.1"] = ("[SIMULATED] " + str(rng.choice(OPEN_POOL[f"{arch}3.1"]))) if rng.random() < 0.6 else ""
        for arch in ("BA", "BB"):
            row += [str(answers[f"{arch}1.{k}"]) for k in FIT_TEXT]
            row += [str(answers[f"{arch}2.{k}"]) for k in TLX_TEXT]
            row.append(answers[f"{arch}3.1"])
        advantage = np.mean([answers[f"BB1.{k}"] - answers[f"BA1.{k}"] for k in FIT_TEXT])
        row.append(str(clip_round(4.6 + 0.6 * advantage + rng.normal(0, 0.8), 1, 7)))
        row.append(C2_OPTIONS[clip_round(0.8 * advantage + rng.normal(0, 0.8), -2, 2) + 2])
        row += [("[SIMULATED] " + str(rng.choice(OPEN_POOL[f"D{d}"]))) if rng.random() < 0.55 else "" for d in range(1, 8)]
        rows.append(row)

    # a couple of skipped rating items, as real exports have
    for _ in range(2):
        r = rows[int(rng.integers(n_decline, n))]
        r[int(rng.integers(6, 13))] = ""
    return headers, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=40, help="number of simulated respondents (including a few who decline)")
    ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "output" / "simulated" / "simulated_responses.csv")
    args = ap.parse_args(argv)
    headers, rows = build(args.n, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows([headers] + rows)
    print(f"{len(rows)} simulated responses -> {args.out}")


if __name__ == "__main__":
    main()
