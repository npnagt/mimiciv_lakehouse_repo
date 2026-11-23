"""Write-audit-publish with data-quality rules on the lakehouse."""
import duckdb
import pandas as pd

# (rule, table, dimension, SQL -> (failed, total), min pass rate, action)
RULES = [
    ("age present", "obt", "Completeness",
     "SELECT COUNT(*) FILTER (WHERE age_at_admission IS NULL), COUNT(*)"
     " FROM {obt}", 0.99, "block"),
    ("age 0-120", "obt", "Validity",
     "SELECT COUNT(*) FILTER (WHERE age_at_admission NOT BETWEEN 0 AND 120),"
     " COUNT(*) FROM {obt}", 1.0, "block"),
    ("one row per admission", "obt", "Uniqueness",
     "SELECT COUNT(*) - COUNT(DISTINCT hadm_id), COUNT(*) FROM {obt}",
     1.0, "block"),
    ("known admission type", "obt", "Validity",
     "SELECT COUNT(*) FILTER (WHERE admission_type NOT IN"
     " ('EMERGENCY','URGENT','ELECTIVE')), COUNT(*) FROM {obt}", 1.0, "warn"),
    ("discharge after admission", "obt", "Consistency",
     "SELECT COUNT(*) FILTER (WHERE disch_time < admit_time), COUNT(*)"
     " FROM {obt}", 1.0, "block"),
    ("note links to an admission", "note", "Integrity",
     "SELECT COUNT(*) FILTER (WHERE o.hadm_id IS NULL), COUNT(*)"
     " FROM {note} n LEFT JOIN {obt} o USING (hadm_id)", 1.0, "block"),
    ("note text present", "note", "Completeness",
     "SELECT COUNT(*) FILTER (WHERE coalesce(trim(text), '') = ''),"
     " COUNT(*) FROM {note}", 0.99, "warn"),
    ("note stored within 30 days", "note", "Timeliness",
     "SELECT COUNT(*) FILTER (WHERE n.last_storetime >"
     " o.disch_time + INTERVAL 30 DAY), COUNT(*)"
     " FROM {note} n JOIN {obt} o USING (hadm_id)", 0.98, "warn"),
    ("known tobacco category", "nlp", "Validity",
     "SELECT COUNT(*) FILTER (WHERE tobacco_use NOT IN"
     " ('current','former','never')), COUNT(*) FROM {nlp}", 1.0, "warn"),
    ("NLP coverage of admissions", "nlp", "Completeness",
     "SELECT COUNT(*) FILTER (WHERE x.hadm_id IS NULL), COUNT(*)"
     " FROM {obt} o LEFT JOIN {nlp} x USING (hadm_id)", 0.95, "warn"),
]
TABLES = {"obt": "obt_admission_features", "note": "fact_discharge_note",
          "nlp": "fact_discharge_note_nlp"}


def audit(con, schema):
    """Run every rule against the tables in `schema`; return a scorecard."""
    t = {k: f"{schema}.{v}" for k, v in TABLES.items()}
    rows = []
    for name, table, dim, sql, threshold, action in RULES:
        failed, total = con.execute(sql.format(**t)).fetchone()
        rate = 1 - failed / total if total else 1.0
        status = ("pass" if rate >= threshold
                  else "BLOCK" if action == "block" else "warn")
        rows.append(dict(rule=name, table=TABLES[table], dimension=dim,
                         failed=failed, total=total, pass_rate=round(rate, 4),
                         threshold=threshold, action=action, status=status))
    return pd.DataFrame(rows)


def write_audit_publish(db, batch):
    """Stage main + new batch, audit it, publish only if nothing blocks."""
    con = duckdb.connect(db)
    con.execute("DROP SCHEMA IF EXISTS audit CASCADE; CREATE SCHEMA audit")
    for name, df in batch.items():                  # 1. WRITE to a branch
        con.register("b", df)
        con.execute(f"CREATE TABLE audit.{name} AS SELECT * FROM main.{name}"
                    " UNION ALL BY NAME SELECT * FROM b")
        con.unregister("b")
    card = audit(con, "audit")                      # 2. AUDIT
    publish = not (card["status"] == "BLOCK").any()
    if publish:                                     # 3. PUBLISH atomically
        con.execute("BEGIN")
        for name in batch:
            con.execute(f"CREATE OR REPLACE TABLE main.{name} AS"
                        f" SELECT * FROM audit.{name}")
        con.execute("COMMIT")
    con.execute("DROP SCHEMA audit CASCADE")        # keep it to investigate
    con.close()
    return card, publish
