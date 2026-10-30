"""Care plan contract shared with the companion UI.

Field names match `src/lib/care-data.ts` in the CareBridge frontend
(`patient`, `meds`, `appointments`, `checklist`, `flags`, `warnings`)
so a plan produced here can render on the Care plan page without mapping.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Patient(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    discharged: str = Field(min_length=1)
    hospital: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    plain: str = Field(
        min_length=20,
        description="Plain-language restatement of the discharge summary. No new medical advice.",
    )


class Medication(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    dose: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    times: list[str] = Field(min_length=1)
    until: str = Field(min_length=1)
    note: str | None = None


class Appointment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str
    day: str
    title: str
    who: str
    time: str


class Flag(BaseModel):
    """Something the patient should confirm with a clinician. The agent does not resolve it."""

    model_config = ConfigDict(extra="ignore")

    level: Literal["confirm", "missing"]
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class CarePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    patient: Patient
    meds: list[Medication] = Field(min_length=1)
    appointments: list[Appointment] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CheckInReply(BaseModel):
    """Shape the check-in screen renders: prose, an outcome badge, and follow-up questions."""

    text: str
    outcome: Literal["monitor", "review", "emergency"] | None = None
    questions: list[str] | None = None
    summary: str | None = None
    trace: list[str] | None = None
