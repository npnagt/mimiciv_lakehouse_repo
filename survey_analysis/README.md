# Survey analysis (P1-P9, Cluster 3)

Analyses the participant questionnaire (Google Forms export) for the dissertation
propositions: paired baseline-vs-ATLAS ratings for P1-P7, Raw TLX workload for P8,
adoption intent for P9, plus reliability, sensitivity, open-ended answers for coding,
inter-coder kappa, and a proposition-verdict sheet that sits beside the pipeline evidence.

Setup (separate from the pipeline's `.venv`):

```
python -m venv survey_analysis/.venv
survey_analysis/.venv/Scripts/python.exe -m pip install -r survey_analysis/requirements.txt
```

Dry run on simulated data:

```
survey_analysis/.venv/Scripts/python.exe survey_analysis/simulate_responses.py
survey_analysis/.venv/Scripts/python.exe survey_analysis/analyze_survey.py --input survey_analysis/output/simulated/simulated_responses.csv --out-dir survey_analysis/output/simulated
```

Real data: save the Google Forms CSV export under `survey_analysis/data/` and run

```
survey_analysis/.venv/Scripts/python.exe survey_analysis/analyze_survey.py --input survey_analysis/data/responses.csv --out-dir survey_analysis/output/real
```

Add `--coding double_coded.csv` (columns `respondent_id,item,coder1,coder2`, codes separated
by `;`) once the open-ended answers are double-coded.

**The questions are read from the CSV header row**, so adding, removing or renumbering
questions on the form needs no code change. Each question title must start with its code
(`A1.`, `BA1.1`, `BB2.3`, `C1.`, `D4.` ...) or carry it after `[` in a grid row
(`BA1. ... [BA1.1 ...]`). The code decides how a question is used: `A<n>` profile, `BA1.k`/`BB1.k`
fit pairs (proposition `Pk`, or a `[Pn]` tag in the title), `BA2.k`/`BB2.k` TLX pairs,
`BA3.k`/`BB3.k` and `D<n>` open-ended, `C1` adoption intent, `C2` preference. Columns without a
code are ignored; the consent question is found among them. The workbook's **Instrument**
sheet lists how every column was classified, and a warning flags any baseline/ATLAS pair
whose wording differs beyond the architecture name.

TLX answers are expected on a 0-10 scale and rescaled to 0-100; pass `--tlx-scale 1-20` for
an export from the older 1-20 version.

`survey_analysis/data/` and `survey_analysis/output/` are git-ignored: real responses are
human-subject data and must not be committed.
