import json
from pathlib import Path

from carebridge.schema import CarePlan
from carebridge.safety.warning_signs import DialogState, evaluate_report

_PLAN = CarePlan.model_validate(
    json.loads(
        (Path(__file__).resolve().parents[1] / "app/CareBridge/carebridge/sample_data/maria_haddad_plan.json").read_text()
    )
)


def _eval(report: str, dialog: DialogState | None = None):
    return evaluate_report(report, _PLAN, dialog or DialogState())


def test_fever_asks_questions_then_review():
    assessment, dialog = _eval("My temperature is 38.5°C. It was 37°C yesterday. Is this normal?")
    assert assessment.outcome == "pending"
    assert dialog.awaiting_answers is True
    assert assessment.questions[0] == "When did you measure your temperature?"

    follow_up, dialog = evaluate_report("This morning, and I had chills.", _PLAN, dialog)
    assert follow_up.outcome == "review"
    assert dialog.awaiting_answers is False
    assert "Dr. Samir Khoury" in follow_up.guidance
    assert "Maria Haddad" in (follow_up.summary or "")


def test_emergency_beats_a_pending_question():
    _, dialog = _eval("I have more pain than yesterday.")
    assert dialog.awaiting_answers is True
    assessment, dialog = evaluate_report("Now I have chest pain.", _PLAN, dialog)
    assert assessment.outcome == "emergency"
    assert "112" in assessment.guidance
    assert assessment.questions == []
    assert dialog.awaiting_answers is False


def test_negated_chest_pain_is_not_an_emergency():
    assessment, _ = _eval("I don't have chest pain. I slept well.")
    assert assessment.outcome == "monitor"


def test_missed_dose_does_not_authorize_a_double():
    assessment, _ = _eval("I forgot to take my amoxicillin.")
    assert assessment.outcome == "monitor"
    assert "Amoxicillin-Clavulanate" in assessment.guidance
    assert "double up" in assessment.guidance


def test_blood_pressure_is_not_treated_as_bleeding():
    normal, _ = _eval("My blood pressure is 122/78.")
    assert normal.outcome == "monitor"
    high, _ = _eval("My blood pressure is 190/110.")
    assert high.outcome == "pending"


def test_confusion_about_a_medicine_is_not_a_neurological_emergency():
    assessment, _ = _eval("I am confused about my medication times.")
    assert assessment.outcome == "monitor"


def test_bluish_lips_are_an_emergency():
    assessment, _ = _eval("My lips look bluish and I feel confused.")
    assert assessment.outcome == "emergency"


def test_temperature_below_the_plan_threshold_is_monitor():
    assessment, _ = _eval("I checked and it was 37.2 c.")
    assert assessment.outcome == "monitor"
