import pytest

from carebridge.errors import CareBridgeError
from carebridge.google_calendar import connect_url, disconnect, event_body, push_plan, status
from carebridge.schema import Appointment, CarePlan


def _appointment(**updates) -> Appointment:
    payload = {
        "date": "November 3, 2026",
        "day": "Tuesday",
        "title": "Follow-up",
        "who": "Dr. Samir Khoury",
        "time": "10:30",
    }
    payload.update(updates)
    return Appointment.model_validate(payload)


def test_a_timed_visit_becomes_a_calendar_event(monkeypatch):
    monkeypatch.setenv("CAREBRIDGE_TIMEZONE", "Asia/Beirut")
    body = event_body(_appointment())
    assert body["summary"] == "Follow-up"
    assert body["location"] == "Dr. Samir Khoury"
    assert body["start"]["dateTime"] == "2026-11-03T10:30:00"
    assert body["start"]["timeZone"] == "Asia/Beirut"
    assert body["end"]["dateTime"] == "2026-11-03T11:15:00"
    assert body["reminders"]["overrides"][0] == {"method": "popup", "minutes": 1440}
    assert "With Dr. Samir Khoury" in body["description"]


def test_a_visit_without_a_clock_time_is_all_day():
    body = event_body(_appointment(time="Not stated", who="Not stated"))
    assert body["start"] == {"date": "2026-11-03"}
    assert body["end"] == {"date": "2026-11-04"}
    assert body["location"] == ""


def test_status_stays_disconnected_without_a_token(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    assert status() == {"configured": False, "connected": False, "email": None}


def test_connect_url_uses_the_calendar_scope(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    url = connect_url()
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "calendar.events" in url
    assert "client-id" in url
    assert "prompt=consent" in url
    disconnect()
    assert status()["connected"] is False


def test_push_asks_for_a_connection_before_calling_google(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    plan = CarePlan.model_validate(
        {
            "id": "maria-haddad",
            "patient": {
                "name": "Maria Haddad",
                "discharged": "October 28, 2026",
                "hospital": "St. Luke's",
                "diagnosis": "Pneumonia",
                "plain": "You were treated for a lung infection and need to finish the antibiotic.",
            },
            "meds": [
                {
                    "name": "Amoxicillin",
                    "dose": "875 mg",
                    "purpose": "Antibiotic",
                    "times": ["08:00"],
                    "until": "November 4, 2026",
                }
            ],
            "appointments": [_appointment().model_dump()],
        }
    )
    with pytest.raises(CareBridgeError, match="Connect Google Calendar"):
        push_plan(plan)
