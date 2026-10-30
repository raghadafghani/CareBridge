"""AgentCore Memory session manager.

AgentCore sets MEMORY_CAREBRIDGEMEMORY_ID when the memory in agentcore.json
is deployed. Local runs leave that variable empty and use file or S3 memory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from carebridge.agents.session import get_memory_session_manager

__all__ = ["get_memory_session_manager"]
