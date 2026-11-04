"""Reject a care plan that is a paste of the discharge note or leaves sections blank.

The discharge agent fills the plan. This check runs inside commit_care_plan
before anything is saved, and the error text is what the model uses on retry.
It does not invent medications or warning signs. It only requires the model
to sort information the document already contains into the right fields.
"""

from __future__ import annotations

import re
from datetime import datetime

from carebridge.schema import CarePlan

_MAX_PLAIN = 420
_PASTE_MARKERS = (
    "medical record number",
    "history of present illness",
    "discharge summary",
    "dictated by",
    "admission date",
)
_HOSPITAL_PLACEHOLDERS = {"unknown", "n/a", "na", "none", "not specified", "not available"}
_FOLLOW_UP = re.compile(r"follow[\s-]?up|appointment", re.IGNORECASE)
_HOME_CARE = re.compile(
    r"discharge instructions|activity|diet|rest|exercise|fluids|spirometer",
    re.IGNORECASE,
)
_VAGUE_DOSE = re.compile(r"#|puff|inhaler|as directed|not stated|unknown", re.IGNORECASE)
_NOT_A_SYMPTOM = re.compile(r"no warning|not listed|not stated|none recorded|^none$", re.IGNORECASE)


def normalize_plan_payload(payload: dict) -> dict:
    """Fill blank schedule fields and unwrap warning objects the model sometimes sends."""
    hospital = payload.get("patient")
    if isinstance(hospital, dict) and not str(hospital.get("hospital") or "").strip():
        hospital["hospital"] = "Not named in the report"
    appointments = []
    for item in payload.get("appointments") or []:
        if not isinstance(item, dict):
            continue
        appointments.append(
            _with_weekday(
                {
                    "date": _text(item.get("date") or item.get("when"), "Not stated"),
                    "day": _text(item.get("day"), "Not stated"),
                    "title": _text(item.get("title") or item.get("name"), "Follow-up"),
                    "who": _text(item.get("who") or item.get("with") or item.get("clinician"), "Not stated"),
                    "time": _text(item.get("time"), "Not stated"),
                }
            )
        )
    payload["appointments"] = appointments
    payload["warnings"] = [_warning_text(item) for item in payload.get("warnings") or [] if _warning_text(item)]
    payload["checklist"] = [_line(item) for item in payload.get("checklist") or [] if _line(item)]
    return payload


