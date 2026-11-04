"""Google Calendar sign-in and appointment reminders.

The browser never sees the client secret. Connect redirects to Google, the
callback stores a refresh token under the local data directory, and pushing a
care plan creates or updates one event per visit. Phone reminders are the
calendar app's popup alerts, a day before and an hour before.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from carebridge.config import get_settings
from carebridge.errors import CareBridgeError
from carebridge.schema import Appointment, CarePlan

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_USERINFO = "https://www.googleapis.com/oauth2/v2/userinfo"
_SCOPE = "openid email https://www.googleapis.com/auth/calendar.events"
_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%m/%d/%Y", "%Y-%m-%d")
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\s*([ap]m)?\b", re.IGNORECASE)


class CalendarNotConnected(CareBridgeError):
    """The Google account has not been connected on this machine."""


def status() -> dict:
    saved = _load()
    return {
        "configured": _configured(),
        "connected": bool(saved.get("refresh_token")),
        "email": saved.get("email") or None,
    }


def connect_url() -> str:
    if not _configured():
        raise CareBridgeError(
            "Google Calendar is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )
    state = secrets.token_urlsafe(24)
    saved = _load()
    saved["oauth_state"] = state
    _save(saved)
    query = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "scope": _SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return f"{_AUTH}?{query}"


def finish_oauth(code: str, state: str) -> None:
    saved = _load()
    if not state or state != saved.get("oauth_state"):
        raise CareBridgeError("The Google sign-in session expired. Connect again.")
    token = _form(
        {
            "code": code,
            "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        }
    )
    refresh = token.get("refresh_token") or saved.get("refresh_token")
    if not refresh:
        raise CareBridgeError(
            "Google did not return a refresh token. Remove CareBridge from your Google account and connect again."
        )
    access = str(token.get("access_token") or "")
    saved["refresh_token"] = refresh
    saved["access_token"] = access
    saved["expires_at"] = time.time() + int(token.get("expires_in") or 3600) - 60
    saved.pop("oauth_state", None)
    saved["email"] = _email(access)
    _save(saved)


def disconnect() -> None:
    path = _path()
    if path.is_file():
        path.unlink()


def push_plan(plan: CarePlan) -> dict[str, int]:
    if not _configured():
        raise CareBridgeError(
            "Google Calendar is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )
    saved = _load()
    if not saved.get("refresh_token"):
        raise CalendarNotConnected("Connect Google Calendar before adding these visits.")
    token = _access_token(saved)
    events = dict(saved.get("events") or {})
    added = 0
    updated = 0
    for appointment in plan.appointments:
        body = event_body(appointment)
        key = _event_key(plan.id, appointment)
        existing = events.get(key)
        if existing:
            try:
                _api("PATCH", f"{_EVENTS}/{urllib.parse.quote(existing)}", body, token)
                updated += 1
                continue
            except CareBridgeError as exc:
                if getattr(exc, "status", None) != 404:
                    raise
        created = _api("POST", _EVENTS, body, token)
        events[key] = str(created.get("id") or "")
        added += 1
    saved = _load()
    saved["events"] = events
    _save(saved)
    return {"added": added, "updated": updated}


def event_body(appointment: Appointment) -> dict:
    """One Calendar event. A visit with no clock time is an all-day event."""
    day = _parse_date(appointment.date)
    if day is None:
        raise CareBridgeError(f"Could not read the appointment date “{appointment.date}”.")
    who = appointment.who.strip()
    location = "" if who.casefold() in {"", "not stated", "unknown"} else who
    summary = appointment.title.strip() or "Follow-up"
    description = "CareBridge follow-up from your discharge plan."
    if location:
        description += f" With {location}."
    reminders = {
        "useDefault": False,
        "overrides": [
            {"method": "popup", "minutes": 24 * 60},
            {"method": "popup", "minutes": 60},
        ],
    }
    clock = _parse_clock(appointment.time)
    if clock is None:
        return {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {"date": day.date().isoformat()},
            "end": {"date": (day + timedelta(days=1)).date().isoformat()},
            "reminders": reminders,
        }
    start = day.replace(hour=clock[0], minute=clock[1])
    end = start + timedelta(minutes=45)
    zone = os.getenv("CAREBRIDGE_TIMEZONE", "Asia/Beirut").strip() or "Asia/Beirut"
    stamp = "%Y-%m-%dT%H:%M:%S"
    return {
        "summary": summary,
        "location": location,
        "description": description,
        "start": {"dateTime": start.strftime(stamp), "timeZone": zone},
        "end": {"dateTime": end.strftime(stamp), "timeZone": zone},
        "reminders": reminders,
    }


def redirect_uri() -> str:
    return os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:8787/v1/calendar/callback").strip()


def app_return() -> str:
    return os.getenv("CAREBRIDGE_APP_URL", "http://127.0.0.1:8080/plan").strip()


def _configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID", "").strip() and os.getenv("GOOGLE_CLIENT_SECRET", "").strip())


def _path() -> Path:
    directory = get_settings().data_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "google_calendar.json"


def _load() -> dict:
    path = _path()
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save(data: dict) -> None:
    path = _path()
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)


def _parse_date(text: str) -> datetime | None:
    cleaned = " ".join(text.strip().split())
    candidates = [cleaned, cleaned.replace(",", "")]
    formats = list(_DATE_FORMATS) + [fmt.replace(", ", " ") for fmt in _DATE_FORMATS]
    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(cleaned.replace(",", ""), fmt)
        except ValueError:
            continue
        return parsed.replace(year=datetime.now().year)
    return None


def _parse_clock(text: str) -> tuple[int, int] | None:
    if text.strip().casefold() in {"", "not stated", "unknown"}:
        return None
    match = _CLOCK.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    suffix = (match.group(3) or "").lower()
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _event_key(plan_id: str, appointment: Appointment) -> str:
    return "|".join([plan_id, appointment.date.strip(), appointment.time.strip(), appointment.title.strip()])


def _access_token(saved: dict) -> str:
    if saved.get("access_token") and float(saved.get("expires_at") or 0) > time.time():
        return str(saved["access_token"])
    token = _form(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
            "refresh_token": saved["refresh_token"],
            "grant_type": "refresh_token",
        }
    )
    saved["access_token"] = token["access_token"]
    saved["expires_at"] = time.time() + int(token.get("expires_in") or 3600) - 60
    _save(saved)
    return str(saved["access_token"])


def _email(token: str) -> str | None:
    try:
        profile = _api("GET", _USERINFO, None, token)
    except CareBridgeError:
        return None
    email = profile.get("email")
    return str(email) if email else None


def _form(fields: dict) -> dict:
    payload = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(_TOKEN, data=payload, method="POST")
    return _read(request)


def _api(method: str, url: str, body: dict | None, token: str) -> dict:
    payload = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    return _read(request)


def _ssl_context() -> ssl.SSLContext | None:
    """Use certifi when the local Python install has no CA bundle."""
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def _read(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=20, context=_ssl_context()) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:240]
        failure = CareBridgeError(f"Google Calendar returned {exc.code}. {detail}")
        failure.status = exc.code  # type: ignore[attr-defined]
        raise failure from exc
    except urllib.error.URLError as exc:
        raise CareBridgeError("Could not reach Google Calendar.") from exc
    if not raw:
        return {}
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {}
