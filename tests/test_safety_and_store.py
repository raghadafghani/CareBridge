import json
from pathlib import Path

from carebridge.documents import extract_upload, strip_sample_banner
from carebridge.safety.messages import patient_visible_text
from carebridge.safety.language import enforce_patient_response
from carebridge.schema import CarePlan
from carebridge.plans.store import CareStore, safe_id
from carebridge.safety.warning_signs import Assessment


def test_sample_plan_matches_the_companion_ui(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    sample = Path(__file__).resolve().parents[1] / "app/CareBridge/carebridge/sample_data/maria_haddad_plan.json"
    plan = CarePlan.model_validate(json.loads(sample.read_text()))
    stored = CareStore().save_plan(plan)
    loaded = CareStore().get_plan("maria-haddad")
    assert stored.id == "maria-haddad"
    assert loaded.patient.name == "Maria Haddad"
    assert [flag.title for flag in loaded.flags] == [
        "Metoprolol duration not stated",
        "Conflicting antibiotic dose",
        "No guidance on returning to work",
    ]
    assert len(loaded.meds) == 4
    assert len(loaded.warnings) == 4


def test_ids_cannot_escape_the_data_directory():
    assert safe_id("../maria") == "maria"
    try:
        safe_id("..")
    except Exception as exc:
        assert "not safe" in str(exc)
    else:
        raise AssertionError("path-only id should be rejected")


def test_a_digital_pdf_is_read_without_textract(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("a text PDF should not call Amazon Textract")

    monkeypatch.setattr("carebridge.documents._textract_bytes", fail_if_called)
    pdf = Path(__file__).resolve().parent / "fixtures" / "one-page-discharge.pdf"
    text = extract_upload(pdf.name, pdf.read_bytes())
    assert "Amoxicillin 875 mg" in text
    assert "Russell Johnson" in text


def test_sample_banner_is_removed_before_the_agent_sees_the_document():
    path = Path(__file__).resolve().parents[1] / "app/CareBridge/carebridge/sample_data/maria_haddad_discharge.txt"
    text = extract_upload(path.name, path.read_bytes())
    assert "NOT A REAL MEDICAL RECORD" not in text
    assert "875 mg" in text
    assert "500 mg" in text
    assert strip_sample_banner("hello") == "hello"


def test_model_reasoning_is_not_shown_to_the_patient():
    text = patient_visible_text("<thinking> The specialist said monitor. </thinking>\n\nCheck with your pharmacist.")
    assert "thinking" not in text.lower()
    assert text == "Check with your pharmacist."


def test_unsafe_model_text_is_replaced_by_the_tool_guidance():
    emergency = Assessment(
        outcome="emergency",
        guidance="Please call emergency services (112 / 911) now.",
    )
    assert "911" in enforce_patient_response("This is normal, wait and see.", emergency)
    assert "wait and see" not in enforce_patient_response("This is normal, wait and see.", emergency)

    safe = "Please call emergency services (112 / 911) or go to the emergency department now."
    assert enforce_patient_response(safe, emergency) == safe

    assert "dose" in enforce_patient_response("You should double the dose.", None).lower()
