"""Amazon Bedrock model used by every agent.

Module 1: Strands defaults to Amazon Bedrock, so no model argument is required.
Set CAREBRIDGE_MODEL_ID to pin a model. The workshop region is us-east-1.
"""

from __future__ import annotations

from typing import Any

from carebridge.config import get_settings


def model_kwargs() -> dict[str, Any]:
    settings = get_settings()
    return _bedrock(settings.model_id, settings.region, max_tokens=None)


def followup_model_kwargs() -> dict[str, Any]:
    """Check-in replies are short. A smaller token cap keeps that turn brief."""
    settings = get_settings()
    model_id = settings.checkin_model_id or settings.model_id
    return _bedrock(model_id, settings.region, max_tokens=280)


def _bedrock(model_id: str | None, region: str, max_tokens: int | None) -> dict[str, Any]:
    if not model_id:
        return {}
    from strands.models import BedrockModel

    config: dict[str, Any] = {"model_id": model_id, "region_name": region}
    if max_tokens is not None:
        config["max_tokens"] = max_tokens
    return {"model": BedrockModel(**config)}
