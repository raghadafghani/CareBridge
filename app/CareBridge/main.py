"""AgentCore Runtime entrypoint.

The sample layout is app/<project>/main.py. The carebridge package sits
beside this file, so the runtime and the local API import the same code.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP = Path(__file__).resolve().parent
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from carebridge.runtime import invoke_payload
from parse import parse_request

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload, context):
    """Handler AgentCore calls. `payload` is the dict sent by the caller."""
    del context
    body = parse_request(payload)
    if not body:
        raise ValueError("Missing payload")
    return invoke_payload(body)


if __name__ == "__main__":
    app.run()
