"""MCP server: a governed, read-only window onto the lakehouse."""
import json
import re
from datetime import datetime, timezone

import duckdb
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("atlas-lakehouse")
DB, LOG = "demo_lakehouse.duckdb", "agent_inference.jsonl"

# Semantic layer: what each table means, and governed metric definitions
CATALOG = {
    "obt_admission_features": "One row per admission (hadm_id): age, "
        "admission type, diagnosis_count, heart_failure, lab and "
        "length-of-stay roll-ups.",
    "v_admission_outcomes": "obt_admission_features plus readmit_30d (1 = "
        "readmitted within 30 days of discharge).",
    "fact_discharge_note": "Discharge-note text, one row per admission.",
    "fact_discharge_note_nlp": "tobacco_use, alcohol_use, obesity_level "
        "extracted from each discharge note.",
}
METRICS = {"readmission_rate_30d": "SELECT AVG(readmit_30d) FROM "
           "v_admission_outcomes  -- share readmitted within 30 days"}


@mcp.tool()
def list_tables() -> str:
    """List governed tables and metric definitions, with business meanings."""
    return json.dumps({"tables": CATALOG, "metrics": METRICS}, indent=1)


@mcp.tool()
def describe_table(table: str) -> str:
    """Show the columns and data types of one governed table."""
    if table not in CATALOG:
        return f"Unknown table '{table}'. Call list_tables first."
    with duckdb.connect(DB, read_only=True) as con:
        cols = con.execute(f"DESCRIBE {table}").fetchall()
    return "\n".join(f"{c[0]}: {c[1]}" for c in cols)


@mcp.tool()
def run_sql(query: str) -> str:
    """Run ONE read-only SELECT over governed tables; returns up to 50 rows."""
    single = ";" not in query.rstrip("; \n")
    if not (re.match(r"\s*(select|with)\b", query, re.I) and single):
        return "Rejected: only a single SELECT statement is allowed."
    with duckdb.connect(DB, read_only=True) as con:   # read-only by design
        try:
            return con.execute(query).fetchdf().head(50).to_csv(index=False)
        except duckdb.Error as e:
            return f"SQL error: {e}"      # lets the agent self-correct


@mcp.tool()
def search_notes(keyword: str, limit: int = 5) -> str:
    """Find discharge notes containing a keyword; returns IDs and excerpts."""
    with duckdb.connect(DB, read_only=True) as con:
        rows = con.execute("SELECT hadm_id, substr(text, 1, 160) FROM "
                           "fact_discharge_note WHERE text ILIKE ? LIMIT ?",
                           [f"%{keyword}%", min(limit, 20)]).fetchall()
    return "\n".join(f"{h}: {t}..." for h, t in rows) or "No matching notes."


@mcp.tool()
def log_answer(question: str, answer: str, model: str, steps: int) -> str:
    """Record the agent's final answer as an Inference Fact for audit."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "question": question,
           "answer": answer, "model": model, "steps": steps}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return "logged"


if __name__ == "__main__":
    mcp.run()          # stdio transport: any MCP-capable agent can connect
