"""Outcome of the safety tool and active document for the request in flight.

The Strands ledger remembers tool calls for steering. The HTTP handler also
needs the structured outcome after the loop finishes, without parsing model
prose. Assessments are scoped to a ContextVar per request turn (with a
bounded process-local fallback for direct unit-test calls) and cleared at the
start of each check-in.

`activate_session` is the id for this request. Tools use it instead of an id
the model typed, so a wrong argument cannot file the outcome under another key.
`activate_document` binds the uploaded discharge `document_id` to the current
extraction turn so `commit_care_plan` validates against the exact document
that was uploaded, even under concurrent requests.
"""

from __future__ import annotations

import contextvars

from carebridge.plans.store import safe_id
from carebridge.safety.warning_signs import Assessment

_MAX_FALLBACK = 256
_assessments: dict[str, Assessment] = {}
_turn_map: contextvars.ContextVar[dict[str, Assessment] | None] = contextvars.ContextVar(
    "carebridge_turn_assessments", default=None
)
_active: contextvars.ContextVar[str | None] = contextvars.ContextVar("carebridge_session", default=None)
_active_document: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "carebridge_document", default=None
)


def activate_session(session_id: str) -> None:
    _active.set(safe_id(session_id))


def active_session() -> str | None:
    return _active.get()


def activate_document(document_id: str) -> None:
    _active_document.set(safe_id(document_id))


def active_document() -> str | None:
    return _active_document.get()


def begin_turn(session_id: str) -> None:
    cleaned = safe_id(session_id)
    activate_session(cleaned)
    _turn_map.set({})
    _assessments.pop(cleaned, None)


def set_turn_assessment(session_id: str, assessment: Assessment) -> None:
    cleaned = safe_id(session_id)
    scoped = _turn_map.get()
    if scoped is not None:
        scoped[cleaned] = assessment
    if len(_assessments) >= _MAX_FALLBACK and cleaned not in _assessments:
        oldest = next(iter(_assessments))
        _assessments.pop(oldest, None)
    _assessments[cleaned] = assessment


def get_turn_assessment(session_id: str) -> Assessment | None:
    cleaned = safe_id(session_id)
    scoped = _turn_map.get()
    if scoped is not None and cleaned in scoped:
        return scoped[cleaned]
    return _assessments.get(cleaned)
