"""The same lakehouse MCP server, used from the Claude Agent SDK."""
import asyncio
import sys

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from agent import SYSTEM

options = ClaudeAgentOptions(
    system_prompt=SYSTEM,
    mcp_servers={"lakehouse": {"command": sys.executable,
                               "args": ["lakehouse_mcp_server.py"]}},
    allowed_tools=["mcp__lakehouse__list_tables",       # read-only tools only;
                   "mcp__lakehouse__describe_table",    # nothing else allowed
                   "mcp__lakehouse__run_sql",
                   "mcp__lakehouse__search_notes"],
    setting_sources=["project"],    # loads .claude/skills/*/SKILL.md
    max_turns=12, max_budget_usd=0.50)                  # step and cost limits


async def main(question: str):
    async for message in query(prompt=question, options=options):
        if isinstance(message, ResultMessage):           # final answer + cost
            print(message.result)
            print(f"turns={message.num_turns} cost=${message.total_cost_usd}")


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or
                     "Which groups have the highest readmission rates?"))
