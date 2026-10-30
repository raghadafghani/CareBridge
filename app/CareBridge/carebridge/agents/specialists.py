"""Safety review exposed to the orchestrator as one tool.

Workshop Module 6, agents-as-tools. The check-in agent does not contain the
warning-sign policy. It calls safety_review_specialist the way it calls any
other @tool, and the docstring is what tells it when to delegate.

The assessment itself is deterministic Python. A nested model loop used to
sit inside this tool, then the orchestrator paraphrased the same result.
That second loop is what made every check-in wait through several Bedrock
calls. The tool now runs assess_warning_signs and returns its outcome.
The orchestrator still decides when to delegate, and it is the only model
the patient waits on.
"""

from __future__ import annotations

from strands import tool

from carebridge.agents.tools import assess_warning_signs
from carebridge.safety.turn_state import active_session


@tool
def safety_review_specialist(plan_id: str, session_id: str, patient_report: str) -> str:
    """Assess a symptom, measurement, missed dose, or change in how the patient feels.

    Use this once for fever, pain, dizziness, a wound change, trouble breathing,
    or a forgotten dose. Do not use it for questions about the medication
    schedule or appointment times. Pass the patient's words unchanged.
    After it returns, answer the patient in one or two sentences and stop.

    Args:
        plan_id: Active care plan id.
        session_id: Active session id.
        patient_report: The patient's own words, unchanged.
    """
    # The request session wins over an id the model typed into the tool call.
    session_id = active_session() or session_id
    return assess_warning_signs(plan_id, session_id, patient_report)
