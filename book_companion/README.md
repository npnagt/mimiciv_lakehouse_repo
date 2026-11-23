# Book companion code

Runnable examples from the book *Multimodal Data Architecture for Intelligent Enterprise*. The research edition is titled *End-to-End Data Architecture for Multimodal Data*. Both examples use **synthetic** data with the same table shapes as the MIMIC-IV reference implementation in this repository. They contain no real patient records and need no AWS account.

| Folder | Chapter | What it shows |
|---|---|---|
| [Chapter_17_Lakehouse_Agent](Chapter_17_Lakehouse_Agent/) | 17, Data for Agents, Agents for Data | An analytics agent that answers questions over the lakehouse. The pieces: an MCP server with governed, read-only tools; a framework-free agent loop (`agent.py`); a Claude Agent SDK version; an Agent Skill; and a plumbing test that needs no API key. |
| [Chapter_20_Data_Quality](Chapter_20_Data_Quality/) | 20, Measuring Success and Maintaining Trust | Ten SQL quality rules and a write–audit–publish gate. The demo blocks a defective batch and publishes a clean one. |

## Quick start

```
cd book_companion/Chapter_17_Lakehouse_Agent
pip install "mcp>=2" duckdb pandas numpy anthropic claude-agent-sdk
python make_demo_lakehouse.py       # creates demo_lakehouse.duckdb
python test_plumbing.py             # end-to-end test, no API key needed

cd ../Chapter_20_Data_Quality
python run_demo.py                  # uses make_demo_lakehouse.py from the Chapter 17 folder
```

Each folder's README lists its files and the versions it was tested with. Generated files, such as `*.duckdb`, `agent_inference.jsonl` and `scorecard_*.csv`, are not committed.

The book's spreadsheet companions are distributed with the book's companion materials, not in this repository. They are the TCO calculator, the business-case template, the governance and quality scorecard, and the roadmap planner.
