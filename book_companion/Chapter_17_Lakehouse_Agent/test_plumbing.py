"""Exercise agent.py end to end without an API key: a scripted stand-in replaces the model and issues the
tool calls a model would make, so the MCP server, tools, guardrails, and logging are tested for real."""
import asyncio
import json
from types import SimpleNamespace as NS

import agent

SCRIPT = [
    ("list_tables", {}),
    ("describe_table", {"table": "v_admission_outcomes"}),
    ("run_sql", {"query": "DELETE FROM obt_admission_features"}),              # guardrail must reject
    ("run_sql", {"query": "SELECT heart_failur, AVG(readmit_30d) FROM v_admission_outcomes GROUP BY 1"}),  # typo -> error
    ("run_sql", {"query": "SELECT heart_failure, COUNT(*) AS admissions, ROUND(AVG(readmit_30d), 3) AS readmit_rate "
                          "FROM v_admission_outcomes GROUP BY heart_failure ORDER BY heart_failure"}),
    ("search_notes", {"keyword": "congestive heart failure", "limit": 2}),
]


class FakeModel:
    """Stands in for client.messages: replays SCRIPT, then answers from the last SQL result."""

    def __init__(self):
        self.messages = self
        self.i = 0
        self.transcript = []

    def create(self, **kw):
        msgs = kw["messages"]
        if msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], list):
            self.transcript.append(("observation", msgs[-1]["content"][0]["content"][:300]))
        if self.i < len(SCRIPT):
            name, args = SCRIPT[self.i]; self.i += 1
            self.transcript.append(("tool call", f"{name}({json.dumps(args)})"))
            return NS(stop_reason="tool_use", content=[NS(type="tool_use", id=f"t{self.i}", name=name, input=args)])
        sql = [c for c in self.transcript if c[0] == "observation" and "readmit_rate" in c[1]][-1][1]
        text = f"Readmission by heart-failure status (from v_admission_outcomes):\n{sql}"
        return NS(stop_reason="end_turn", content=[NS(type="text", text=text)])


if __name__ == "__main__":
    fake = FakeModel()
    answer = asyncio.run(agent.run_agent("What is our 30-day readmission rate, and is it higher for heart failure?", client=fake))
    for kind, text in fake.transcript:
        print(f"[{kind}] {text}\n")
    print("[final answer]", answer)
    with open("agent_inference.jsonl", encoding="utf-8") as f:
        print("[inference fact]", f.readlines()[-1][:200])
