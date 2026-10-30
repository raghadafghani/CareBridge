"""Read text and tool names out of Strands message dicts.

Module 1 inspects `agent.messages`, where a user turn, an assistant `toolUse`
block, and a user `toolResult` block are the loop written down. Steering
handlers use the same structure to see what the patient just said.
"""

from __future__ import annotations

import re
from typing import Any

_THINKING = re.compile(r"<thinking>.*?</thinking>", re.IGNORECASE | re.DOTALL)

# Prefix the SDK stores as a user message when a handler returns Guide.
# Skipping it stops a retry from treating our own guidance as a new symptom.
GUIDE_PREFIX = "Steering guidance:"


def patient_visible_text(text: str) -> str:
    """Drop model scaffolding before a reply is shown to the patient."""
    return _THINKING.sub("", text).strip()


def message_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    parts: list[str] = []
    for block in message.get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts).strip()


def latest_patient_text(agent: Any) -> str:
    """Last human message, ignoring tool results and steering retries."""
    for message in reversed(getattr(agent, "messages", None) or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content") or []
        if any(isinstance(block, dict) and "toolResult" in block for block in content):
            continue
        text = message_text(message)
        if not text or text.startswith(GUIDE_PREFIX):
            continue
        return text
    return ""


def is_tool_stop(stop_reason: Any) -> bool:
    """True while the model is still selecting a tool. Steering waits for the final draft."""
    label = str(getattr(stop_reason, "value", stop_reason)).lower()
    return label.endswith("tool_use") or "tool_use" in label
