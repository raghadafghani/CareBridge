"""Outcome of the safety tool for the request that is in flight.

The Strands ledger remembers tool calls for steering. The HTTP handler also
needs the structured outcome after the loop finishes, without parsing model
prose. This map is process-local and cleared at the start of each check-in.

`activate_session` is the id for this request. Tools use it instead of an id
the model typed, so a wrong argument cannot file the outcome under another key.
"""

from __future__ import annotations

import contextvars

from carebridge.plans.store import safe_id
from carebridge.safety.warning_signs import Assessment

_assessments: dict[str, Assessment] = {}
_active: contextvars.ContextVar[str | None] = contextvars.ContextVar("carebridge_session", default=None)


def activate_session(session_id: str) -> None:
    _active.set(safe_id(session_id))


def active_session() -> str | None:
    return _active.get()


def begin_turn(session_id: str) -> None:
    session_id = safe_id(session_id)
    activate_session(session_id)
    _assessments.pop(session_id, None)


def set_turn_assessment(session_id: str, assessment: Assessment) -> None:
    _assessments[safe_id(session_id)] = assessment


def get_turn_assessment(session_id: str) -> Assessment | None:
    return _assessments.get(safe_id(session_id))
