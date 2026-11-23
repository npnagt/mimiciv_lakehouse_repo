# Chapter 17 companion code: an analytics agent on the lakehouse

A minimal agent that answers clinical-operations questions over a lakehouse organized by the
Multimodal Fusion Schema. All data is **synthetic**: it has the same table shapes as the
book's MIMIC-IV reference implementation but contains no real patient records.

## Files

| File | Purpose |
|---|---|
| `make_demo_lakehouse.py` | Creates `demo_lakehouse.duckdb` (1,365 synthetic admissions, notes, NLP features, readmission view) |
| `lakehouse_mcp_server.py` | MCP server: `list_tables`, `describe_table`, read-only `run_sql`, `search_notes`, `log_answer` |
| `agent.py` | Framework-free agent loop using the Anthropic API and the MCP server |
| `sdk_agent.py` | The same server used from the Claude Agent SDK (skills, tool allow-list, budget) |
| `.claude/skills/readmission-analysis/SKILL.md` | Agent Skill encoding how to do a readmission analysis |
| `test_plumbing.py` | Runs `agent.py` end to end with a scripted stand-in model (no API key needed) |

## Run

```
pip install "mcp>=2" duckdb pandas numpy anthropic claude-agent-sdk
python make_demo_lakehouse.py
python test_plumbing.py                      # no API key needed
set ANTHROPIC_API_KEY=...                    # Windows (export on macOS/Linux)
python agent.py "Is readmission higher for heart-failure patients?"
python sdk_agent.py                          # framework version
```

Tested on 2026-10-16 with Python 3.14, mcp 2.3.0, duckdb 1.5.6, anthropic 1.15.0, and
claude-agent-sdk 0.2.168. The live-model runs (`agent.py`, `sdk_agent.py`) were not executed in
that test because no API key was available; `test_plumbing.py` exercised everything else.
MCP Python SDK 2.x renamed `FastMCP` to `MCPServer`; with mcp 1.x use
`from mcp.server.fastmcp import FastMCP` and `t.inputSchema` instead.
