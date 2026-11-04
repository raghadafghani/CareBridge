"""Deterministic escalation for a patient report.

These rules are the safety policy. The model is not allowed to upgrade or
downgrade them. Patterns cover the warning signs shown in the companion UI,
plus a few fixed emergency signs (chest pain, trouble breathing, coughing
blood, new confusion, bluish lips). A high blood-pressure reading is sent
for clinician review; the word "blood" alone is not treated as an emergency,
because patients also report blood pressure.

Negation is handled so "I do not have chest pain" is not escalated.

This module is plain Python on purpose. Workshop Module 3 puts hard rules in
code (the refund handler), not in the prompt. The steering handler and the
API both trust this function as the source of the outcome.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from carebridge.schema import CarePlan

Outcome = Literal["monitor", "review", "emergency", "pending"]

_EMERGENCY = re.compile(
    r"chest pain|can'?t breathe|cannot breathe|short(?:ness)? of breath|"
    r"cough(?:ing)?(?: up)? blood|bluish|blue lips|unconscious|unresponsive|"
    r"passed out|fainted|fainting",
    re.IGNORECASE,
)
_CONFUSION = re.compile(r"\b(confused|confusion)\b", re.IGNORECASE)
_CONFUSION_ABOUT = re.compile(r"confused about|confusion about", re.IGNORECASE)
_CONCERN = re.compile(
    r"temperature|fever|\bpain\b|\bred\b|swell|dizz|vomit|rash|\bchills?\b",
    re.IGNORECASE,
)
_MISSED = re.compile(r"\b(forgot|missed|skip(?:ped)?)\b", re.IGNORECASE)
_NEGATION = re.compile(
    r"\b(no|not|without|don't|dont|denies|denied|isn't|isnt|hasn't|hasnt)\b",
    re.IGNORECASE,
)
_TEMPERATURE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(?:°|degrees?)?\s*c\b",
    re.IGNORECASE,
)
_THRESHOLD_IN_PLAN = re.compile(
    r"(3\d(?:\.\d+)?|4\d(?:\.\d+)?)\s*°?\s*c",
    re.IGNORECASE,
)
_BLOOD_PRESSURE = re.compile(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b")

_FEVER_QUESTIONS = [
    "When did you measure your temperature?",
    "Have you had chills or sweating?",
    "Are you experiencing any other symptoms?",
]
_GENERAL_QUESTIONS = [
    "When did this start?",
    "Is it getting worse, staying the same, or improving?",
    "Do you have fever, swelling or any other symptoms?",
]


class DialogState(BaseModel):
    """Check-in progress that must survive a new HTTP request.

    Strands session memory stores the conversation (Module 4). This object
    stores the escalation state machine and fast-path turns, which is
    application data: whether we are waiting for answers to a pending question
    and what the patient already reported in this session.
    """

    awaiting_answers: bool = False
    reports: list[str] = Field(default_factory=list)
    history: list[dict[str, str]] = Field(default_factory=list)


class Assessment(BaseModel):
    outcome: Outcome
    questions: list[str] = Field(default_factory=list)
    guidance: str
    summary: str | None = None


def looks_like_symptom_report(text: str) -> bool:
    """True when steering must require the safety specialist before a reply.

    Skills tell the agent to escalate any change in how the patient feels.
    Steering enforces that suggestion only for reports that can change the
    outcome: warning-sign language, a temperature, a missed dose, or a
    blood-pressure reading. Schedule questions stay on the orchestrator.
    """
    return (
        _is_emergency(text)
        or _has_positive(_CONCERN, text)
        or _temperature(text) is not None
        or _high_blood_pressure(text)
        or _MISSED.search(text) is not None
    )


def fever_threshold(plan: CarePlan) -> float:
    for warning in plan.warnings:
        match = _THRESHOLD_IN_PLAN.search(warning)
        if match:
            return float(match.group(1))
    return 38.5


def evaluate_report(report: str, plan: CarePlan, dialog: DialogState) -> tuple[Assessment, DialogState]:
    """Apply the escalation policy and return the next dialog state."""
    updated = dialog.model_copy(deep=True)
    updated.reports = [*dialog.reports, report.strip()]
    clinician = _clinician(plan)

    if _is_emergency(report):
        updated.awaiting_answers = False
        return (
            Assessment(
                outcome="emergency",
                guidance=(
                    "What you describe matches a warning sign in your discharge instructions. "
                    "Please call emergency services (112 / 911) or go to the nearest emergency "
                    "department now. Don't wait for more questions from me."
                ),
            ),
            updated,
        )

    if dialog.awaiting_answers:
        updated.awaiting_answers = False
        return (
            Assessment(
                outcome="review",
                guidance=(
                    f"Thank you. Your discharge instructions ask you to contact your care team if this "
                    f"happens, so I recommend calling {clinician}'s office today. I've prepared a short "
                    f"summary of what you reported that you can share with them."
                ),
                summary=_summary(plan, updated.reports),
            ),
            updated,
        )

    if _concern(report, plan):
        updated.awaiting_answers = True
        fever = bool(re.search(r"temperature|fever", report, re.IGNORECASE)) or _temperature(report) is not None
        questions = _FEVER_QUESTIONS if fever else _GENERAL_QUESTIONS
        if fever and "yesterday" in report.lower():
            intro = (
                "I noticed that your temperature has increased compared with yesterday. "
                "I'd like to ask a few questions:"
            )
        elif fever:
            intro = "Thanks for telling me the temperature. I'd like to ask a few questions:"
        else:
            intro = (
                "Thanks for letting me know. I'd like to ask a few questions so I can "
                "compare this with your discharge instructions:"
            )
        return Assessment(outcome="pending", questions=questions, guidance=intro), updated

    if _MISSED.search(report):
        updated.awaiting_answers = False
        return (
            Assessment(outcome="monitor", guidance=_missed_dose_guidance(report, plan)),
            updated,
        )

    updated.awaiting_answers = False
    return (
        Assessment(
            outcome="monitor",
            guidance=(
                "I didn't find anything in your report that matches a warning sign in your discharge "
                "instructions. That doesn't mean everything is fine — keep monitoring, and tell me if "
                "anything changes."
            ),
        ),
        updated,
    )


def render_assessment(assessment: Assessment) -> str:
    """Text the safety specialist must pass back to the orchestrator unchanged."""
    lines = [f"OUTCOME: {assessment.outcome}", f"GUIDANCE: {assessment.guidance}"]
    if assessment.questions:
        lines.append("QUESTIONS:")
        lines.extend(f"- {question}" for question in assessment.questions)
    else:
        lines.append("QUESTIONS: none")
    if assessment.summary:
        lines.append(f"SUMMARY: {assessment.summary}")
    return "\n".join(lines)


def _is_emergency(text: str) -> bool:
    return _has_positive(_EMERGENCY, text) or _confusion(text)


def _confusion(text: str) -> bool:
    if _CONFUSION_ABOUT.search(text):
        # "Confused about my medication" is a question, not a new neurological symptom.
        without_phrase = _CONFUSION_ABOUT.sub(" ", text)
        return _has_positive(_CONFUSION, without_phrase)
    return _has_positive(_CONFUSION, text)


def _concern(text: str, plan: CarePlan) -> bool:
    if _has_positive(_CONCERN, text):
        return True
    reading = _temperature(text)
    if reading is not None and reading >= fever_threshold(plan):
        return True
    return _high_blood_pressure(text)


def _high_blood_pressure(text: str) -> bool:
    pressure = _BLOOD_PRESSURE.search(text)
    if pressure is None:
        return False
    return int(pressure.group(1)) >= 180 or int(pressure.group(2)) >= 120


def _temperature(text: str) -> float | None:
    match = _TEMPERATURE.search(text)
    if not match:
        return None
    return float(match.group(1))


def _has_positive(pattern: re.Pattern[str], text: str) -> bool:
    return any(not _negated(text, match) for match in pattern.finditer(text))


def _negated(text: str, match: re.Match[str]) -> bool:
    window = text[max(0, match.start() - 24) : match.start()]
    return _NEGATION.search(window) is not None


def _clinician(plan: CarePlan) -> str:
    for appointment in plan.appointments:
        if "primary" in appointment.title.lower():
            return appointment.who
    for appointment in plan.appointments:
        if appointment.who.lower().startswith("dr"):
            return appointment.who
    return "your care team"


def _summary(plan: CarePlan, reports: list[str]) -> str:
    meds = ", ".join(med.name for med in plan.meds)
    lines = [
        f"{plan.patient.name} · discharged {plan.patient.discharged} · {plan.patient.diagnosis}",
        *[f"— {report}" for report in reports],
        f"Current meds: {meds}",
    ]
    return "\n".join(lines)


def _missed_dose_guidance(report: str, plan: CarePlan) -> str:
    named = _mentioned_med(report, plan)
    if named:
        schedule = ", ".join(named.times)
        note = f", {named.note}" if named.note else ""
        subject = f"{named.name} at {schedule}{note}"
    else:
        subject = "; ".join(f"{med.name} ({', '.join(med.times)})" for med in plan.meds)
    return (
        f"Your plan lists {subject}. I can't tell you whether to take a missed dose or double up — "
        "please check with your pharmacist or care team before changing anything. I'll note this in today's log."
    )


def _mentioned_med(report: str, plan: CarePlan):
    lowered = report.lower()
    for med in plan.meds:
        first = med.name.split()[0].lower()
        if med.name.lower() in lowered or (len(first) > 4 and first in lowered):
            return med
    return None
