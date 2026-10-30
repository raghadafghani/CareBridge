"""Local commands. `carebridge chat` is the workshop's multi-turn chat.py."""

from __future__ import annotations

import argparse
from pathlib import Path

from carebridge.documents import extract_upload
from carebridge.agents.harness import format_harness
from carebridge.agents.loop_inspection import inspect_loop
from carebridge.service import run_check_in, seed_sample_plan
from carebridge.agents.session import normalize_session_id
from carebridge.plans.store import CareStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="carebridge", description="CareBridge post-discharge companion")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("harness", help="Print the Strands layers without calling a model")
    sub.add_parser("seed", help="Store the sample Maria Haddad plan from the companion UI")

    extract = sub.add_parser("extract", help="Run the discharge agent on a file")
    extract.add_argument("path", type=Path)

    chat = sub.add_parser("chat", help="Multi-turn check-in. Type quit to exit.")
    chat.add_argument("--plan", default="maria-haddad")
    chat.add_argument("--session", default="maria-haddad-followup")

    serve = sub.add_parser("serve", help="HTTP API for the companion UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)

    args = parser.parse_args(argv)
    if args.command == "harness":
        print(format_harness())
        return 0
    if args.command == "seed":
        plan = _seed()
        print(f"Stored plan {plan.id} for {plan.patient.name}.")
        return 0
    if args.command == "extract":
        return _extract(args.path)
    if args.command == "chat":
        return _chat(args.plan, args.session)
    if args.command == "serve":
        import uvicorn

        uvicorn.run("carebridge.api:app", host=args.host, port=args.port)
        return 0
    return 1


def _seed():
    return seed_sample_plan()


def _extract(path: Path) -> int:
    from carebridge.service import extract_care_plan

    data = path.read_bytes()
    text = extract_upload(path.name, data)
    plan, trace, reply = extract_care_plan(text, path.name)
    print(plan.model_dump_json(indent=2))
    print("\n--- loop ---")
    print("\n".join(trace))
    print("\n--- reply ---")
    print(reply)
    return 0


def _chat(plan_id: str, session_id: str) -> int:
    from carebridge.agents.harness import build_followup_agent

    session_id = normalize_session_id(session_id)
    CareStore().get_plan(plan_id)
    trace: list[str] = []
    # One agent for the whole conversation, matching the workshop chat.py.
    # The session manager also persists it, so a later process can resume.
    agent = build_followup_agent(plan_id, session_id, trace, silent=False)
    print(f"CareBridge check-in. Plan {plan_id}. Session {session_id}. Type quit to exit.")
    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not message or message.lower() in {"quit", "exit"}:
            if message.lower() in {"quit", "exit"}:
                return 0
            continue
        trace.clear()
        reply = run_check_in(plan_id, session_id, message, agent=agent, trace=trace)
        if reply.outcome:
            print(f"\n[{reply.outcome}]")
        print(f"\nCareBridge: {reply.text}")
        if reply.questions:
            for index, question in enumerate(reply.questions, start=1):
                print(f"  {index}. {question}")
        print("\n--- loop ---")
        print("\n".join(trace))
        print(inspect_loop(agent, getattr(agent, "_last_result", None)))
    return 0
