"""Conversation memory that survives process restarts.

Workshop Module 4. FileSessionManager writes JSON under a session id for local
development. S3SessionManager is the same interface when CAREBRIDGE_SESSION_BUCKET
is set, which is the production backend the workshop names.

The session id is the resume key. Recreating the agent with the same id
restores `agent.messages`. A SlidingWindowConversationManager is separate:
the session manager stores history, the conversation manager bounds what the
model sees on the next call. The workshop uses window_size=20.

Only the patient-facing orchestrator gets a session manager. Module 6
specialists are created per delegation and must not have their own; the
Strands multi-agent runtime rejects an inner agent that carries one.
"""

from __future__ import annotations

import os

from carebridge.config import get_settings
from carebridge.plans.store import safe_id

# Set by AgentCore when agentcore.json declares the CareBridgeMemory resource.
_MEMORY_ID = "MEMORY_CAREBRIDGEMEMORY_ID"


def normalize_session_id(session_id: str) -> str:
    """FileSessionManager rejects path separators. AgentCore also requires 33+ characters."""
    cleaned = safe_id(session_id)
    if len(cleaned) < 33:
        cleaned = f"{cleaned}-carebridge-session"
    if len(cleaned) < 33:
        cleaned = cleaned + ("0" * (33 - len(cleaned)))
    return cleaned[:80]


def get_memory_session_manager(session_id: str, actor_id: str = "carebridge-patient"):
    """AgentCore Memory session, or None when this process is not deployed with one."""
    memory_id = os.getenv(_MEMORY_ID, "").strip()
    if not memory_id:
        return None
    from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
    from bedrock_agentcore.memory.integrations.strands.session_manager import (
        AgentCoreMemorySessionManager,
    )

    return AgentCoreMemorySessionManager(
        AgentCoreMemoryConfig(
            memory_id=memory_id,
            session_id=session_id,
            actor_id=actor_id,
        ),
        os.getenv("AWS_REGION", "us-east-1"),
    )


def build_session_manager(session_id: str):
    session_id = normalize_session_id(session_id)
    memory = get_memory_session_manager(session_id)
    if memory is not None:
        return memory
    settings = get_settings()
    if settings.session_bucket:
        # Production path from Module 4. Same constructor role as FileSessionManager.
        from strands.session.s3_session_manager import S3SessionManager

        return S3SessionManager(
            session_id=session_id,
            bucket=settings.session_bucket,
            prefix="carebridge/sessions",
            region_name=settings.region,
        )

    from strands.session.file_session_manager import FileSessionManager

    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    return FileSessionManager(
        session_id=session_id,
        storage_dir=str(settings.sessions_dir),
    )
