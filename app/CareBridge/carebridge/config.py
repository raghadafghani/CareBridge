"""Runtime settings. Read on each call so tests can change the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def project_root() -> Path:
    """Repository root: the directory that contains agentcore/agentcore.json."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "agentcore" / "agentcore.json").is_file():
            return parent
    return Path.cwd()


def _load_project_env() -> None:
    """Fill unset variables from the project .env. Existing environment wins."""
    path = project_root() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and not os.getenv(key, "").strip():
            os.environ[key] = value


_load_project_env()


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    region: str
    model_id: str | None
    checkin_model_id: str | None
    data_dir: Path
    sessions_dir: Path
    session_bucket: str | None
    document_bucket: str | None
    llm_steering: bool
    max_tool_calls: int
    doctor_email: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    smtp_from: str | None
    smtp_tls: bool
    cors_origins: tuple[str, ...] = ("*",)

    @property
    def package_dir(self) -> Path:
        return Path(__file__).resolve().parent


def get_settings() -> Settings:
    root = project_root()
    data_dir = Path(os.getenv("CAREBRIDGE_DATA_DIR", root / ".carebridge"))
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    model_id = os.getenv("CAREBRIDGE_MODEL_ID", "").strip() or None
    checkin_model_id = os.getenv("CAREBRIDGE_CHECKIN_MODEL_ID", "").strip() or None
    bucket = os.getenv("CAREBRIDGE_SESSION_BUCKET", "").strip() or None
    documents = os.getenv("CAREBRIDGE_DOCUMENT_BUCKET", "").strip() or None
    try:
        max_calls = int(os.getenv("CAREBRIDGE_MAX_TOOL_CALLS", "3"))
    except ValueError:
        max_calls = 3
    return Settings(
        region=os.getenv("AWS_REGION", "us-east-1"),
        model_id=model_id,
        checkin_model_id=checkin_model_id,
        data_dir=data_dir,
        sessions_dir=data_dir / "sessions",
        session_bucket=bucket,
        document_bucket=documents,
        llm_steering=_flag("CAREBRIDGE_LLM_STEERING", True),
        max_tool_calls=max(1, max_calls),
        doctor_email=os.getenv("CAREBRIDGE_DOCTOR_EMAIL", "").strip() or None,
        smtp_host=os.getenv("CAREBRIDGE_SMTP_HOST", "").strip() or None,
        smtp_port=_port("CAREBRIDGE_SMTP_PORT", 587),
        smtp_user=os.getenv("CAREBRIDGE_SMTP_USER", "").strip() or None,
        smtp_password=os.getenv("CAREBRIDGE_SMTP_PASSWORD", "").strip() or None,
        smtp_from=os.getenv("CAREBRIDGE_SMTP_FROM", "").strip() or None,
        smtp_tls=_flag("CAREBRIDGE_SMTP_TLS", True),
        cors_origins=_origins("CAREBRIDGE_CORS_ORIGINS"),
    )


def _origins(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ("*",)
    parsed = tuple(part.strip() for part in raw.split(",") if part.strip())
    return parsed or ("*",)


def _port(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
