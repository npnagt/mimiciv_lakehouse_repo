"""A minimal tool-using agent: Claude + the lakehouse MCP server."""
import asyncio
import sys

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = "claude-sonnet-5-5"           # any model that supports tool use
SYSTEM = ("You are a hospital operations analyst. Use only the lakehouse "
          "tools. Read table descriptions before writing SQL, use governed "
          "metric definitions, cite admission IDs for examples, and say so "
          "when the data cannot answer the question.")


async def run_agent(question: str, client=None, max_steps: int = 10) -> str:
    server = StdioServerParameters(command=sys.executable,
                                   args=["lakehouse_mcp_server.py"])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            tools = [{"name": t.name, "description": t.description,
                      "input_schema": t.input_schema}
                     for t in (await mcp.list_tools()).tools
                     if t.name != "log_answer"]   # logging is not the model's job
            client = client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
            messages = [{"role": "user", "content": question}]
            for step in range(1, max_steps + 1):       # the agent loop
                reply = client.messages.create(        # 1. reason and decide
                    model=MODEL, max_tokens=2000, system=SYSTEM,
                    tools=tools, messages=messages)
                messages.append({"role": "assistant",
                                 "content": reply.content})
                if reply.stop_reason != "tool_use":    # no more tools: answer
                    answer = "".join(b.text for b in reply.content
                                     if b.type == "text")
                    await mcp.call_tool("log_answer", {"question": question,
                        "answer": answer, "model": MODEL, "steps": step})
                    return answer
                results = []
                for block in reply.content:            # 2. act through MCP
                    if block.type == "tool_use":
                        out = await mcp.call_tool(block.name, block.input)
                        results.append({"type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": out.content[0].text})
                messages.append({"role": "user",         # 3. observe
                                 "content": results})
            return "Stopped: step limit reached without an answer."


if __name__ == "__main__":
    print(asyncio.run(run_agent(" ".join(sys.argv[1:]) or
          "What is our 30-day readmission rate, and is it higher for "
          "patients with heart failure?")))