def _text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _warning_text(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("text", "warning", "symptom", "detail", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _line(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("task", "text", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def complete_plan(plan: CarePlan, source: str) -> CarePlan:
    """Fill sections the document already supports, and replace a pasted summary.

    The discharge model sometimes copies the note into patient.plain and leaves
    appointments, checklist, and flags empty. This sorts facts that are already
    in the document into those fields. It does not add a medicine, a dose, or a
    warning sign the document does not contain.
    """
    data = plan.model_dump()
    if _FOLLOW_UP.search(source) and not plan.appointments:
        data["appointments"] = [_follow_up_appointment(source)]
    elif _FOLLOW_UP.search(source) and plan.appointments:
        data["appointments"] = _fill_appointment_blanks(plan, source)
    if _HOME_CARE.search(source) and not plan.checklist:
        data["checklist"] = _tasks_from_source(source)
    data["meds"] = [_grounded_med(med.model_dump(), source) for med in plan.meds]
    data["meds"] = _with_day_labels(data["meds"], data.get("appointments") or [])
    drafted = CarePlan.model_validate(data)
    data["flags"] = _with_required_flags(drafted)
    drafted = CarePlan.model_validate(data)
    if _plain_problems(drafted.patient.plain, source):
        data["patient"]["plain"] = _short_plain(drafted)
    return CarePlan.model_validate(data)


def _follow_up_appointment(source: str) -> dict[str, str]:
    window = _follow_up_window(source)
    when = "Not stated"
    dated = re.search(
        r"\bin\s+\w+(?:\s+\w+){0,4}\s+weeks?\b"
        r"|\bin\s+\d+\s+(?:day|week|month)s?\b"
        r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
        r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        window,
        re.IGNORECASE,
    )
    if dated:
        when = dated.group(0).strip()
        when = when[0].upper() + when[1:]
    clock = re.search(r"\bat\s+(\d{1,2}:\d{2}\s*[AP]M)\b", window, re.IGNORECASE)
    doctor = re.search(r"\bDr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?", window)
    if doctor:
        who = re.sub(r"^Dr\s+", "Dr. ", doctor.group(0))
    elif re.search(r"physician|doctor|\bGP\b|primary care", window, re.IGNORECASE):
        who = "Your regular physician"
    else:
        who = "Not stated"
    return _with_weekday(
        {
            "date": when,
            "day": "Not stated",
            "title": "Follow-up",
            "who": who,
            "time": clock.group(1).upper() if clock else "Not stated",
        }
    )


def _fill_appointment_blanks(plan: CarePlan, source: str) -> list[dict]:
    extracted = _follow_up_appointment(source)
    filled = []
    for item in plan.appointments:
        row = item.model_dump()
        if _blank(row.get("who")) and not _blank(extracted["who"]):
            row["who"] = extracted["who"]
        if _blank(row.get("date")) and not _blank(extracted["date"]):
            row["date"] = extracted["date"]
        if _blank(row.get("time")) and not _blank(extracted["time"]):
            row["time"] = extracted["time"]
        filled.append(_with_weekday(row))
    return filled


def _blank(value: object) -> bool:
    return str(value or "").strip().casefold() in {"", "not stated", "unknown"}


_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%m/%d/%Y", "%m/%d/%y")


def _weekday_name(date: str) -> str | None:
    """Tuesday for a full calendar date. A phrase like 'in two weeks' stays blank."""
    text = date.strip().replace(",", ", ")
    text = re.sub(r",\s+", ", ", text)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%A")
        except ValueError:
            continue
    return None


def _with_weekday(row: dict) -> dict:
    if _blank(row.get("day")):
        named = _weekday_name(str(row.get("date") or ""))
        if named:
            row["day"] = named
    return row


def _follow_up_window(source: str) -> str:
    match = re.search(r"follow[\s-]?up[^.!\n]{0,180}", source, re.IGNORECASE)
    return match.group(0) if match else source


_TASK_PATTERNS = (
    (re.compile(r"regular diet", re.IGNORECASE), "Regular diet"),
    (re.compile(r"no activity restriction", re.IGNORECASE), "No activity restriction"),
    (re.compile(r"incentive spirometer", re.IGNORECASE), "Use the incentive spirometer as shown"),
    (re.compile(r"drink plenty of fluids", re.IGNORECASE), "Drink plenty of fluids"),
    (re.compile(r"rest more often", re.IGNORECASE), "Rest more often than usual"),
    (re.compile(r"finish the (?:full )?antibiotic", re.IGNORECASE), "Finish the antibiotic course"),
)


def _tasks_from_source(source: str) -> list[str]:
    return [label for pattern, label in _TASK_PATTERNS if pattern.search(source)]


def _grounded_med(med: dict, source: str) -> dict:
    dose = str(med.get("dose") or "")
    numbers = re.findall(r"\d+(?:\.\d+)?", dose)
    if numbers and any(number not in source for number in numbers):
        med["dose"] = "Amount not stated in the report"
    return med


_EXPLICIT_AMPM = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\b", re.IGNORECASE)
_EXPLICIT_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_AS_NEEDED = re.compile(r"\bas needed\b|\bprn\b|\bup to\b", re.IGNORECASE)
_PARTS_OF_DAY = (
    (re.compile(r"\b(?:morning|breakfast)\b", re.IGNORECASE), 8 * 60),
    (re.compile(r"\b(?:noon|midday|lunch)\b", re.IGNORECASE), 12 * 60),
    (re.compile(r"\bafternoon\b", re.IGNORECASE), 14 * 60),
    (re.compile(r"\b(?:evening|dinner|supper)\b", re.IGNORECASE), 20 * 60),
    (re.compile(r"\b(?:bedtime|night)\b", re.IGNORECASE), 21 * 60),
)
_FREQUENCIES = (
    (re.compile(r"\b(?:four times|4 times|qid)\b", re.IGNORECASE), (8 * 60, 12 * 60, 16 * 60, 20 * 60)),
    (re.compile(r"\b(?:three times|3 times|tid)\b", re.IGNORECASE), (8 * 60, 14 * 60, 20 * 60)),
    (re.compile(r"\b(?:twice|two times|2 times|bid)\b", re.IGNORECASE), (8 * 60, 20 * 60)),
    (re.compile(r"\b(?:once|one time|daily|every day)\b", re.IGNORECASE), (8 * 60,)),
)


def _with_day_labels(meds: list, appointments: list) -> list:
    return [_with_clock_times(med, appointments) for med in meds]


def _with_clock_times(med: dict, appointments: list) -> dict:
    """Turn morning/evening into hours. Leave a clock time the report stated."""
    times = [str(item) for item in med.get("times") or []]
    text = " ".join(times)
    stated = _explicit_minutes(text)
    if stated:
        med["times"] = [_format_clock(minute) for minute in _unique(stated)]
        return med
    busy = _appointment_minutes(appointments)
    parts = [minute for pattern, minute in _PARTS_OF_DAY if pattern.search(text)]
    if parts:
        med["times"] = [_format_clock(_avoid(minute, busy)) for minute in _unique(parts)]
        return med
    if _AS_NEEDED.search(text):
        return med
    for pattern, slots in _FREQUENCIES:
        if pattern.search(text):
            chosen: list[int] = []
            used = set(busy)
            for minute in slots:
                slot = _avoid(minute, used)
                used.add(slot)
                chosen.append(slot)
            med["times"] = [_format_clock(minute) for minute in chosen]
            return med
    return med


def _explicit_minutes(text: str) -> list[int]:
    ampm = []
    for match in _EXPLICIT_AMPM.finditer(text):
        hours = int(match.group(1))
        minutes = int(match.group(2) or 0)
        if match.group(3).lower() == "p" and hours < 12:
            hours += 12
        if match.group(3).lower() == "a" and hours == 12:
            hours = 0
        ampm.append(hours * 60 + minutes)
    if ampm:
        return ampm
    return [int(match.group(1)) * 60 + int(match.group(2)) for match in _EXPLICIT_CLOCK.finditer(text)]


def _appointment_minutes(appointments: list) -> set[int]:
    busy: set[int] = set()
    for item in appointments:
        when = item.get("time") if isinstance(item, dict) else getattr(item, "time", "")
        busy.update(_explicit_minutes(str(when or "")))
    return busy


def _avoid(minute: int, busy: set[int]) -> int:
    if minute not in busy:
        return minute
    for delta in (-60, 60, -30, 30, -90, 90, -120, 120):
        candidate = minute + delta
        if 6 * 60 <= candidate <= 22 * 60 and candidate not in busy:
            return candidate
    return minute


def _format_clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _unique(values: list[int]) -> list[int]:
    seen: list[int] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def _with_required_flags(plan: CarePlan) -> list[dict]:
    flags = [flag.model_dump() for flag in plan.flags]
    if not _symptom_warnings(plan) and not _mentions(plan, "missing", ("warning", "urgent", "emergency", "return")):
        flags.append(
            {
                "level": "missing",
                "title": "No warning signs listed",
                "detail": "Ask your clinician what should send you back to care.",
            }
        )
    for med in plan.meds:
        if not _dose_is_vague(med.name, med.dose):
            continue
        if _mentions(plan, "confirm", _name_needles(med.name)):
            continue
        flags.append(
            {
                "level": "confirm",
                "title": f"{med.name} dose is not fully stated",
                "detail": "The report names this medicine but does not state the full dose. Confirm it with your clinician.",
            }
        )
    return flags


def _short_plain(plan: CarePlan) -> str:
    diagnosis = plan.patient.diagnosis.strip().rstrip(".")
    text = f"You were in the hospital for {diagnosis}."
    if plan.meds:
        names = ", ".join(med.name for med in plan.meds[:3])
        text += f" At home, continue {names} exactly as this plan lists them."
    if plan.appointments:
        visit = plan.appointments[0]
        when = visit.date.strip()
        if when.casefold() not in {"not stated", "unknown", ""}:
            joiner = " " if when[:1].islower() else " on "
            text += f" See {visit.who}{joiner}{when}."
    if len(text) < 20:
        text = "Your discharge report is now the care plan on this page. Confirm any item marked for your clinician."
    return text[:_MAX_PLAIN]


def plan_problems(plan: CarePlan, source: str) -> list[str]:
    problems: list[str] = []
    problems.extend(_plain_problems(plan.patient.plain, source))
    if plan.patient.hospital.strip().casefold() in _HOSPITAL_PLACEHOLDERS:
        problems.append(
            "patient.hospital is a placeholder. Use the hospital name from the document, "
            "or 'Not named in the report' when the document does not name one."
        )
    if _FOLLOW_UP.search(source) and plan.appointments:
        named = re.search(r"Dr\.?\s+[A-Z][a-z]+", source)
        if named and all(item.who.strip().casefold() in {"not stated", "unknown", ""} for item in plan.appointments):
            problems.append(
                "The document names a physician, but appointments.who is 'Not stated'. "
                "Use that physician's name, or 'Your regular physician' when that is the only follow-up the document gives."
            )
    if _FOLLOW_UP.search(source) and not plan.appointments:
        problems.append(
            "The document mentions a follow-up, but appointments is empty. "
            "Add one appointment. Put the timing from the document in date "
            "(for example 'In 2 to 3 weeks'). Use 'Not stated' for day or time "
            "when the document has no clock time. Put the clinician in who."
        )
    if _HOME_CARE.search(source) and not plan.checklist:
        problems.append(
            "The document has home-care instructions, but checklist is empty. "
            "Add one short line per task the document already states, such as diet, "
            "activity, or finishing a medicine. Do not add tasks the document does not mention."
        )
    if not _symptom_warnings(plan) and not _mentions(plan, "missing", ("warning", "urgent", "emergency", "return")):
        problems.append(
            "warnings is empty and no flag says the warning signs are missing. "
            "Copy warning signs into warnings only when the document lists them. "
            "Otherwise add a flag with level 'missing', title 'No warning signs listed', "
            "and a detail that tells the patient to ask their clinician what should send them back to care."
        )
    for med in plan.meds:
        if not _dose_is_vague(med.name, med.dose):
            continue
        if _mentions(plan, "confirm", _name_needles(med.name)):
            continue
        problems.append(
            f"The dose for {med.name} is incomplete ({med.dose}). "
            "Keep the medicine, and add a flag with level 'confirm' whose title names that medicine "
            "and whose detail says the document does not state the full dose."
        )
    return problems


def _plain_problems(plain: str, source: str) -> list[str]:
    text = " ".join(plain.split())
    problems: list[str] = []
    if len(text) > _MAX_PLAIN or _is_paste(text, source):
        problems.append(
            "patient.plain must be 2 or 3 short sentences in everyday words, under "
            f"{_MAX_PLAIN} characters. Explain why the patient was in hospital and what to do at home. "
            "Do not paste the discharge summary, headings, or the medical record number."
        )
    return problems


def _is_paste(plain: str, source: str) -> bool:
    lowered = plain.casefold()
    if any(marker in lowered for marker in _PASTE_MARKERS):
        return True
    compact_plain = re.sub(r"\s+", " ", plain).casefold()
    compact_source = re.sub(r"\s+", " ", source).casefold()
    window = 80
    if len(compact_plain) < window or len(compact_source) < window:
        return False
    for start in range(0, len(compact_plain) - window, 40):
        if compact_plain[start : start + window] in compact_source:
            return True
    return False


def _dose_is_vague(name: str, dose: str) -> bool:
    if not re.search(r"\d", dose):
        return True
    return bool(_VAGUE_DOSE.search(name) or _VAGUE_DOSE.search(dose))


def _symptom_warnings(plan: CarePlan) -> list[str]:
    return [warning for warning in plan.warnings if warning.strip() and not _NOT_A_SYMPTOM.search(warning)]


def _name_needles(name: str) -> tuple[str, ...]:
    parts = tuple(part for part in re.split(r"\W+", name.casefold()) if len(part) > 3)
    return parts or (name.casefold(),)


def _mentions(plan: CarePlan, level: str, needles: tuple[str, ...]) -> bool:
    for flag in plan.flags:
        if flag.level != level:
            continue
        haystack = f"{flag.title} {flag.detail}".casefold()
        if any(needle.casefold() in haystack for needle in needles):
            return True
    return False
