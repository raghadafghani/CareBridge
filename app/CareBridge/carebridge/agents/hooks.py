"""Hooks — deterministic code inside the agent loop.

Workshop Module 2: a hook implements HookProvider and registers callbacks on
lifecycle events. The workshop's RateLimiterHook listens for
BeforeInvocationEvent (reset the counters) and BeforeToolCallEvent (count
the call). Setting `event.cancel_tool` skips the tool and sends that string
back to the model as the tool result, so the model stops retrying.

CareBridge uses the same two events, plus AfterToolCallEvent so a caller can
inspect the loop while it runs. Module 1 prints `agent.messages` after the
fact; LoopTraceHook records the same stages as they happen:

    Input & context → Reasoning → Tool selection → Tool execution → Response

MedicationBoundaryHook is the same cancel_tool mechanism applied to a
clinical rule: a tool argument must not carry a dose change. It does not
inspect the patient's own words, so a report of "should I double my dose?"
still reaches the safety specialist.
"""

from __future__ import annotations

import json
from typing import Any

from strands.hooks import (
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

_DOSE_CHANGE = ("double the dose", "double my dose", "extra dose", "increase the dose", "stop taking")
_GUARDED_TOOLS = {"explain_medication", "commit_care_plan", "today_recovery_schedule"}


class RateLimiterHook(HookProvider):
    """Cap each tool at max_calls per invocation. Same control as the workshop hook."""

    def __init__(self, max_calls: int = 3) -> None:
        self.max_calls = max_calls
        self.counts: dict[str, int] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self.reset)
        registry.add_callback(BeforeToolCallEvent, self.check)

    def reset(self, event: BeforeInvocationEvent) -> None:
        """Module 2 resets per request, not for the life of the agent."""
        del event
        self.counts = {}

    def check(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use["name"]
        self.counts[name] = self.counts.get(name, 0) + 1
        if self.counts[name] > self.max_calls:
            event.cancel_tool = (
                f"'{name}' hit the {self.max_calls}-call limit. Do NOT call this tool again. "
                "If this is commit_care_plan and it has not returned SAVED, say that the plan "
                "could not be saved. Do not paste the discharge note to the patient."
            )


class MedicationBoundaryHook(HookProvider):
    """Refuse tool arguments that ask the tool to change a dose.

    Workshop alignment: Module 2, `BeforeToolCallEvent.cancel_tool`. The
    patient's report is not scanned here; only tools that read or write the
    plan are. Escalation stays with the safety specialist.
    """

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.check)

    def check(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use.get("name", "")
        if name not in _GUARDED_TOOLS:
            return
        raw = json.dumps(event.tool_use.get("input", {}), default=str).lower()
        if any(phrase in raw for phrase in _DOSE_CHANGE):
            event.cancel_tool = (
                "This tool cannot change a medication dose. Tell the patient to check "
                "with their pharmacist or care team before taking anything different."
            )


class LoopTraceHook(HookProvider):
    """Record loop stages for the CLI and the API trace.

    Module 1 teaches you to read `agent.messages` and `result.metrics` after
    the call. This hook subscribes to the same lifecycle so the stages are
    visible while the loop is running. It never cancels a tool.
    """

    def __init__(self, sink: list[str] | None = None) -> None:
        self.steps: list[str] = sink if sink is not None else []

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self.on_start)
        registry.add_callback(BeforeToolCallEvent, self.on_select)
        registry.add_callback(AfterToolCallEvent, self.on_execute)

    def on_start(self, event: BeforeInvocationEvent) -> None:
        del event
        self.steps.append("Input & context")

    def on_select(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use.get("name", "unknown")
        self.steps.append(f"Tool selection: {name}")

    def on_execute(self, event: AfterToolCallEvent) -> None:
        name = event.tool_use.get("name", "unknown")
        status = "error" if getattr(event, "exception", None) else "ok"
        self.steps.append(f"Tool execution: {name} ({status})")
