"""Assemble the agent harness. This is the file to read first.

The workshop builds one customer-service agent up across modules. CareBridge
builds two harnesses on those same layers, because the companion UI has two
jobs: understand a discharge report, and stay with the patient afterwards.

    Module 1  Agent + @tool          agents/tools.py
    Module 2  Hooks                  agents/hooks.py   RateLimiterHook and friends
    Module 3  Skills + steering      agents/skills/    SKILL.md, loaded on demand
                                      agents/steering.py  Proceed / Guide gates
    Module 4  Session manager        agents/session.py FileSessionManager or S3
    Module 5  AgentCore entrypoint   runtime.py        BedrockAgentCoreApp
    Module 6  Agents as tools        agents/specialists.py  safety_review_specialist
    Module 7  Evals                  evals/run_evals.py

Skills suggest a procedure. Steering blocks the shortcut. Hooks cap runaway
tool calls. The session manager remembers the conversation. The specialist
owns escalation. The orchestrator talks to the patient.

The discharge harness is single-shot, so it has no session manager. The
follow-up harness has one, and it is the only agent that does: the specialist
it delegates to must not carry its own (Module 6).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from strands import Agent, AgentSkills
from strands.agent.conversation_manager import SlidingWindowConversationManager

from carebridge.config import get_settings
from carebridge.agents.hooks import LoopTraceHook, MedicationBoundaryHook, RateLimiterHook
from carebridge.agents.model import followup_model_kwargs, model_kwargs
from carebridge.agents.prompts import DISCHARGE_PROMPT, FOLLOWUP_PROMPT
from carebridge.agents.session import build_session_manager
from carebridge.agents.specialists import safety_review_specialist
from carebridge.agents.steering import (
    CheckInWorkflowHandler,
    ClinicalBoundaryHandler,
    PlainLanguageGuardrail,
    PlanCommitHandler,
)
from carebridge.agents.tools import (
    commit_care_plan,
    explain_medication,
    load_care_plan,
    read_discharge_document,
    today_recovery_schedule,
)

# Module 1 tool lists. Names and docstrings are what the model uses to choose.
DISCHARGE_TOOLS = [read_discharge_document, commit_care_plan]
FOLLOWUP_TOOLS = [
    load_care_plan,
    today_recovery_schedule,
    explain_medication,
    safety_review_specialist,
]

_PACKAGE = Path(__file__).resolve().parent
DISCHARGE_SKILLS = _PACKAGE / "skills" / "discharge"
FOLLOWUP_SKILLS = _PACKAGE / "skills" / "followup"


def build_discharge_agent(trace: list[str] | None = None) -> Agent:
    """Agent that reads one discharge document and commits a care plan.

    No session manager: extraction is one request, not a conversation to resume.
    """
    return Agent(
        **model_kwargs(),
        tools=DISCHARGE_TOOLS,
        system_prompt=DISCHARGE_PROMPT,
        hooks=[
            RateLimiterHook(max_calls=max(get_settings().max_tool_calls, 8)),
            MedicationBoundaryHook(),
            LoopTraceHook(trace),
        ],
        # Module 3: skills and steering share the plugins list.
        plugins=[
            AgentSkills(skills=[str(DISCHARGE_SKILLS)]),
            PlanCommitHandler(),
        ],
        callback_handler=None,
    )


def build_followup_agent(
    plan_id: str,
    session_id: str,
    trace: list[str] | None = None,
    *,
    silent: bool = True,
) -> Agent:
    """Patient-facing agent: tools, hooks, skills, steering, and memory.

    `silent=True` matches the workshop eval and API path (`callback_handler=None`).
    The CLI leaves streaming on so a local conversation shows the loop.
    """
    settings = get_settings()
    plugins: list[Any] = [
        AgentSkills(skills=[str(FOLLOWUP_SKILLS)]),
        CheckInWorkflowHandler(),
        ClinicalBoundaryHandler(session_id),
    ]
    # Module 3 Part 3. Opt out with CAREBRIDGE_LLM_STEERING=0.
    if settings.llm_steering:
        plugins.append(PlainLanguageGuardrail())

    kwargs: dict[str, Any] = {}
    if silent:
        kwargs["callback_handler"] = None

    return Agent(
        **followup_model_kwargs(),
        tools=FOLLOWUP_TOOLS,
        system_prompt=FOLLOWUP_PROMPT.format(plan_id=plan_id, session_id=session_id),
        hooks=[
            RateLimiterHook(max_calls=settings.max_tool_calls),
            MedicationBoundaryHook(),
            LoopTraceHook(trace),
        ],
        plugins=plugins,
        # Module 4. History is stored; the window bounds what the model sees.
        conversation_manager=SlidingWindowConversationManager(window_size=20),
        session_manager=build_session_manager(session_id),
        **kwargs,
    )


def skill_names(directory: Path) -> list[str]:
    return sorted(path.parent.name for path in directory.glob("*/SKILL.md"))


def harness_manifest() -> dict[str, Any]:
    """Layers actually wired above, without constructing an agent or calling Bedrock."""
    settings = get_settings()
    followup_plugins = [
        "AgentSkills",
        "CheckInWorkflowHandler",
        "ClinicalBoundaryHandler",
    ]
    if settings.llm_steering:
        followup_plugins.append("PlainLanguageGuardrail")
    return {
        "region": settings.region,
        "model_id": settings.model_id or "strands-default-bedrock",
        "llm_steering": settings.llm_steering,
        "discharge": {
            "tools": [tool.__name__ for tool in DISCHARGE_TOOLS],
            "hooks": ["RateLimiterHook", "MedicationBoundaryHook", "LoopTraceHook"],
            "plugins": ["AgentSkills", "PlanCommitHandler"],
            "skills": skill_names(DISCHARGE_SKILLS),
            "session_manager": None,
        },
        "followup": {
            "tools": [tool.__name__ for tool in FOLLOWUP_TOOLS],
            "hooks": ["RateLimiterHook", "MedicationBoundaryHook", "LoopTraceHook"],
            "plugins": followup_plugins,
            "skills": skill_names(FOLLOWUP_SKILLS),
            "session_manager": "S3SessionManager" if settings.session_bucket else "FileSessionManager",
            "conversation_manager": "SlidingWindowConversationManager(window_size=20)",
            "specialist": {
                "tool": "safety_review_specialist",
                "inner_tools": ["assess_warning_signs"],
                "session_manager": None,
            },
        },
    }


def format_harness() -> str:
    manifest = harness_manifest()
    lines = [
        "CareBridge agent harness",
        f"Region: {manifest['region']}",
        f"Model: {manifest['model_id']}",
        f"LLM steering (Module 3 tone guardrail): {'on' if manifest['llm_steering'] else 'off'}",
        "",
        "Discharge agent (upload). No session manager — one document, one plan.",
        *_block(manifest["discharge"]),
        "",
        "Follow-up agent (check-in). Session manager on this agent only.",
        *_block(manifest["followup"]),
    ]
    return "\n".join(lines)


def _block(section: dict[str, Any]) -> list[str]:
    lines = [
        f"  Tools (Module 1): {', '.join(section['tools'])}",
        f"  Hooks (Module 2): {', '.join(section['hooks'])}",
        f"  Plugins (Module 3): {', '.join(section['plugins'])}",
        f"  Skills (Module 3): {', '.join(section['skills'])}",
        f"  Session (Module 4): {section['session_manager']}",
    ]
    if "conversation_manager" in section:
        lines.append(f"  Context window (Module 4): {section['conversation_manager']}")
    specialist = section.get("specialist")
    if specialist:
        lines.append(
            "  Specialist (Module 6): "
            f"{specialist['tool']} runs {', '.join(specialist['inner_tools'])} directly; "
            "no nested model loop; no session manager"
        )
    return lines
