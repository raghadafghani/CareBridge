"""Steering handlers. Skills suggest the workflow; these handlers enforce it.

Workshop Module 3:

- A deterministic handler subclasses SteeringHandler, takes a LedgerProvider,
  and implements steer_before_tool. Proceed lets the tool run. Guide cancels
  it and sends the reason back to the model. The workshop's
  RefundWorkflowHandler blocks process_refund until lookup_customer and
  get_order_history have succeeded. PlanCommitHandler and
  CheckInWorkflowHandler are that same gate, on discharge commits and on
  symptom replies.
- steer_after_model runs on the drafted reply. Guide discards the draft and
  retries. The workshop uses this for an LLM tone check. ClinicalBoundaryHandler
  and RelayOutcomeHandler do it with deterministic rules, because a dose
  change or a softened emergency is not a tone preference.
- PlainLanguageGuardrail subclasses LLMSteeringHandler, the workshop's
  ToneGuardrailHandler, for judgment a regex should not own: jargon, blame,
  and false reassurance that is not an exact phrase.

Handlers are plugins. The harness passes them in the same plugins list as
AgentSkills, which is how Module 3 composes the agent.

Each handler allows two Guide retries per invocation, then Proceeds. The API
still replaces unsafe prose with the deterministic guidance, so a capped
retry cannot be the last safety check.
"""

from __future__ import annotations

from typing import Any

from strands.vended_plugins.steering import (
    Guide,
    LedgerProvider,
    LLMSteeringHandler,
    Proceed,
    SteeringHandler,
)
from strands.hooks import BeforeInvocationEvent

from carebridge.safety.messages import GUIDE_PREFIX, is_tool_stop, latest_patient_text, message_text
from carebridge.safety.language import emergency_text_ok, forbidden_reason, review_text_ok
from carebridge.safety.turn_state import get_turn_assessment
from carebridge.safety.warning_signs import looks_like_symptom_report

_MAX_GUIDES = 2


class _BudgetedHandler(SteeringHandler):
    """Shared ledger access and a per-invocation guide budget."""

    def __init__(self) -> None:
        # LedgerProvider records each tool call and its status, which is how
        # the workshop handler knows the prerequisites already ran.
        super().__init__(context_providers=[LedgerProvider()])
        self._ledger_len_at_start = 0
        self._guides = 0

    def init_agent(self, agent: Any) -> None:
        super().init_agent(agent)
        agent.add_hook(self._on_invocation_start, BeforeInvocationEvent)

    def _on_invocation_start(self, event: BeforeInvocationEvent) -> None:
        del event
        self._ledger_len_at_start = len(self._calls())
        self._guides = 0

    def _calls(self) -> list[dict[str, Any]]:
        ledger = self.steering_context.data.get("ledger") or {}
        calls = ledger.get("tool_calls") or []
        return list(calls)

    def _calls_this_invocation(self) -> list[dict[str, Any]]:
        return self._calls()[self._ledger_len_at_start :]

    def _commit_saved(self) -> bool:
        return any(
            call.get("tool_name") == "commit_care_plan" and "SAVED plan_id=" in str(call.get("result") or "")
            for call in self._calls_this_invocation()
        )

    def _succeeded(self, tool_name: str) -> bool:
        return any(
            call.get("tool_name") == tool_name and call.get("status") == "success"
            for call in self._calls_this_invocation()
        )

    def _guide(self, reason: str) -> Any:
        self._guides += 1
        if self._guides > _MAX_GUIDES:
            return Proceed(reason="Guide budget reached for this invocation.")
        return Guide(reason=f"{GUIDE_PREFIX} {reason}")


class PlanCommitHandler(_BudgetedHandler):
    """Block a saved plan until the document has been read, and block a final
    answer until the plan has been saved.

    Workshop analogue: RefundWorkflowHandler, which blocks process_refund
    until lookup_customer and get_order_history have succeeded.
    """

    name = "plan-commit"

    async def steer_before_tool(self, *, agent: Any, tool_use: dict[str, Any], **kwargs: Any) -> Any:
        del agent, kwargs
        if tool_use.get("name") != "commit_care_plan":
            return Proceed(reason="Not a plan commit.")
        if not self._succeeded("read_discharge_document"):
            return self._guide(
                "Call read_discharge_document and use only that text before commit_care_plan."
            )
        return Proceed(reason="Discharge document was read.")

    async def steer_after_model(self, *, agent: Any, message: Any, stop_reason: Any, **kwargs: Any) -> Any:
        del agent, kwargs
        if is_tool_stop(stop_reason):
            return Proceed(reason="Model is still selecting a tool.")
        if self._commit_saved():
            return Proceed(reason="Care plan is saved.")
        if message_text(message):
            return self._guide(
                "Do not answer yet. Call commit_care_plan with the care plan JSON. "
                "If it returns ERROR, fix the JSON and call it again."
            )
        return Proceed(reason="No final text to steer.")


