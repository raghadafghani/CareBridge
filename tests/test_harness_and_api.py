"""The harness manifest and the HTTP contract, without a model call."""

from fastapi.testclient import TestClient

from carebridge.api import app
from carebridge.agents.harness import format_harness, harness_manifest
from carebridge.schema import CheckInReply
from carebridge.service import seed_sample_plan


def test_manifest_covers_every_workshop_layer(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CAREBRIDGE_SESSION_BUCKET", raising=False)
    monkeypatch.setenv("CAREBRIDGE_LLM_STEERING", "1")
    manifest = harness_manifest()
    text = format_harness()

    assert "read_discharge_document" in manifest["discharge"]["tools"]
    assert "commit_care_plan" in manifest["discharge"]["tools"]
    assert "RateLimiterHook" in manifest["followup"]["hooks"]
    assert "CheckInWorkflowHandler" in manifest["followup"]["plugins"]
    assert "PlainLanguageGuardrail" in manifest["followup"]["plugins"]
    assert manifest["followup"]["skills"] == [
        "medication-questions",
        "recovery-check-in",
        "safety-escalation",
    ]
    assert manifest["followup"]["session_manager"] == "FileSessionManager"
    assert manifest["followup"]["specialist"]["session_manager"] is None
    assert manifest["discharge"]["session_manager"] is None
    assert "Module 6" in text
    assert "safety_review_specialist" in text


def test_plan_endpoint_returns_the_seeded_ui_plan(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    seed_sample_plan()
    client = TestClient(app)
    response = client.get("/v1/plans/maria-haddad")
    assert response.status_code == 200
    body = response.json()
    assert body["patient"]["diagnosis"] == "Community-acquired pneumonia"
    assert body["meds"][0]["name"] == "Amoxicillin-Clavulanate"
    assert body["flags"][1]["level"] == "confirm"

    missing = client.get("/v1/plans/does-not-exist")
    assert missing.status_code == 404


def test_check_in_route_returns_the_ui_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))

    def fake_check_in(plan_id, session_id, message, **kwargs):
        assert plan_id == "maria-haddad"
        assert message == "My temperature is 38.5 C"
        return CheckInReply(
            text="I'd like to ask a few questions:",
            questions=["When did you measure your temperature?"],
            trace=["Input & context", "Tool selection: load_care_plan"],
        )

    monkeypatch.setattr("carebridge.api.run_check_in", fake_check_in)
    client = TestClient(app)
    response = client.post(
        "/v1/check-ins",
        json={"plan_id": "maria-haddad", "message": "My temperature is 38.5 C", "session_id": "maria"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] is None
    assert body["questions"] == ["When did you measure your temperature?"]
    assert len(body["session_id"]) >= 33


def test_latest_plan_follows_the_most_recent_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    missing = client.get("/v1/plans/latest")
    assert missing.status_code == 404

    seed_sample_plan()
    from carebridge.schema import CarePlan

    uploaded = CarePlan.model_validate(
        {
            "id": "russell-johnson",
            "patient": {
                "name": "Russell Johnson",
                "discharged": "August 5, 2014",
                "hospital": "Community hospital",
                "diagnosis": "Right lower lobe pneumonia",
                "plain": "You were treated for a lung infection and sent home once your breathing had improved.",
            },
            "meds": [
                {
                    "name": "Azithromycin",
                    "dose": "once daily",
                    "purpose": "Antibiotic for pneumonia",
                    "times": ["08:00"],
                    "until": "until the course is finished",
                }
            ],
        }
    )
    from carebridge.plans.store import CareStore

    CareStore().save_plan(uploaded)
    body = client.get("/v1/plans/latest").json()
    assert body["patient"]["name"] == "Russell Johnson"
    assert body["id"] == "russell-johnson"


def test_sample_plan_endpoint_does_not_call_a_model(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    response = TestClient(app).post("/v1/sample-plan")
    assert response.status_code == 200
    assert response.json()["id"] == "maria-haddad"


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
