"""Local JSON store (with optional S3 backing) for documents, care plans, and check-in state.

Conversation text is persisted by the Strands session manager (Module 4).
This store holds the structured plan the UI renders and the escalation
state machine. Neither of those belongs in the model's context alone:
the safety tool reads the plan from here so a prompt cannot edit a dose.

When `CAREBRIDGE_SESSION_BUCKET` is configured in cloud deployments (such as
AgentCore Runtime where `/tmp/carebridge` is ephemeral), `CareStore` mirrors
writes to S3 under `carebridge/store/` and hydrates from S3 on local cache miss.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from carebridge.config import get_settings
from carebridge.errors import DocumentError, PlanNotFound
from carebridge.schema import CarePlan
from carebridge.safety.warning_signs import DialogState

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]+")
_S3_PREFIX = "carebridge/store"


def safe_id(value: str) -> str:
    """Session and plan ids become filenames. Reject path separators, as FileSessionManager does."""
    cleaned = _SAFE_ID.sub("-", value).strip("-")
    if not cleaned or cleaned in {".", ".."}:
        raise DocumentError("Identifier is empty or not safe to store.")
    return cleaned[:80]


class CareStore:
    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        self.root = root or settings.data_dir
        self.bucket = None if root is not None else settings.session_bucket
        self.region = settings.region
        self.documents = self.root / "documents"
        self.plans = self.root / "plans"
        self.dialogs = self.root / "dialogs"
        for directory in (self.documents, self.plans, self.dialogs):
            directory.mkdir(parents=True, exist_ok=True)

    def save_document(self, text: str, filename: str = "discharge.txt") -> str:
        document_id = safe_id(Path(filename).stem) + "-" + uuid.uuid4().hex[:8]
        path = self.documents / f"{document_id}.txt"
        path.write_text(text, encoding="utf-8")
        self._s3_put_text(f"documents/{document_id}.txt", text)
        return document_id

    def read_document(self, document_id: str) -> str:
        cleaned = safe_id(document_id)
        path = self.documents / f"{cleaned}.txt"
        if not path.is_file():
            remote = self._s3_get_text(f"documents/{cleaned}.txt")
            if remote is not None:
                path.write_text(remote, encoding="utf-8")
                return remote
            raise DocumentError(f"No discharge document with id {document_id}.")
        return path.read_text(encoding="utf-8")

    def source_document_text(self, document_id: str | None = None) -> str:
        """Return text for a specific document_id when known, or fall back to latest."""
        if document_id:
            try:
                return self.read_document(document_id)
            except DocumentError:
                pass
        return self.latest_document_text()

    def save_plan(self, plan: CarePlan) -> CarePlan:
        plan_id = safe_id(plan.id)
        stored = plan.model_copy(update={"id": plan_id})
        payload = stored.model_dump()
        self._write_json(self.plans / f"{plan_id}.json", payload)
        pointer = self.root / "latest_plan.txt"
        pointer.write_text(plan_id, encoding="utf-8")
        self._s3_put_text(f"plans/{plan_id}.json", json.dumps(payload, indent=2))
        self._s3_put_text("latest_plan.txt", plan_id)
        return stored

    def get_plan(self, plan_id: str) -> CarePlan:
        cleaned = safe_id(plan_id)
        path = self.plans / f"{cleaned}.json"
        if not path.is_file():
            remote = self._s3_get_text(f"plans/{cleaned}.json")
            if remote is not None:
                path.write_text(remote, encoding="utf-8")
            else:
                raise PlanNotFound(f"No care plan with id {plan_id}.")
        return CarePlan.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def latest_document_text(self) -> str:
        files = [path for path in self.documents.glob("*.txt") if path.is_file()]
        if not files:
            return ""
        newest = max(files, key=lambda path: path.stat().st_mtime)
        return newest.read_text(encoding="utf-8")

    def latest_plan_id(self) -> str | None:
        pointer = self.root / "latest_plan.txt"
        if pointer.is_file():
            value = pointer.read_text(encoding="utf-8").strip()
            if value:
                return value
        remote = self._s3_get_text("latest_plan.txt")
        if remote and remote.strip():
            cleaned = remote.strip()
            pointer.write_text(cleaned, encoding="utf-8")
            return cleaned
        return None

    def get_dialog(self, session_id: str) -> DialogState:
        cleaned = safe_id(session_id)
        path = self._dialog_path(cleaned)
        if not path.is_file():
            remote = self._s3_get_text(f"dialogs/{cleaned}.json")
            if remote is not None:
                path.write_text(remote, encoding="utf-8")
            else:
                return DialogState()
        return DialogState.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save_dialog(self, session_id: str, dialog: DialogState) -> None:
        cleaned = safe_id(session_id)
        payload = dialog.model_dump()
        self._write_json(self._dialog_path(cleaned), payload)
        self._s3_put_text(f"dialogs/{cleaned}.json", json.dumps(payload, indent=2))

    def _dialog_path(self, session_id: str) -> Path:
        return self.dialogs / f"{safe_id(session_id)}.json"

    def _s3_put_text(self, rel_key: str, text: str) -> None:
        if not self.bucket:
            return
        try:
            import boto3

            s3 = boto3.client("s3", region_name=self.region)
            s3.put_object(
                Bucket=self.bucket,
                Key=f"{_S3_PREFIX}/{rel_key}",
                Body=text.encode("utf-8"),
                ContentType="application/json" if rel_key.endswith(".json") else "text/plain; charset=utf-8",
            )
        except Exception as exc:
            logger.warning("S3 store write skipped for %s: %s", rel_key, exc)

    def _s3_get_text(self, rel_key: str) -> str | None:
        if not self.bucket:
            return None
        try:
            import boto3

            s3 = boto3.client("s3", region_name=self.region)
            response = s3.get_object(Bucket=self.bucket, Key=f"{_S3_PREFIX}/{rel_key}")
            return response["Body"].read().decode("utf-8")
        except Exception:
            return None

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(path)