class CheckInWorkflowHandler(_BudgetedHandler):
    """Require the plan to be loaded, and require the safety specialist for symptom reports.

    Workshop analogue: the refund gate. load_care_plan is the customer lookup.
    safety_review_specialist is the step that must not be skipped, in the same
    way process_refund must not run before the order history is checked.
    A new HTTP request builds a new handler, so the ledger starts empty and the
    plan is loaded again even when Module 4 has restored the conversation.
    """

    name = "check-in-workflow"

    _GATED = {"today_recovery_schedule", "explain_medication"}

    async def steer_before_tool(self, *, agent: Any, tool_use: dict[str, Any], **kwargs: Any) -> Any:
        del agent, kwargs
        name = tool_use.get("name")
        if name not in self._GATED:
            return Proceed(reason="Tool is not gated.")
        if not self._succeeded("load_care_plan"):
            return self._guide(f"Call load_care_plan before {name}.")
        return Proceed(reason="Care plan is loaded.")

    async def steer_after_model(self, *, agent: Any, message: Any, stop_reason: Any, **kwargs: Any) -> Any:
        del kwargs
        if is_tool_stop(stop_reason):
            return Proceed(reason="Model is still selecting a tool.")
        if not message_text(message):
            return Proceed(reason="No final text to steer.")
        patient_text = latest_patient_text(agent)
        if looks_like_symptom_report(patient_text):
            if not self._succeeded("safety_review_specialist"):
                return self._guide(
                    "This message reports a symptom, measurement, or missed dose. "
                    "Call safety_review_specialist once with the patient's words unchanged, "
                    "then answer in one or two sentences using its GUIDANCE. Do not call it again."
                )
            return Proceed(reason="Safety specialist already assessed this report.")
        if not self._succeeded("load_care_plan"):
            return self._guide("Call load_care_plan before you answer the patient.")
        return Proceed(reason="Check-in workflow satisfied.")


class ClinicalBoundaryHandler(_BudgetedHandler):
    """Reject a patient-facing draft that contradicts the safety tool.

    Workshop analogue: steer_after_model in the tone guardrail, done with
    Python instead of a second model. Phrase checks live in safety_language.py.
    """

    name = "clinical-boundary"

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    async def steer_after_model(self, *, agent: Any, message: Any, stop_reason: Any, **kwargs: Any) -> Any:
        del agent, kwargs
        if is_tool_stop(stop_reason):
            return Proceed(reason="Model is still selecting a tool.")
        text = message_text(message)
        if not text:
            return Proceed(reason="No final text to steer.")

        assessment = get_turn_assessment(self.session_id)
        if assessment is not None and assessment.outcome == "emergency" and not emergency_text_ok(text):
            return self._guide(
                "The safety tool outcome is emergency. Tell the patient to call emergency "
                "services (112 / 911) or go to the emergency department now. Do not ask a question. "
                f"Use this guidance: {assessment.guidance}"
            )
        if assessment is not None and assessment.outcome == "review" and not review_text_ok(text):
            return self._guide(
                "The safety tool outcome is review. Recommend contacting their clinician today. "
                "Do not say the symptom is normal and do not change any dose. "
                f"Use this guidance: {assessment.guidance}"
            )
        phrase = forbidden_reason(text)
        if phrase:
            return self._guide(
                f"Remove the phrase '{phrase}'. Do not diagnose, reassure the patient that a "
                "symptom is normal, or tell them to change a dose."
            )
        return Proceed(reason="Patient-facing text passed the clinical boundary.")


class RelayOutcomeHandler(_BudgetedHandler):
    """Make the safety specialist return the tool outcome instead of a softer paraphrase.

    The specialist is the Module 6 sub-agent. Its final message is the tool
    result the orchestrator sees, so the OUTCOME line has to survive.
    """

    name = "relay-outcome"

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id

    async def steer_after_model(self, *, agent: Any, message: Any, stop_reason: Any, **kwargs: Any) -> Any:
        del agent, kwargs
        if is_tool_stop(stop_reason):
            return Proceed(reason="Specialist is still selecting a tool.")
        text = message_text(message)
        if not self._succeeded("assess_warning_signs"):
            return self._guide("Call assess_warning_signs once before you answer.")
        assessment = get_turn_assessment(self.session_id)
        expected = assessment.outcome if assessment else ""
        if expected and f"OUTCOME: {expected}" not in text:
            return self._guide(
                f"Your final message must include the line 'OUTCOME: {expected}' "
                "and the GUIDANCE from the tool, unchanged in meaning."
            )
        return Proceed(reason="Specialist relayed the tool outcome.")


class PlainLanguageGuardrail(LLMSteeringHandler):
    """Second-model check for tone, the workshop's ToneGuardrailHandler.

    Deterministic handlers own emergencies and doses. This one owns fuzzy
    rules: jargon, blame, and reassurance that is not an exact banned phrase.
    LLMSteeringHandler runs steer_after_model and returns Proceed or Guide.
    """

    name = "plain-language-guardrail"

    def __init__(self) -> None:
        super().__init__(
            system_prompt="""You are reviewing a post-discharge companion's reply to a patient.
Reject the reply if it:
- Uses unexplained clinical jargon
- Blames the patient
- Promises an outcome the discharge plan does not state
- Implies the companion is a doctor or that it has examined the patient
- Softens an instruction to seek emergency care or to call the care team
- Adds a medication, dose, or diagnosis that the conversation does not already contain

If you reject it, say exactly what to change, in one or two sentences.
A short, plain, specific reply that follows the safety tool is acceptable.
"""
        )
