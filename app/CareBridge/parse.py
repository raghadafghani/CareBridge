"""Normalize the JSON AgentCore passes into the entrypoint."""

from __future__ import annotations


def parse_request(payload: dict | None) -> dict:
    body = dict(payload or {})
    body.setdefault("action", "check_in")
    return body
