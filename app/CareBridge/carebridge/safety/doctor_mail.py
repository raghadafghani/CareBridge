"""Email the configured doctor when safety rules escalate.

Emergency and review outcomes send a fixed draft. Pending and monitor do not.
A missing doctor address or SMTP failure does not change the patient's reply.
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage

from carebridge.config import Settings, get_settings
from carebridge.schema import CarePlan
from carebridge.safety.warning_signs import Assessment

logger = logging.getLogger(__name__)

_ESCALATIONS = {"emergency", "review"}


def notify_escalation(plan: CarePlan, report: str, assessment: Assessment) -> str:
    """Send or store the doctor draft. Returns sent, saved, unconfigured, skipped, or failed."""
    if assessment.outcome not in _ESCALATIONS:
        return "skipped"
    settings = get_settings()
    if not settings.doctor_email:
        logger.info("Doctor email skipped: CAREBRIDGE_DOCTOR_EMAIL is empty.")
        return "unconfigured"
    message = escalation_message(plan, report, assessment, settings)
    if not settings.smtp_host:
        _save_local(settings, message)
        logger.info("Doctor draft saved locally. Set CAREBRIDGE_SMTP_HOST to send it.")
        return "saved"
    try:
        _smtp_send(settings, message)
    except Exception as exc:
        _save_local(settings, message)
        logger.warning("Doctor email failed (%s). Draft saved locally.", exc)
        return "failed"
    logger.info("Doctor escalation email sent for outcome %s.", assessment.outcome)
    return "sent"


def escalation_message(plan: CarePlan, report: str, assessment: Assessment, settings: Settings) -> EmailMessage:
    patient = plan.patient
    subject = f"CareBridge {assessment.outcome}: {patient.name}"
    lines = [
        "CareBridge escalation notice",
        "",
        f"Patient: {patient.name}",
        f"Discharged: {patient.discharged} from {patient.hospital}",
        f"Diagnosis: {patient.diagnosis}",
        "",
        f"Escalation: {assessment.outcome}",
        "What the patient reported:",
        report.strip() or "(empty report)",
        "",
        "Why this was flagged:",
        assessment.guidance,
    ]
    if assessment.summary:
        lines.extend(["", "Summary for the care team:", assessment.summary])
    lines.extend(
        [
            "",
            "This notice was sent automatically because CareBridge safety rules marked the report "
            f"as {assessment.outcome}. It is not a diagnosis.",
        ]
    )
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user or "carebridge@localhost"
    message["To"] = settings.doctor_email or ""
    message.set_content("\n".join(lines))
    return message


def _smtp_send(settings: Settings, message: EmailMessage) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


def _save_local(settings: Settings, message: EmailMessage) -> None:
    folder = settings.data_dir / "doctor_mail"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"escalation-{int(time.time() * 1000)}.txt"
    path.write_text(message.as_string(), encoding="utf-8")
