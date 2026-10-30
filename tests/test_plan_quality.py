from carebridge.plans.quality import complete_plan, normalize_plan_payload, plan_problems
from carebridge.schema import CarePlan

SOURCE = (
    "Discharge Instructions: regular diet, no activity restriction. "
    "Zithromycin daily until gone, inhalers #of puffs. "
    "Follow up in two to three weeks with the regular physician."
)


def _plan(**updates) -> CarePlan:
    payload = {
        "id": "russell-johnson",
        "patient": {
            "name": "Russell Johnson",
            "discharged": "August 5, 2014",
            "hospital": "Not named in the report",
            "diagnosis": "Pneumonia and a COPD flare",
            "plain": (
                "You were treated for a lung infection and a flare of your lung disease. "
                "Finish the antibiotic, keep using your inhalers, and see your doctor in two to three weeks."
            ),
        },
        "meds": [
            {
                "name": "Azithromycin",
                "dose": "once daily, amount not stated",
                "purpose": "Antibiotic",
                "times": ["Once a day"],
                "until": "until the course is finished",
            }
        ],
        "appointments": [
            {
                "date": "In 2 to 3 weeks",
                "day": "Not stated",
                "title": "Follow-up with your physician",
                "who": "Your regular physician",
                "time": "Not stated",
            }
        ],
        "checklist": ["Regular diet", "No activity restriction"],
        "flags": [
            {
                "level": "confirm",
                "title": "Azithromycin dose not stated",
                "detail": "The report says daily until gone, but not how many milligrams.",
            },
            {
                "level": "missing",
                "title": "No warning signs listed",
                "detail": "Ask your clinician what should send you back to care.",
            },
        ],
        "warnings": [],
    }
    payload.update(updates)
    return CarePlan.model_validate(payload)


def test_a_sorted_plan_is_accepted():
    assert plan_problems(_plan(), SOURCE) == []


def test_a_pasted_discharge_note_is_rejected():
    pasted = _plan()
    pasted.patient.plain = (
        "Discharge Summary Patient Name: Russell Johnson Medical Record Number: 123456789 "
        "History of Present Illness 72 year old thin white male presented to emergency."
    )
    problems = plan_problems(pasted, SOURCE)
    assert any("patient.plain" in problem for problem in problems)


def test_missing_appointment_fields_are_filled_before_validation():
    payload = normalize_plan_payload(
        {
            "appointments": [{"title": "Follow up with regular physician"}],
            "warnings": [{"symptom": "fever"}],
            "checklist": [{"task": "Regular diet"}],
        }
    )
    assert payload["appointments"][0]["date"] == "Not stated"
    assert payload["warnings"] == ["fever"]
    assert payload["checklist"] == ["Regular diet"]


RUSSELL = """
Discharge Summary
Patient Name: Russell Johnson
Medical Record Number: 123456789
Discharge Date: 08/05/14
Primary Care Physician: Dr Dianna Miller
Final Diagnosis: RLL pneumonia, COPD exacerbation, mild CHF, osteoarthritis
Discharge Medications Zithromycin daily until gone, inhalers #of puffs,
Discharge Instructions: no activity restriction, regular diet, follow up in two to three weeks with regular physician.
"""


def test_a_pasted_note_is_sorted_into_the_plan_sections():
    pasted = _plan(
        appointments=[],
        checklist=[],
        flags=[],
        warnings=[],
        meds=[
            {
                "name": "Zithromycin",
                "dose": "250mg",
                "purpose": "To treat pneumonia",
                "times": ["daily"],
                "until": "gone",
            },
            {
                "name": "inhalers",
                "dose": "#of puffs",
                "purpose": "To manage COPD",
                "times": ["as needed"],
                "until": "not stated",
            },
        ],
    )
    pasted.patient.plain = (
        "Discharge Summary Patient Name: Russell Johnson Medical Record Number: 123456789 "
        "History of Present Illness 72 year old thin white male presented to emergency."
    )
    completed = complete_plan(pasted, RUSSELL)
    assert plan_problems(completed, RUSSELL) == []
    assert "medical record" not in completed.patient.plain.casefold()
    assert len(completed.patient.plain) <= 420
    assert completed.appointments[0].who == "Your regular physician"
    assert "week" in completed.appointments[0].date.casefold()
    assert "Regular diet" in completed.checklist
    assert completed.meds[0].dose == "Amount not stated in the report"
    assert any(flag.level == "missing" for flag in completed.flags)
    assert any(flag.level == "confirm" for flag in completed.flags)


def test_missing_follow_up_and_tasks_are_rejected():
    plan = _plan()
    plan.appointments = []
    plan.checklist = []
    problems = plan_problems(plan, SOURCE)
    assert any("appointments" in problem for problem in problems)
    assert any("checklist" in problem for problem in problems)
