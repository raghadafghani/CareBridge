"""Hooks and steering, without calling Amazon Bedrock.

Module 2's RateLimiterHook is tested by counting tool calls and reading
`cancel_tool`. Module 3's handlers are tested by calling steer_before_tool
and steer_after_model with a fake ledger, the same record LedgerProvider
fills during a real loop.
"""

import asyncio
from types import SimpleNamespace

from strands.vended_plugins.steering import Guide, Proceed

from carebridge.agents.hooks import MedicationBoundaryHook, RateLimiterHook
from carebridge.safety.messages import GUIDE_PREFIX
from carebridge.agents.steering import (
    CheckInWorkflowHandler,
    ClinicalBoundaryHandler,
    PlanCommitHandler,
    RelayOutcomeHandler,
)
from carebridge.safety.turn_state import set_turn_assessment
from carebridge.safety.warning_signs import Assessment


def _run(coro):
    return asyncio.run(coro)


def _ledger(handler, calls):
    handler.steering_context.data.set("ledger", {"tool_calls": calls})
    handler._ledger_len_at_start = 0
    handler._guides = 0


def test_rate_limiter_cancels_the_call_past_the_cap():
    hook = RateLimiterHook(max_calls=2)
    first = SimpleNamespace(tool_use={"name": "load_care_plan"})
    second = SimpleNamespace(tool_use={"name": "load_care_plan"})
    third = SimpleNamespace(tool_use={"name": "load_care_plan"})
    hook.check(first)
    hook.check(second)
    hook.check(third)
    assert not hasattr(first, "cancel_tool")
    assert "2-call limit" in third.cancel_tool

    hook.reset(SimpleNamespace())
    again = SimpleNamespace(tool_use={"name": "load_care_plan"})
    hook.check(again)
    assert not hasattr(again, "cancel_tool")


def test_medication_hook_blocks_a_dose_change_argument_only():
    hook = MedicationBoundaryHook()
    blocked = SimpleNamespace(
        tool_use={"name": "explain_medication", "input": {"medication_name": "double the dose"}}
    )
    allowed = SimpleNamespace(
        tool_use={"name": "safety_review_specialist", "input": {"patient_report": "Should I double the dose?"}}
    )
    hook.check(blocked)
    hook.check(allowed)
    assert "cannot change" in blocked.cancel_tool
    assert not hasattr(allowed, "cancel_tool")


def test_plan_commit_requires_the_document_first():
    handler = PlanCommitHandler()
    _ledger(handler, [])
    blocked = _run(
        handler.steer_before_tool(agent=None, tool_use={"name": "commit_care_plan", "input": {}})
    )
    assert isinstance(blocked, Guide)
    assert GUIDE_PREFIX in blocked.reason

    _ledger(handler, [{"tool_name": "read_discharge_document", "status": "success"}])
    allowed = _run(
        handler.steer_before_tool(agent=None, tool_use={"name": "commit_care_plan", "input": {}})
    )
    assert isinstance(allowed, Proceed)


def test_symptom_reply_requires_the_safety_specialist():
    handler = CheckInWorkflowHandler()
    _ledger(handler, [{"tool_name": "load_care_plan", "status": "success"}])
    agent = SimpleNamespace(
        messages=[{"role": "user", "content": [{"text": "My temperature is 38.5 C"}]}]
    )
    blocked = _run(
        handler.steer_after_model(
            agent=agent,
            message={"role": "assistant", "content": [{"text": "That sounds fine."}]},
            stop_reason="end_turn",
        )
    )
    assert isinstance(blocked, Guide)

    _ledger(
        handler,
        [
            {"tool_name": "load_care_plan", "status": "success"},
            {"tool_name": "safety_review_specialist", "status": "success"},
        ],
    )
    schedule = SimpleNamespace(
        messages=[{"role": "user", "content": [{"text": "When do I take the antibiotic?"}]}]
    )
    allowed = _run(
        handler.steer_after_model(
            agent=schedule,
            message={"role": "assistant", "content": [{"text": "It is listed at 08:00 and 20:00."}]},
            stop_reason="end_turn",
        )
    )
    assert isinstance(allowed, Proceed)


def test_schedule_tool_is_blocked_until_the_plan_is_loaded():
    handler = CheckInWorkflowHandler()
    _ledger(handler, [])
    blocked = _run(
        handler.steer_before_tool(agent=None, tool_use={"name": "explain_medication", "input": {}})
    )
    assert isinstance(blocked, Guide)


def test_clinical_boundary_rejects_a_softened_emergency():
    handler = ClinicalBoundaryHandler("session-clinical-boundary")
    set_turn_assessment(
        "session-clinical-boundary",
        Assessment(outcome="emergency", guidance="Call emergency services (112 / 911) now."),
    )
    blocked = _run(
        handler.steer_after_model(
            agent=SimpleNamespace(messages=[]),
            message={"role": "assistant", "content": [{"text": "This is normal. You can wait."}]},
            stop_reason="end_turn",
        )
    )
    assert isinstance(blocked, Guide)
    assert "emergency" in blocked.reason.lower()


def test_specialist_must_call_assess_before_it_answers():
    handler = RelayOutcomeHandler("session-relay")
    _ledger(handler, [])
    blocked = _run(
        handler.steer_after_model(
            agent=SimpleNamespace(messages=[]),
            message={"role": "assistant", "content": [{"text": "I think this can wait."}]},
            stop_reason="end_turn",
        )
    )
    assert isinstance(blocked, Guide)


def test_tool_stop_is_not_steered_as_a_final_answer():
    handler = PlanCommitHandler()
    _ledger(handler, [])
    action = _run(
        handler.steer_after_model(
            agent=SimpleNamespace(messages=[]),
            message={"role": "assistant", "content": [{"text": ""}]},
            stop_reason="tool_use",
        )
    )
    assert isinstance(action, Proceed)
