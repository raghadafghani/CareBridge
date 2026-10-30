"""The model the Runtime uses. Model ids come from CAREBRIDGE_MODEL_ID."""

from __future__ import annotations

import sys
from pathlib import Path

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from carebridge.agents.model import followup_model_kwargs, model_kwargs


def load_model():
    """Discharge model. None means the Strands default Bedrock model."""
    return model_kwargs().get("model")


def load_checkin_model():
    """Shorter check-in model."""
    return followup_model_kwargs().get("model")
