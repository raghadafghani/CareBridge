"""Local JSON store for discharge documents, care plans, and check-in state.

Conversation text is persisted by the Strands session manager (Module 4).
This store holds the structured plan the UI renders and the escalation
state machine. Neither of those belongs in the model's context alone:
the safety tool reads the plan from here so a prompt cannot edit a dose.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from carebridge.config import get_settings
from carebridge.errors import DocumentError, PlanNotFound
from carebridge.schema import CarePlan
from carebridge.safety.warning_signs import DialogState

_SAFE_ID = re.compile(r"[^A-Za-z0-9_-]+")


def safe_id(value: str) -> str:
    """Session and plan ids become filenames. Reject path separators, as FileSessionManager does."""
    cleaned = _SAFE_ID.sub("-", value).strip("-")
    if not cleaned or cleaned in {".", ".."}:
        raise DocumentError("Identifier is empty or not safe to store.")
    return cleaned[:80]


class CareStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().data_dir
        self.documents = self.root / "documents"
        self.plans = self.root / "plans"
        self.dialogs = self.root / "dialogs"
        for directory in (self.documents, self.plans, self.dialogs):
            directory.mkdir(parents=True, exist_ok=True)

    def save_document(self, text: str, filename: str = "discharge.txt") -> str:
        document_id = safe_id(Path(filename).stem) + "-" + uuid.uuid4().hex[:8]
        path = self.documents / f"{document_id}.txt"
        path.write_text(text, encoding="utf-8")
        return document_id

    def read_document(self, document_id: str) -> str:
        path = self.documents / f"{safe_id(document_id)}.txt"
        if not path.is_file():
            raise DocumentError(f"No discharge document with id {document_id}.")
        return path.read_text(encoding="utf-8")

    def save_plan(self, plan: CarePlan) -> CarePlan:
        plan_id = safe_id(plan.id)
        stored = plan.model_copy(update={"id": plan_id})
        self._write_json(self.plans / f"{plan_id}.json", stored.model_dump())
        pointer = self.root / "latest_plan.txt"
        pointer.write_text(plan_id, encoding="utf-8")
        return stored

    def get_plan(self, plan_id: str) -> CarePlan:
        path = self.plans / f"{safe_id(plan_id)}.json"
        if not path.is_file():
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
        if not pointer.is_file():
            return None
        return pointer.read_text(encoding="utf-8").strip() or None

    def get_dialog(self, session_id: str) -> DialogState:
        path = self._dialog_path(session_id)
        if not path.is_file():
            return DialogState()
        return DialogState.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save_dialog(self, session_id: str, dialog: DialogState) -> None:
        self._write_json(self._dialog_path(session_id), dialog.model_dump())

    def _dialog_path(self, session_id: str) -> Path:
        return self.dialogs / f"{safe_id(session_id)}.json"

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(path)
