"""Analyse the ATLAS participant questionnaire for propositions P1-P9.

Reads a Google Forms CSV export and writes an Excel workbook plus a Markdown summary.
The instrument is read from the CSV header row, not hard-coded: every column whose
question title starts with a question code (A1., BA1.1, BB2.3, C2., D4. ...) is picked
up, together with its question text and an optional "[Pn]" proposition tag. Adding,
removing or renumbering questions on the form therefore needs no change here.

How codes are interpreted:

  A<n>          respondent profile (Section A); ordinal when every answer starts with a
                number ("6-9 years") or None/Limited/Moderate/Extensive, else nominal
  BA1.k / BB1.k architectural fit, baseline vs ATLAS, 1-7 agreement; pair k is
                proposition [Pn] from the title if tagged, else Pk
  BA2.k / BB2.k NASA-TLX subscale, baseline vs ATLAS, on --tlx-scale (default 0-10),
                rescaled to 0-100; the subscale name is the title text before " - "
  BA3.k / BB3.k open-ended, per architecture
  C1            adoption intent, 1-7 agreement
  C2            overall preference (strongly/somewhat preferred baseline/proposed, none)
  D<n>          open-ended reflections

Columns without a code (Timestamp, the consent question, blank trailing columns) are
listed as ignored; the consent column is found among them.

Outputs:
  * instrument as parsed, including a wording check of every baseline/ATLAS pair
  * sample profile and consent / completeness counts
  * reliability -- Cronbach's alpha for the fit scales and the TLX subscales
  * per fit pair: Wilcoxon signed-rank (r = Z / sqrt(n pairs)), Holm-corrected across
    pairs, plus paired mean difference, 95% CI and Cohen's d_z (manuscript bar d >= 0.50)
  * fit composite -- paired t-test and Wilcoxon
  * P8: Raw TLX (unweighted mean of the subscales), composite and per subscale
  * P9: C1 one-sample Wilcoxon vs the neutral midpoint 4; C2 distribution and sign test
  * exploratory Spearman correlations of ordinal profile items with the ATLAS advantage
  * sensitivity: smallest d_z detectable at 80% power with the achieved n
  * open-ended answers in long format, ready for coding; optional Cohen's kappa
  * proposition verdicts beside the pipeline evidence (joint-display scaffold)

    python survey_analysis/analyze_survey.py --input survey_analysis/data/responses.csv --out-dir survey_analysis/output/real
    python survey_analysis/analyze_survey.py --input responses.csv --tlx-scale 1-20 --coding double_coded.csv

Real responses are human-subject data: keep them under survey_analysis/data/ or
survey_analysis/output/, both git-ignored.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from scipy import stats

ALPHA = 0.05
D_MIN = 0.50  # manuscript acceptance clause: p < .05 with Cohen's d >= 0.50
POWER = 0.80
LIKERT = (1, 7)
NEUTRAL = 4  # midpoint of the 1-7 agreement scale
TLX_SCALES = {"0-10": (0, 10), "1-20": (1, 20)}

# Where an open-ended item's answers feed in, when its title carries no "[Pn]" tag.
OPEN_DEFAULT_MAPS = {
    "D1": "P9", "D2": "P5", "D3": "P6", "D4": "Fact taxonomy",
    "D5": "Recorded vs inferred", "D6": "P9", "D7": "General",
}
ORDINAL_WORDS = ["none", "limited", "moderate", "extensive"]
# Headline pipeline (system-measurement) evidence per proposition, as last recorded.
# Refresh these from the measurement scripts' latest output before reporting.
PIPELINE_EVIDENCE = {
    "P1": "30-workflow catalogue (validate_rq2_queries.py): 100% vs 86.67% coverage",
    "P2": "Not yet measured -- count systems/hops per catalogue workflow",
    "P3": "measure_storage_footprint.py: redundancy ratio",
    "P4": "P4 ad-hoc catalogue: 97.8% vs 7.8% query coverage",
    "P5": "measure_native_vs_external_join.py: native join 2.49x/2.55x faster",
    "P6": "measure_time_to_insight.py: pass/fail, every query <= 10 s (no baseline)",
    "P7": "etl_process_log: incremental re-runs 2-16x faster than backfill",
    "P8": "No system measure (survey only)",
    "P9": "No system measure (survey only)",
}

CODE_RE = re.compile(r"(?:^|\[)\s*([A-Z]{1,2}\d+(?:\.\d+)?)(?=[\s.:)\]-]|$)")
PROP_TAG_RE = re.compile(r"\[(P\d+(?:\.\d+)?)\]")
ARCH_RE = re.compile(r"\b(?:the\s+)?(?:baseline|proposed(?:\s+multimodal)?)\s+architecture\b", re.I)
DASHES = str.maketrans({"–": "-", "—": "-", "−": "-"})


# ---------------------------------------------------------------- instrument (from the header)

def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        sys.exit(f"{path}: empty file")
    return rows[0], rows[1:]


def extract_code(header: str) -> str | None:
    """Question code at the start of the title, or after '[' in a Google Forms grid row."""
    codes = [c for c in CODE_RE.findall(header.strip()) if not re.fullmatch(r"P\d+(?:\.\d+)?", c)]
    return codes[-1] if codes else None  # a grid row's "[CODE ...]" wins over its section prefix


def question_text(header: str, code: str) -> str:
    h = header.strip()
    i = h.rfind(code)
    text = h[i + len(code):] if i >= 0 else h
    text = PROP_TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" .:-]")


def short(text: str, n: int = 70) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def code_key(code: str):
    return [int(x) if x.isdigit() else x for x in re.findall(r"[A-Z]+|\d+", code)]


@dataclass
class Item:
    code: str
    col: int
    text: str
    tag: str | None  # "[Pn]" proposition tag from the title, if any


class Instrument:
    """Questions discovered from the CSV header row."""

    def __init__(self, headers: list[str]):
        self.items: dict[str, Item] = {}
        self.ignored: list[tuple[int, str]] = []
        self.notes: list[str] = []
        for idx, header in enumerate(headers):
            code = extract_code(header)
            if code is None:
                self.ignored.append((idx, header))
                continue
            if code in self.items:
                sys.exit(f"question code {code} appears in two columns: "
                         f"{headers[self.items[code].col]!r} and {header!r}")
            tag = PROP_TAG_RE.search(header)
            self.items[code] = Item(code, idx, question_text(header, code), tag.group(1) if tag else None)

        codes = sorted(self.items, key=code_key)
        self.profile = [c for c in codes if re.fullmatch(r"A\d+", c)]
        self.fit = self._pairs(1)
        self.tlx = self._pairs(2)
        self.open = ([c for c in codes if re.fullmatch(r"B[AB]3\.\d+", c)]
                     + [c for c in codes if re.fullmatch(r"D\d+", c)])
        self.c1 = "C1" if "C1" in self.items else None
        self.c2 = "C2" if "C2" in self.items else None
        known = set(self.profile) | set(self.open) | {self.c1, self.c2}
        known |= {c for k in self.fit + self.tlx for c in (k["ba"], k["bb"])}
        self.unclassified = [c for c in codes if c not in known]
        if self.unclassified:
            self.notes.append("Codes not used by any analysis: " + ", ".join(self.unclassified))

        missing = [name for name, ok in (("fit pairs BA1.k/BB1.k", self.fit), ("TLX pairs BA2.k/BB2.k", self.tlx),
                                         ("C1", self.c1), ("C2", self.c2)) if not ok]
        if missing:
            sys.exit("the CSV header has no " + "; no ".join(missing) + ".\nCodes found: "
                     + (", ".join(codes) or "none") + "\nEach question title must start with its code (e.g. 'BA1.1 ...').")

        for kind, pairs in (("fit", self.fit), ("TLX", self.tlx)):
            for p in pairs:
                a, b = self.items[p["ba"]].text, self.items[p["bb"]].text
                if norm_wording(a) != norm_wording(b):
                    p["wording_differs"] = True
                    self.notes.append(f"{p['ba']} / {p['bb']} ({kind}) are not worded the same apart from the "
                                      f"architecture name -- check the form")

    def _pairs(self, section: int) -> list[dict]:
        def ks(arch):
            return {int(m.group(1)): m.group(0) for c in self.items
                    if (m := re.fullmatch(rf"B{arch}{section}\.(\d+)", c))}
        ba, bb = ks("A"), ks("B")
        for k in sorted(set(ba) ^ set(bb)):
            self.notes.append(f"{(ba | bb)[k]} has no {'ATLAS' if k in ba else 'baseline'} counterpart -- left out")
        pairs = []
        for k in sorted(set(ba) & set(bb)):
            item_a, item_b = self.items[ba[k]], self.items[bb[k]]
            pairs.append({"k": k, "ba": ba[k], "bb": bb[k], "tag": item_a.tag or item_b.tag,
                          "text": item_a.text, "wording_differs": False})
        return pairs

    def prop(self, pair: dict) -> str:
        return pair["tag"] or f"P{pair['k']}"

    def open_maps(self, code: str) -> str:
        item = self.items[code]
        if item.tag:
            return item.tag
        if re.fullmatch(r"B[AB]3\.\d+", code):
            return "P8 (workload context)"
        return OPEN_DEFAULT_MAPS.get(code, "General")

    def rows(self) -> list[tuple]:
        """One row per CSV column: how it was classified."""
        role = {}
        for c in self.profile:
            role[c] = ("Profile", "")
        for p in self.fit:
            role[p["ba"]] = ("Fit (baseline)", self.prop(p))
            role[p["bb"]] = ("Fit (ATLAS)", self.prop(p))
        for p in self.tlx:
            role[p["ba"]] = ("TLX (baseline)", "P8")
            role[p["bb"]] = ("TLX (ATLAS)", "P8")
        for c in self.open:
            role[c] = ("Open-ended", self.open_maps(c))
        if self.c1:
            role[self.c1] = ("Adoption intent (1-7)", "P9")
        if self.c2:
            role[self.c2] = ("Overall preference", "P9")
        out = [(it.col + 1, it.code, *role.get(it.code, ("Not used", "")), it.text) for it in self.items.values()]
        out += [(i + 1, "", "Ignored (no code)", "", h) for i, h in self.ignored]
        return sorted(out, key=lambda r: r[0])


def norm_wording(text: str) -> str:
    t = ARCH_RE.sub("<arch>", text)
    return re.sub(r"\s+", " ", t).strip(" .?").lower()


def tlx_name(text: str) -> str:
    return text.split(" - ")[0].strip() if " - " in text else short(text, 30)


# ---------------------------------------------------------------- responses

def find_consent_column(inst: Instrument, rows: list[list[str]]) -> int | None:
    for idx, header in inst.ignored:
        if re.search(r"consent|agree", header, re.I):
            return idx
    for idx, _ in inst.ignored:
        if any("agree to participate" in r[idx].lower() for r in rows if idx < len(r)):
            return idx
    return None


def consented(value: str) -> bool:
    v = value.strip().lower()
    if not v or v in ("no", "n", "false") or re.search(r"\b(not|disagree|decline)\b|do not|don't", v):
        return False
    return v in ("yes", "y", "true", "checked", "1") or "agree" in v or v.startswith("yes")


def ordinal_rank(value: str) -> float:
    v = value.lower().translate(DASHES).strip()
    m = re.match(r"(\d+(?:\.\d+)?)", v)
    if m:
        return float(m.group(1))
    for rank, word in enumerate(ORDINAL_WORDS):
        if v.startswith(word):
            return float(rank)
    return math.nan


def c2_score(value: str) -> float:
    v = value.lower()
    if "no preference" in v:
        return 0.0
    side = 1 if "proposed" in v or "atlas" in v else -1 if "baseline" in v else 0
    strength = 2 if "strong" in v else 1 if "somewhat" in v or "slight" in v else 0
    return float(side * strength) if side and strength else math.nan


class Responses:
    """Answers for the consented respondents, arranged by the parsed instrument."""

    def __init__(self, inst: Instrument, rows: list[list[str]], *, consent_filter=True,
                 tlx_scale="0-10", performance_high_is_good=False):
        self.inst = inst
        self.warnings: list[str] = list(inst.notes)
        self.n_rows = len(rows)
        consent_idx = find_consent_column(inst, rows) if consent_filter else None
        if consent_filter and consent_idx is None:
            self.warnings.append("No consent column found; all rows treated as consented.")
        self.consent_column = inst.ignored[[i for i, _ in inst.ignored].index(consent_idx)][1] if consent_idx is not None else None
        kept = [r for r in rows if consent_idx is None or (consent_idx < len(r) and consented(r[consent_idx]))]
        self.n_declined = len(rows) - len(kept)
        self.ids = [f"R{i + 1:03d}" for i in range(len(kept))]
        self.n = len(kept)
        self.tlx_scale = tlx_scale

        def col(code):
            i = inst.items[code].col
            return [r[i].strip() if i < len(r) else "" for r in kept]

        def numeric(code, lo, hi):
            return np.array([self._num(v, lo, hi, code, rid) for v, rid in zip(col(code), self.ids)])

        self.fit_ba = self._matrix([numeric(p["ba"], *LIKERT) for p in inst.fit])
        self.fit_bb = self._matrix([numeric(p["bb"], *LIKERT) for p in inst.fit])
        lo, hi = TLX_SCALES[tlx_scale]

        def tlx(code, name):
            x = (numeric(code, lo, hi) - lo) / (hi - lo) * 100  # rescale to the standard 0-100 metric
            return 100 - x if performance_high_is_good and "performance" in name.lower() else x

        self.tlx_names = [tlx_name(p["text"]) for p in inst.tlx]
        self.tlx_ba = self._matrix([tlx(p["ba"], nm) for p, nm in zip(inst.tlx, self.tlx_names)])
        self.tlx_bb = self._matrix([tlx(p["bb"], nm) for p, nm in zip(inst.tlx, self.tlx_names)])
        self.c1 = numeric(inst.c1, *LIKERT)
        self.c2 = np.array([self._c2(v, rid) for v, rid in zip(col(inst.c2), self.ids)])
        self.cat = {c: col(c) for c in inst.profile}
        self.ord = {}
        for c, values in self.cat.items():
            ranks = np.array([ordinal_rank(v) if v else math.nan for v in values])
            answered = [v for v in values if v]
            if answered and not np.isnan(ranks[[bool(v) for v in values]]).any():
                self.ord[c] = ranks
        self.text = {c: col(c) for c in inst.open}

    def _matrix(self, columns):
        return np.column_stack(columns) if columns else np.empty((self.n, 0))

    def _num(self, value, lo, hi, code, rid):
        if not value:
            return np.nan
        m = re.search(r"-?\d+", value)
        if not m or not lo <= int(m.group()) <= hi:
            self.warnings.append(f"{rid} {code}: unreadable value {value!r} (expected {lo}-{hi}); treated as missing")
            return np.nan
        return float(m.group())

    def _c2(self, value, rid):
        if not value:
            return np.nan
        score = c2_score(value)
        if math.isnan(score):
            self.warnings.append(f"{rid} C2: unrecognised option {value!r}; treated as missing")
        return score


# ---------------------------------------------------------------- statistics

def paired(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ok = ~np.isnan(a) & ~np.isnan(b)
    return a[ok], b[ok]


def wilcoxon_z(diffs: np.ndarray) -> float:
    """Normal-approximation Z of the signed-rank statistic (zeros dropped, tie-corrected)."""
    nz = diffs[diffs != 0]
    n = len(nz)
    if n == 0:
        return 0.0
    ranks = stats.rankdata(np.abs(nz))
    t_plus = ranks[nz > 0].sum()
    _, counts = np.unique(np.abs(nz), return_counts=True)
    var = n * (n + 1) * (2 * n + 1) / 24 - (counts ** 3 - counts).sum() / 48
    return float((t_plus - n * (n + 1) / 4) / math.sqrt(var)) if var > 0 else 0.0


def paired_test(baseline: np.ndarray, atlas: np.ndarray) -> dict:
    """ATLAS minus baseline: Wilcoxon (p, Z, r) and paired t (mean diff, 95% CI, d_z)."""
    a, b = paired(baseline, atlas)
    n = len(a)
    out = {"n": n, "median_baseline": np.nan, "median_atlas": np.nan, "mean_baseline": np.nan,
           "mean_atlas": np.nan, "mean_diff": np.nan, "ci_low": np.nan, "ci_high": np.nan,
           "d_z": np.nan, "t": np.nan, "p_t": np.nan, "wilcoxon_W": np.nan, "z": np.nan,
           "r": np.nan, "p_wilcoxon": np.nan}
    if n < 3:
        return out
    d = b - a
    out.update(median_baseline=float(np.median(a)), median_atlas=float(np.median(b)),
               mean_baseline=float(a.mean()), mean_atlas=float(b.mean()), mean_diff=float(d.mean()))
    sd = d.std(ddof=1)
    if sd > 0:
        half = stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n)
        t_res = stats.ttest_rel(b, a)
        out.update(ci_low=out["mean_diff"] - half, ci_high=out["mean_diff"] + half,
                   d_z=out["mean_diff"] / sd, t=float(t_res.statistic), p_t=float(t_res.pvalue))
    if np.any(d != 0):
        w = stats.wilcoxon(b, a, zero_method="wilcox")
        z = wilcoxon_z(d)
        out.update(wilcoxon_W=float(w.statistic), z=z, r=z / math.sqrt(n), p_wilcoxon=float(w.pvalue))
    else:
        out.update(z=0.0, r=0.0, p_wilcoxon=1.0)
    return out


def holm(pvalues: list[float]) -> list[float]:
    idx = [i for i, p in enumerate(pvalues) if not math.isnan(p)]
    order = sorted(idx, key=lambda i: pvalues[i])
    adjusted = [math.nan] * len(pvalues)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(order) - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def cronbach_alpha(matrix: np.ndarray) -> tuple[float, int]:
    complete = matrix[~np.isnan(matrix).any(axis=1)]
    n, k = complete.shape
    if n < 3 or k < 2:
        return math.nan, n
    total_var = complete.sum(axis=1).var(ddof=1)
    if total_var == 0:
        return math.nan, n
    return float(k / (k - 1) * (1 - complete.var(axis=0, ddof=1).sum() / total_var)), n


def paired_power(dz: float, n: int) -> float:
    df = n - 1
    tcrit = stats.t.ppf(1 - ALPHA / 2, df)
    nc = dz * math.sqrt(n)
    return float(1 - stats.nct.cdf(tcrit, df, nc) + stats.nct.cdf(-tcrit, df, nc))


def min_detectable_dz(n: int) -> float:
    if n < 3:
        return math.nan
    lo, hi = 0.01, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if paired_power(mid, n) < POWER else (lo, mid)
    return hi


def required_n(dz: float) -> int:
    n = 3
    while paired_power(dz, n) < POWER:
        n += 1
    return n


def cohen_kappa(x: list[int], y: list[int]) -> float:
    n = len(x)
    if n == 0:
        return math.nan
    po = sum(a == b for a, b in zip(x, y)) / n
    labels = set(x) | set(y)
    pe = sum((x.count(l) / n) * (y.count(l) / n) for l in labels)
    return math.nan if pe == 1 else (po - pe) / (1 - pe)


def verdict(diff_favours_atlas: bool, p_adj: float, dz: float) -> str:
    if math.isnan(p_adj) or math.isnan(dz):
        return "Insufficient data"
    if p_adj < ALPHA and not diff_favours_atlas:
        return "Contrary (favours baseline)"
    if p_adj < ALPHA and abs(dz) >= D_MIN:
        return "Supported"
    if p_adj < ALPHA:
        return f"Partially supported (significant, |d_z| < {D_MIN})"
    return "Not supported (not significant)"


# ---------------------------------------------------------------- analysis

def complete_rows(*matrices: np.ndarray) -> np.ndarray:
    ok = np.ones(matrices[0].shape[0], dtype=bool)
    for m in matrices:
        ok &= ~np.isnan(m).any(axis=1)
    return ok


def analyse(resp: Responses, coding: Path | None) -> dict:
    inst = resp.inst
    res: dict = {"warnings": resp.warnings, "instrument": inst.rows()}
    fit_ba, fit_bb, tlx_ba, tlx_bb = resp.fit_ba, resp.fit_bb, resp.tlx_ba, resp.tlx_bb
    fit_range = f"{inst.fit[0]['ba']}-{inst.fit[-1]['ba']}"
    tlx_range = f"{inst.tlx[0]['ba']}-{inst.tlx[-1]['ba']}"
    res["fit_range"], res["n_fit"], res["n_tlx"] = fit_range, len(inst.fit), len(inst.tlx)
    res["tlx_scale"] = resp.tlx_scale

    complete = complete_rows(fit_ba, fit_bb, tlx_ba, tlx_bb)
    res["sample"] = [
        ("Rows in export", resp.n_rows),
        ("Declined consent (excluded)", resp.n_declined),
        ("Consented respondents analysed", resp.n),
        ("Complete on all fit + TLX items (both architectures)", int(complete.sum())),
        ("Questions parsed from the header", len(inst.items)),
        ("Consent column", short(resp.consent_column or "(none)", 60)),
    ]
    profile = []
    for c in inst.profile:
        values = [v for v in resp.cat[c] if v]
        is_ord = c in resp.ord
        levels = sorted(set(values), key=lambda v: (ordinal_rank(v) if is_ord else 0, v))
        label = short(inst.items[c].text, 60)
        for level in levels:
            profile.append((c, label, level, values.count(level), values.count(level) / len(values)))
        if len(values) < resp.n:
            profile.append((c, label, "(no answer)", resp.n - len(values), math.nan))
    res["profile"] = profile

    res["reliability"] = []
    for label, m in ((f"Fit scale -- baseline ({fit_range})", fit_ba),
                     (f"Fit scale -- ATLAS ({fit_range.replace('BA', 'BB')})", fit_bb),
                     (f"Raw TLX -- baseline ({tlx_range})", tlx_ba),
                     (f"Raw TLX -- ATLAS ({tlx_range.replace('BA', 'BB')})", tlx_bb)):
        alpha, n = cronbach_alpha(m)
        res["reliability"].append((label, m.shape[1], n, alpha,
                                   "acceptable (>= .70)" if alpha >= 0.70 else
                                   "below .70 -- report items separately" if not math.isnan(alpha) else "n/a"))

    items = []
    for j, p in enumerate(inst.fit):
        t = paired_test(fit_ba[:, j], fit_bb[:, j])
        items.append({"item": f"{p['ba']} vs {p['bb']}", "prop": inst.prop(p), "label": p["text"],
                      "wording": "differs" if p["wording_differs"] else "same", **t})
    for row, p_adj in zip(items, holm([r["p_wilcoxon"] for r in items])):
        row["p_holm"] = p_adj
        row["verdict"] = verdict(row["mean_diff"] > 0, p_adj, row["d_z"])
    res["items"] = items

    ok = complete_rows(fit_ba, fit_bb)
    comp = paired_test(fit_ba[ok].mean(1), fit_bb[ok].mean(1))
    comp["verdict"] = verdict(comp["mean_diff"] > 0, comp["p_t"], comp["d_z"])
    res["composite"] = comp

    # P8 TLX (lower = less workload, so ATLAS is favoured when the difference is negative)
    ok = complete_rows(tlx_ba, tlx_bb)
    raw = paired_test(tlx_ba[ok].mean(1), tlx_bb[ok].mean(1))
    raw["verdict"] = verdict(raw["mean_diff"] < 0, raw["p_t"], raw["d_z"])
    res["tlx_raw"] = raw
    subs = [{"item": f"{p['ba']} vs {p['bb']}", "label": name, **paired_test(tlx_ba[:, j], tlx_bb[:, j])}
            for j, (p, name) in enumerate(zip(inst.tlx, resp.tlx_names))]
    for row, p_adj in zip(subs, holm([r["p_wilcoxon"] for r in subs])):
        row["p_holm"] = p_adj
    res["tlx_subscales"] = subs

    # P9
    c1 = resp.c1[~np.isnan(resp.c1)]
    c1_res = {"n": len(c1), "median": np.nan, "mean": np.nan, "pct_agree": np.nan, "z": np.nan, "r": np.nan, "p": np.nan}
    if len(c1) >= 3:
        d = c1 - NEUTRAL
        z = wilcoxon_z(d)
        p = float(stats.wilcoxon(d).pvalue) if np.any(d != 0) else 1.0
        c1_res.update(median=float(np.median(c1)), mean=float(c1.mean()), pct_agree=float((c1 >= 5).mean()),
                      z=z, r=z / math.sqrt(len(c1)), p=p)
    res["c1"] = c1_res
    c2 = resp.c2[~np.isnan(resp.c2)]
    c2_labels = [(-2, "Strongly preferred the baseline"), (-1, "Somewhat preferred the baseline"), (0, "No preference"),
                 (1, "Somewhat preferred the proposed"), (2, "Strongly preferred the proposed")]
    res["c2_counts"] = [(text, int((c2 == score).sum()), float((c2 == score).mean()) if len(c2) else math.nan)
                        for score, text in c2_labels]
    k_atlas, k_base = int((c2 > 0).sum()), int((c2 < 0).sum())
    sign_p = float(stats.binomtest(k_atlas, k_atlas + k_base, 0.5).pvalue) if k_atlas + k_base else math.nan
    res["c2_sign"] = {"prefer_atlas": k_atlas, "prefer_baseline": k_base, "no_preference": int((c2 == 0).sum()), "p": sign_p}
    p9_ok = c1_res["median"] > NEUTRAL and c1_res["p"] < ALPHA and k_atlas > k_base and sign_p < ALPHA
    res["p9_verdict"] = ("Supported" if p9_ok else
                         "Insufficient data" if math.isnan(c1_res["p"]) else
                         "Partially supported" if (c1_res["p"] < ALPHA or sign_p < ALPHA) else "Not supported")

    # Exploratory
    with np.errstate(all="ignore"):
        fit_adv = np.nanmean(fit_bb, 1) - np.nanmean(fit_ba, 1)
        tlx_adv = np.nanmean(tlx_ba, 1) - np.nanmean(tlx_bb, 1)  # positive = ATLAS lighter
    explo = []
    for c, ranks in resp.ord.items():
        for name, outcome in (("Fit advantage (BB - BA)", fit_adv), ("Workload reduction (BA - BB TLX)", tlx_adv)):
            ok = ~np.isnan(ranks) & ~np.isnan(outcome)
            label = f"{c} {short(inst.items[c].text, 40)}"
            if ok.sum() >= 5 and np.ptp(ranks[ok]) > 0 and np.ptp(outcome[ok]) > 0:
                rho, p = stats.spearmanr(ranks[ok], outcome[ok])
                explo.append((label, name, int(ok.sum()), float(rho), float(p)))
            else:
                explo.append((label, name, int(ok.sum()), math.nan, math.nan))
    res["exploratory"] = explo

    n_pairs = int(complete.sum())
    res["power"] = [
        ("Complete paired respondents", n_pairs),
        (f"Smallest d_z detectable (alpha {ALPHA}, two-tailed, power {POWER})", min_detectable_dz(n_pairs)),
        (f"Paired respondents needed to detect d_z = {D_MIN}", required_n(D_MIN)),
    ]

    res["open"] = [(rid, c, inst.open_maps(c), short(inst.items[c].text, 90), txt)
                   for c in inst.open for rid, txt in zip(resp.ids, resp.text[c]) if txt]
    res["open_counts"] = [(c, short(inst.items[c].text, 70), inst.open_maps(c), sum(1 for t in resp.text[c] if t))
                          for c in inst.open]
    res["kappa"] = intercoder(coding) if coding else None
    return res


def intercoder(path: Path) -> dict:
    """Per-code presence kappa from a CSV with columns respondent_id, item, coder1, coder2.

    Codes in a cell are separated by ';'. Each (unit, code) pair is one yes/no decision."""
    _, rows = read_csv(path)
    units = [(r[2], r[3]) for r in rows if len(r) >= 4]
    split = [({c.strip() for c in a.split(";") if c.strip()}, {c.strip() for c in b.split(";") if c.strip()}) for a, b in units]
    codes = sorted(set().union(*[a | b for a, b in split])) if split else []
    per_code, pooled_x, pooled_y = [], [], []
    for code in codes:
        x = [int(code in a) for a, _ in split]
        y = [int(code in b) for _, b in split]
        pooled_x += x
        pooled_y += y
        per_code.append((code, sum(x), sum(y), sum(i == j for i, j in zip(x, y)) / len(x), cohen_kappa(x, y)))
    pooled = cohen_kappa(pooled_x, pooled_y)
    agree = sum(i == j for i, j in zip(pooled_x, pooled_y)) / len(pooled_x) if pooled_x else math.nan
    return {"units": len(units), "per_code": per_code, "pooled_kappa": pooled, "pooled_agreement": agree}


# ---------------------------------------------------------------- output

HEADER_FILL = PatternFill("solid", fgColor="DDE4EE")


def add_sheet(wb: Workbook, title: str, header: list[str], rows: list, note: str | None = None):
    ws = wb.create_sheet(title)
    start = 1
    if note:
        ws.cell(1, 1, note).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(header), 1))
        ws.row_dimensions[1].height = 15 * max(1, len(note) // 110 + 1)
        start = 3
    for c, h in enumerate(header, 1):
        cell = ws.cell(start, c, h)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for r, row in enumerate(rows, start + 1):
        for c, v in enumerate(row, 1):
            if isinstance(v, (float, np.floating)):
                v = None if math.isnan(v) else float(v)
                cell = ws.cell(r, c, v)
                cell.number_format = "0.000"
            else:
                cell = ws.cell(r, c, v)
            if isinstance(v, str) and len(v) > 60:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    for c, h in enumerate(header, 1):
        width = max([len(str(h))] + [len(str(row[c - 1])) for row in rows if c - 1 < len(row)] + [8])
        ws.column_dimensions[get_column_letter(c)].width = min(width + 2, 70)
    ws.freeze_panes = ws.cell(start + 1, 1)
    return ws


TEST_COLS = ["n", "median_baseline", "median_atlas", "mean_baseline", "mean_atlas", "mean_diff", "ci_low",
             "ci_high", "d_z", "t", "p_t", "wilcoxon_W", "z", "r", "p_wilcoxon"]
TEST_HEADERS = ["n pairs", "Median baseline", "Median ATLAS", "Mean baseline", "Mean ATLAS", "Mean diff (ATLAS - baseline)",
                "95% CI low", "95% CI high", "Cohen's d_z", "t", "p (paired t)", "Wilcoxon W", "Z", "r = Z/sqrt(n)", "p (Wilcoxon)"]


def write_workbook(res: dict, path: Path, label: str):
    wb = Workbook()
    wb.remove(wb.active)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n_tlx = res["n_tlx"]
    add_sheet(wb, "README", ["Field", "Value"], [
        ("Data set", label),
        ("Generated", stamp),
        ("Instrument", f"Parsed from the CSV header: {res['n_fit']} fit pairs, {n_tlx} TLX pairs (see 'Instrument' sheet)."),
        ("Direction", "Differences are ATLAS minus baseline. Fit: higher = better. TLX: lower = less workload."),
        ("Item tests", "Wilcoxon signed-rank (zeros dropped), Holm-corrected within each family; r = Z / sqrt(n pairs)."),
        ("Acceptance", f"Supported = favours ATLAS, adjusted p < {ALPHA} and |d_z| >= {D_MIN} (manuscript clause)."),
        ("TLX", f"Answered on {res['tlx_scale']}, rescaled to 0-100. Raw TLX = unweighted mean of the {n_tlx} subscales."),
        ("Warnings", "\n".join(res["warnings"]) or "none"),
    ])
    add_sheet(wb, "Instrument", ["CSV column", "Code", "Used as", "Proposition / maps to", "Question text (from header)"],
              res["instrument"], note="Every column of the export and how it was classified from its question code.")
    add_sheet(wb, "Sample", ["Measure", "Value"], res["sample"])
    add_sheet(wb, "Profile (Section A)", ["Item", "Question", "Answer", "n", "Share"], res["profile"])
    add_sheet(wb, "Reliability", ["Scale", "Items", "n (complete)", "Cronbach's alpha", "Interpretation"], res["reliability"])
    add_sheet(wb, "Fit items", ["Items", "Proposition", "Statement", "Pair wording"] + TEST_HEADERS + ["p (Holm)", "Verdict"],
              [[r["item"], r["prop"], r["label"], r["wording"]] + [r[c] for c in TEST_COLS] + [r["p_holm"], r["verdict"]]
               for r in res["items"]],
              note="Each baseline (BA1.k) vs ATLAS (BB1.k) rating on the 1-7 agreement scale.")
    c = res["composite"]
    add_sheet(wb, "Fit composite", ["Measure"] + TEST_HEADERS + ["Verdict (paired t)"],
              [[f"Mean of {res['n_fit']} fit items"] + [c[k] for k in TEST_COLS] + [c["verdict"]]],
              note="Complete cases only. Use if Reliability shows alpha >= .70 for both scales.")
    t = res["tlx_raw"]
    add_sheet(wb, "P8 workload", ["Measure"] + TEST_HEADERS + ["p (Holm)", "Verdict"],
              [[f"Raw TLX (mean of {n_tlx})"] + [t[k] for k in TEST_COLS] + [math.nan, t["verdict"]]]
              + [[f"{s['item']} {s['label']}"] + [s[k] for k in TEST_COLS] + [s["p_holm"], ""] for s in res["tlx_subscales"]],
              note=f"0-100 (rescaled from {res['tlx_scale']}), lower = less workload; a negative mean difference favours ATLAS. "
                   f"Subscales Holm-corrected as one family of {n_tlx}.")
    c1, sg = res["c1"], res["c2_sign"]
    add_sheet(wb, "P9 adoption", ["Measure", "Value"], [
        ("C1 n", c1["n"]), ("C1 median (1-7)", c1["median"]), ("C1 mean", c1["mean"]),
        ("C1 share agreeing (5-7)", c1["pct_agree"]), (f"C1 Wilcoxon vs {NEUTRAL}: Z", c1["z"]),
        ("C1 r", c1["r"]), ("C1 p", c1["p"]),
        ("C2 prefers ATLAS", sg["prefer_atlas"]), ("C2 prefers baseline", sg["prefer_baseline"]),
        ("C2 no preference", sg["no_preference"]), ("C2 sign test p (ties excluded)", sg["p"]),
        ("P9 verdict", res["p9_verdict"]),
    ] + [(f"C2: {text}", f"{n} ({share:.0%})" if not math.isnan(share) else n) for text, n, share in res["c2_counts"]])
    add_sheet(wb, "Exploratory", ["Profile item", "Outcome", "n", "Spearman rho", "p (uncorrected)"], res["exploratory"],
              note="Exploratory only: not part of any proposition test, no multiplicity correction.")
    add_sheet(wb, "Power", ["Measure", "Value"], res["power"])
    add_sheet(wb, "Open-ended counts", ["Item", "Prompt", "Maps to", "Non-empty answers"], res["open_counts"])
    add_sheet(wb, "Open-ended for coding",
              ["Respondent", "Item", "Maps to", "Prompt", "Answer", "Coder 1 codes (;)", "Coder 2 codes (;)"],
              [list(r) + ["", ""] for r in res["open"]],
              note="Code with the ATLAS survey qualitative codebook. Save respondent, item, coder1, coder2 as CSV and pass --coding for kappa.")
    if res["kappa"]:
        k = res["kappa"]
        add_sheet(wb, "Inter-coder agreement", ["Code", "Coder 1 uses", "Coder 2 uses", "% agreement", "Cohen's kappa"],
                  k["per_code"] + [("POOLED (all codes)", "", "", k["pooled_agreement"], k["pooled_kappa"])],
                  note=f"{k['units']} double-coded answers; each answer x code is one present/absent decision.")
    verdicts = [[r["prop"], short(r["label"], 80), PIPELINE_EVIDENCE.get(r["prop"], ""),
                 f"median {f0(r['median_baseline'])} -> {f0(r['median_atlas'])}; d_z = {f2(r['d_z'])}; {p_eq(r['p_holm'], 'p(Holm)')}",
                 r["verdict"], "", ""] for r in res["items"]]
    verdicts.append(["P8", "Cognitive workload (Raw TLX)", PIPELINE_EVIDENCE["P8"],
                     f"{f2(t['mean_baseline'])} -> {f2(t['mean_atlas'])}; d_z = {f2(t['d_z'])}; {p_eq(t['p_t'])}", t["verdict"], "", ""])
    verdicts.append(["P9", "Adoption intent (C1, C2)", PIPELINE_EVIDENCE["P9"],
                     f"C1 median {f0(c1['median'])}, {p_eq(c1['p'])}; C2 {sg['prefer_atlas']} vs {sg['prefer_baseline']}, {p_eq(sg['p'])}",
                     res["p9_verdict"], "", ""])
    add_sheet(wb, "Proposition verdicts",
              ["Proposition", "Construct", "Pipeline evidence (refresh before reporting)", "Survey result", "Survey verdict",
               "Qualitative theme (from coding)", "Convergence (confirms / expands / discordant)"], verdicts,
              note="Joint-display scaffold: fill the last two columns after qualitative coding.")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def fmt_p(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "n/a"
    return "<.001" if p < 0.001 else f"{p:.3f}".lstrip("0")


def p_eq(p: float, name: str = "p") -> str:
    text = fmt_p(p)
    return f"{name} < .001" if text == "<.001" else f"{name} = {text}"


def f2(v) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.2f}"


def f0(v) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.0f}"


def write_markdown(res: dict, path: Path, label: str):
    L = [f"# ATLAS survey analysis -- {label}", "",
         f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Differences are ATLAS minus baseline.", ""]
    L += ["## Sample", "", "| Measure | Value |", "|---|--:|"] + [f"| {m} | {v} |" for m, v in res["sample"]] + [""]
    L += ["## Reliability", "", "| Scale | Items | n | alpha |", "|---|--:|--:|--:|"]
    L += [f"| {s} | {k} | {n} | {f2(a)} |" for s, k, n, a, _ in res["reliability"]] + [""]
    L += [f"## Architectural fit ({res['n_fit']} pairs, 1-7)", "",
          "| Prop. | Statement | n | Median BA -> BB | Mean diff [95% CI] | d_z | r | p (Holm) | Verdict |",
          "|---|---|--:|---|---|--:|--:|--:|---|"]
    for r in res["items"]:
        L.append(f"| {r['prop']} | {short(r['label'], 60)} | {r['n']} | {f0(r['median_baseline'])} -> {f0(r['median_atlas'])} | "
                 f"{f2(r['mean_diff'])} [{f2(r['ci_low'])}, {f2(r['ci_high'])}] | {f2(r['d_z'])} | {f2(r['r'])} | "
                 f"{fmt_p(r['p_holm'])} | {r['verdict']} |")
    c = res["composite"]
    L += ["", f"Fit composite (mean of {res['n_fit']}): {f2(c['mean_baseline'])} -> {f2(c['mean_atlas'])}, "
              f"diff {f2(c['mean_diff'])} [{f2(c['ci_low'])}, {f2(c['ci_high'])}], d_z = {f2(c['d_z'])}, "
              f"t = {f2(c['t'])}, {p_eq(c['p_t'])} -- {c['verdict']}.", ""]
    t = res["tlx_raw"]
    L += [f"## P8: workload (Raw TLX, 0-100 from {res['tlx_scale']}, lower is better)", "",
          f"Raw TLX {f2(t['mean_baseline'])} -> {f2(t['mean_atlas'])}, diff {f2(t['mean_diff'])} "
          f"[{f2(t['ci_low'])}, {f2(t['ci_high'])}], d_z = {f2(t['d_z'])}, {p_eq(t['p_t'])} -- {t['verdict']}.", "",
          "| Subscale | Mean BA -> BB | d_z | p (Holm) |", "|---|---|--:|--:|"]
    L += [f"| {s['label']} | {f2(s['mean_baseline'])} -> {f2(s['mean_atlas'])} | {f2(s['d_z'])} | {fmt_p(s['p_holm'])} |"
          for s in res["tlx_subscales"]] + [""]
    c1, sg = res["c1"], res["c2_sign"]
    L += ["## P9: adoption", "",
          (f"C1 median {f2(c1['median'])} ({c1['pct_agree']:.0%} agree), Wilcoxon vs {NEUTRAL}: r = {f2(c1['r'])}, {p_eq(c1['p'])}."
           if c1["n"] >= 3 else f"C1: {c1['n']} answers -- too few to test."),
          f"C2: {sg['prefer_atlas']} prefer ATLAS, {sg['prefer_baseline']} prefer baseline, {sg['no_preference']} no preference; "
          f"sign test {p_eq(sg['p'])}. Verdict: {res['p9_verdict']}.", ""]
    L += ["## Sensitivity", ""] + [f"- {m}: {f2(v) if isinstance(v, float) else v}" for m, v in res["power"]] + [""]
    L += ["## Open-ended answers", "", "| Item | Maps to | Answers |", "|---|---|--:|"]
    L += [f"| {i} | {m} | {n} |" for i, _, m, n in res["open_counts"]] + [""]
    if res["kappa"]:
        k = res["kappa"]
        L += [f"Inter-coder agreement: pooled kappa = {f2(k['pooled_kappa'])} over {k['units']} answers.", ""]
    if res["warnings"]:
        L += ["## Warnings", ""] + [f"- {w}" for w in res["warnings"]] + [""]
    path.write_text("\n".join(L), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--input", required=True, type=Path, help="CSV export of the questionnaire responses")
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "output", help="where to write the results")
    ap.add_argument("--label", default=None, help="data-set label shown in the outputs (default: input file name)")
    ap.add_argument("--tlx-scale", choices=sorted(TLX_SCALES), default="0-10",
                    help="scale the TLX questions were answered on (default 0-10); rescaled to 0-100")
    ap.add_argument("--coding", type=Path, default=None,
                    help="double-coded open-ended answers CSV (respondent_id,item,coder1,coder2) for Cohen's kappa")
    ap.add_argument("--no-consent-filter", action="store_true", help="analyse every row (no consent column)")
    ap.add_argument("--performance-high-is-good", action="store_true",
                    help="reverse TLX Performance (use only if the form's scale ran Failure .. Perfect)")
    args = ap.parse_args(argv)

    headers, rows = read_csv(args.input)
    inst = Instrument(headers)
    resp = Responses(inst, rows, consent_filter=not args.no_consent_filter, tlx_scale=args.tlx_scale,
                     performance_high_is_good=args.performance_high_is_good)
    label = args.label or args.input.name
    res = analyse(resp, args.coding)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    xlsx, md = args.out_dir / "survey_analysis.xlsx", args.out_dir / "survey_analysis.md"
    write_workbook(res, xlsx, label)
    write_markdown(res, md, label)
    print(f"instrument: {len(inst.items)} coded questions -- {len(inst.profile)} profile, {len(inst.fit)} fit pairs, "
          f"{len(inst.tlx)} TLX pairs, {len(inst.open)} open-ended, C1={bool(inst.c1)}, C2={bool(inst.c2)}; "
          f"{len(inst.ignored)} uncoded column(s) ignored")
    print(f"{resp.n} consented respondents ({resp.n_declined} declined) -> {xlsx}")
    print(f"summary -> {md}")
    for w in res["warnings"]:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
