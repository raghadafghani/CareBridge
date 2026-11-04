import json
from pathlib import Path

from carebridge.schema import CarePlan
from carebridge.safety.doctor_mail import escalation_message, notify_escalation
from carebridge.safety.warning_signs import DialogState, evaluate_report

_PLAN = CarePlan.model_validate(
    json.loads(
        (Path(__file__).resolve().parents[1] / "app/CareBridge/carebridge/sample_data/maria_haddad_plan.json").read_text()
    )
)


def _assessment(report: str):
    assessment, _dialog = evaluate_report(report, _PLAN, DialogState())
    return assessment


def test_chest_pain_draft_names_the_patient_and_the_report():
    assessment = _assessment("I have chest pain.")
    message = escalation_message(_PLAN, "I have chest pain.", assessment, _settings())
    body = message.get_content()
    assert message["Subject"] == "CareBridge emergency: Maria Haddad"
    assert message["To"] == "doctor@example.com"
    assert "I have chest pain." in body
    assert "emergency" in body
    assert "Community-acquired pneumonia" in body or "pneumonia" in body.lower()


def test_monitor_does_not_email(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAREBRIDGE_DOCTOR_EMAIL", "doctor@example.com")
    monkeypatch.setenv("CAREBRIDGE_SMTP_HOST", "localhost")
    sent = []
    monkeypatch.setattr("carebridge.safety.doctor_mail._smtp_send", lambda settings, message: sent.append(message))
    assessment = _assessment("I slept well.")
    assert assessment.outcome == "monitor"
    assert notify_escalation(_PLAN, "I slept well.", assessment) == "skipped"
    assert sent == []


def test_emergency_sends_when_smtp_is_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAREBRIDGE_DOCTOR_EMAIL", "doctor@example.com")
    monkeypatch.setenv("CAREBRIDGE_SMTP_HOST", "localhost")
    monkeypatch.setenv("CAREBRIDGE_SMTP_FROM", "carebridge@example.com")
    sent = []
    monkeypatch.setattr("carebridge.safety.doctor_mail._smtp_send", lambda settings, message: sent.append(message))
    assessment = _assessment("I have chest pain.")
    assert notify_escalation(_PLAN, "I have chest pain.", assessment) == "sent"
    assert sent[0]["To"] == "doctor@example.com"
    assert "chest pain" in sent[0].get_content()


def test_missing_smtp_saves_the_draft(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAREBRIDGE_DOCTOR_EMAIL", "doctor@example.com")
    monkeypatch.delenv("CAREBRIDGE_SMTP_HOST", raising=False)
    assessment = _assessment("I have chest pain.")
    assert notify_escalation(_PLAN, "I have chest pain.", assessment) == "saved"
    drafts = list((tmp_path / "doctor_mail").glob("*.txt"))
    assert len(drafts) == 1
    assert "I have chest pain." in drafts[0].read_text()


def _settings():
    from carebridge.config import Settings

    return Settings(
        region="us-east-1",
        model_id=None,
        checkin_model_id=None,
        data_dir=Path("."),
        sessions_dir=Path("."),
        session_bucket=None,
        document_bucket=None,
        llm_steering=False,
        max_tool_calls=3,
        doctor_email="doctor@example.com",
        smtp_host="localhost",
        smtp_port=1025,
        smtp_user=None,
        smtp_password=None,
        smtp_from="carebridge@example.com",
        smtp_tls=False,
    )
