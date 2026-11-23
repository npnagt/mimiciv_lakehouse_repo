# Chapter 20 companion code: data-quality rules with write–audit–publish

Ten SQL quality rules (completeness, validity, uniqueness, consistency, integrity, timeliness) and a
write–audit–publish gate over the **synthetic** lakehouse from Chapter 17.

| File | Purpose |
|---|---|
| `quality_checks.py` | The rules, `audit()` (runs every rule, returns a scorecard) and `write_audit_publish()` (stage, audit, publish only if nothing blocks) |
| `run_demo.py` | Builds the synthetic lakehouse, then stages a defective batch (blocked) and a clean batch (published); writes `scorecard_*.csv` |
| `demo_output.txt` | Output of the run reported in the chapter |

## Run

```
pip install duckdb pandas numpy
python run_demo.py
```

`run_demo.py` imports `make_demo_lakehouse.py` from the sibling folder `../Chapter_17_Lakehouse_Agent`.
Tested 2026-10-16 with Python 3.14 and duckdb 1.5.6. On an Iceberg lakehouse, replace the staging
schema with an Iceberg branch (`write.wap.enabled`, `spark.wap.branch`) and publish by
fast-forwarding `main`.

The companion workbook `ATLAS_Governance_Quality_Scorecard.xlsx` (distributed with the book's companion materials) holds the
same scorecard, plus metrics, maturity and compliance sheets.
