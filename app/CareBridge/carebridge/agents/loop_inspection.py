"""Print the agent loop the way Module 1 does.

After `result = agent(prompt)`, the workshop walks `agent.messages` and reads
`result.metrics`: cycles and total tokens. Tool calls show up as `toolUse`
blocks. This helper is that inspection, shared by the CLI. It truncates long
tool inputs so a discharge document is not dumped into the terminal.
"""

from __future__ import annotations

import json
from typing import Any


def inspect_loop(agent: Any, result: Any) -> str:
    messages = getattr(agent, "messages", None) or []
    lines = [f"Total messages: {len(messages)}"]
    for message in messages:
        role = message.get("role", "?")
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if "text" in block:
                lines.append(f"{role}: {str(block['text'])[:100]}")
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                payload = json.dumps(tool_use.get("input", {}), default=str)
                lines.append(f"tool call: {tool_use.get('name')}({payload[:120]})")
    metrics = getattr(result, "metrics", None)
    if metrics is not None:
        summary = metrics.get_summary() if hasattr(metrics, "get_summary") else {}
        usage = getattr(metrics, "accumulated_usage", {}) or {}
        lines.append(f"Cycles: {summary.get('total_cycles', 'n/a')}")
        lines.append(f"Tokens: {usage.get('totalTokens', 'n/a')}")
    return "\n".join(lines)
