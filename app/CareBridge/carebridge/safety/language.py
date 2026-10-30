"""Checks on the words the patient actually sees.

The model writes the conversation. These checks reject replies that diagnose,
change a dose, call a warning sign normal, or soften an emergency. When a
reply fails, the caller substitutes the guidance produced by `warning_signs`,
which is fixed policy text rather than another model draft.

Workshop Module 3 uses an LLM tone guardrail for fuzzy judgment and a
deterministic handler for rules that must always hold. This module is the
deterministic half, applied again at the API boundary because a capped
steering retry must not be the last line of defense.
"""

from __future__ import annotations

import re

from carebridge.safety.warning_signs import Assessment

_FORBIDDEN = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"this is normal",
        r"that(?:'s| is) normal",
        r"you(?:'re| are) fine",
        r"nothing to worry",
        r"no need to (?:see|call|contact)",
        r"double (?:the |your )?dose",
        r"take (?:an )?extra",
        r"increase (?:your |the )?dose",
        r"stop taking",
        r"you can discontinue",
        r"\bi diagnose\b",
        r"you(?:'re| are) diagnosed",
        r"my diagnosis is",
    )
]

_EMERGENCY_ACTION = re.compile(r"emergency services|\b112\b|\b911\b", re.IGNORECASE)
_CARE_TEAM = re.compile(r"care team|pharmacist|doctor|\bdr\.|clinic|office", re.IGNORECASE)

DOSE_FALLBACK = (
    "I can't advise you to change a dose, skip a dose, or repeat a medication. "
    "Please check with your pharmacist or care team before taking anything different "
    "from your discharge plan."
)


def forbidden_reason(text: str) -> str | None:
    for pattern in _FORBIDDEN:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def emergency_text_ok(text: str) -> bool:
    """Emergency replies must direct the patient to emergency services and must not interview them."""
    return _EMERGENCY_ACTION.search(text) is not None and "?" not in text and forbidden_reason(text) is None


def review_text_ok(text: str) -> bool:
    return forbidden_reason(text) is None and _CARE_TEAM.search(text) is not None


def enforce_patient_response(text: str, assessment: Assessment | None) -> str:
    """Return text that is safe to show, preferring the model's words when they pass."""
    cleaned = text.strip()
    if assessment is None:
        return DOSE_FALLBACK if forbidden_reason(cleaned) else cleaned

    if assessment.outcome == "emergency":
        return cleaned if emergency_text_ok(cleaned) else assessment.guidance
    if assessment.outcome == "review":
        return cleaned if review_text_ok(cleaned) else assessment.guidance
    if assessment.outcome == "pending":
        return assessment.guidance if forbidden_reason(cleaned) else cleaned
    if forbidden_reason(cleaned):
        return assessment.guidance
    return cleaned
