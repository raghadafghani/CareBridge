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


def test_commit_care_plan_uses_the_active_document_instead_of_newest_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    from carebridge.agents.tools import commit_care_plan, read_discharge_document

    store = CareStore()
    first_id = store.save_document(
        "Patient: Maria Haddad. Discharged Oct 28, 2026 from St. Luke's. "
        "Diagnosis: Pneumonia. Amoxicillin 875 mg morning and evening until Nov 4. "
        "Warning signs: chest pain.",
        "maria.txt",
    )
    store.save_document(
        "Patient: Unrelated Patient. Discharged Oct 29, 2026. Diagnosis: Sprain. Ibuprofen 200 mg.",
        "other.txt",
    )

    read_discharge_document(first_id)
    sample = Path(__file__).resolve().parents[1] / "app/CareBridge/carebridge/sample_data/maria_haddad_plan.json"
    result = commit_care_plan(sample.read_text())
    assert "SAVED plan_id=maria-haddad" in result
    saved = store.get_plan("maria-haddad")
    assert saved.meds[0].dose == "875 mg tablet"


def test_fast_path_check_in_records_session_history_for_later_turns(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    from carebridge.agents.session import normalize_session_id
    from carebridge.agents.tools import load_care_plan
    from carebridge.service import run_check_in, seed_sample_plan
    from carebridge.safety.turn_state import begin_turn

    seed_sample_plan()
    normalized = normalize_session_id("maria-session")
    reply = run_check_in("maria-haddad", "maria-session", "What should I do today?")
    assert "Amoxicillin-Clavulanate" in reply.text

    dialog = CareStore().get_dialog(normalized)
    assert len(dialog.history) == 1
    assert dialog.history[0]["user"] == "What should I do today?"

    begin_turn(normalized)
    loaded = load_care_plan("maria-haddad")
    assert "Earlier in this check-in session:" in loaded
    assert "What should I do today?" in loaded


def test_care_store_hydrates_from_s3_on_local_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path / "node1"))
    monkeypatch.setenv("CAREBRIDGE_SESSION_BUCKET", "carebridge-test-bucket")
    objects: dict[str, bytes] = {}

    class FakeBody:
        def __init__(self, data: bytes) -> None:
            self._data = data

        def read(self) -> bytes:
            return self._data

    class FakeS3:
        def put_object(self, *, Bucket, Key, Body, ContentType):
            assert Bucket == "carebridge-test-bucket"
            objects[Key] = Body

        def get_object(self, *, Bucket, Key):
            assert Bucket == "carebridge-test-bucket"
            if Key not in objects:
                raise KeyError(Key)
            return {"Body": FakeBody(objects[Key])}

    import boto3

    monkeypatch.setattr(boto3, "client", lambda service, **kwargs: FakeS3())
    sample = Path(__file__).resolve().parents[1] / "app/CareBridge/carebridge/sample_data/maria_haddad_plan.json"
    plan = CarePlan.model_validate(json.loads(sample.read_text()))
    CareStore().save_plan(plan)

    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path / "node2"))
    second_node = CareStore()
    assert second_node.latest_plan_id() == "maria-haddad"
    restored = second_node.get_plan("maria-haddad")
    assert restored.patient.name == "Maria Haddad"

