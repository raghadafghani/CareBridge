"""Invocation body for Amazon Bedrock AgentCore Runtime.

Workshop Module 5 wraps the same agent — same tools, hooks, skills, steering,
and session manager — in an entrypoint. The workshop's `invoke` reads
`payload["prompt"]` and returns the agent's reply. CareBridge keeps that
shape and adds an `action` so one deployed harness serves both UI screens.

    {"action": "extract", "document_text": "..."}
    {"action": "check_in", "plan_id": "...", "session_id": "...", "prompt": "..."}
    {"action": "proactive_check_in", "plan_id": "...", "session_id": "..."}

`session_id` must be at least 33 characters when you call the deployed
runtime with `agentcore invoke` or bedrock-agentcore `InvokeAgentRuntime`.
normalize_session_id pads shorter ids.

Observability: add aws-opentelemetry-distro when you deploy, as Module 5 does.
AgentCore then emits spans to CloudWatch. You do not add tracing code here.
The local Module 1 metrics (`result.metrics`) are the same signals, collected
for every production invocation.

app/CareBridge/main.py is the file AgentCore loads. It constructs
BedrockAgentCoreApp and calls this function from @app.entrypoint.
"""

from __future__ import annotations

from typing import Any

from carebridge.service import PROACTIVE_CHECKIN, extract_care_plan, run_check_in
from carebridge.agents.session import normalize_session_id


def invoke_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    body = payload or {}
    action = body.get("action") or "check_in"

    if action == "extract":
        document_text = body.get("document_text") or body.get("prompt")
        if not document_text:
            raise ValueError("Missing required field: document_text")
        plan, trace, reply = extract_care_plan(str(document_text), body.get("filename") or "discharge.txt")
        return {
            "response": reply,
            "plan": plan.model_dump(),
            "trace": trace,
        }

    prompt = body.get("prompt")
    plan_id = body.get("plan_id")
    if not plan_id:
        raise ValueError("Missing required field: plan_id")
    session_id = normalize_session_id(str(body.get("session_id") or f"{plan_id}-followup"))
    if action == "proactive_check_in":
        prompt = PROACTIVE_CHECKIN
    if not prompt:
        raise ValueError("Missing required field: prompt")

    reply = run_check_in(str(plan_id), session_id, str(prompt))
    return {
        "response": reply.text,
        "outcome": reply.outcome,
        "questions": reply.questions,
        "summary": reply.summary,
        "session_id": session_id,
        "trace": reply.trace,
    }
