"""HTTP API for the companion UI.

The Care plan page reads a CarePlan. The check-in page posts a message and
renders `text`, `outcome` (monitor, review, emergency), `questions`, and
`summary`. Those fields match the React components. The plan on screen is
the latest document the discharge agent saved, not a built-in patient.

This process is a local development server. The deployed path is AgentCore
(Module 5), which calls the same service functions.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, File, UploadFile
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from carebridge import __version__
from carebridge.documents import extract_upload
from carebridge.errors import CareBridgeError, DocumentError, PlanNotFound
from carebridge.runtime import invoke_payload
from carebridge.schema import CarePlan
from carebridge.service import PROACTIVE_CHECKIN, extract_care_plan, run_check_in, seed_sample_plan
from carebridge.agents.session import normalize_session_id
from carebridge.plans.store import CareStore

logger = logging.getLogger(__name__)

app = FastAPI(title="CareBridge", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextDocument(BaseModel):
    text: str = Field(min_length=1)
    filename: str = "discharge.txt"


class CheckInRequest(BaseModel):
    plan_id: str
    message: str = Field(min_length=1)
    session_id: str = "carebridge-check-in"


class ProactiveRequest(BaseModel):
    plan_id: str
    session_id: str = "carebridge-check-in"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/v1/documents/text", response_model=CarePlan)
def extract_text(body: TextDocument) -> CarePlan:
    plan, _trace, _reply = extract_care_plan(body.text, body.filename)
    return plan


@app.post("/v1/documents/file", response_model=CarePlan)
async def extract_file(file: UploadFile = File(...)) -> CarePlan:
    data = await file.read()
    text = extract_upload(file.filename or "discharge", data)
    plan, _trace, _reply = extract_care_plan(text, file.filename or "discharge.txt")
    return plan


@app.post("/v1/sample-plan", response_model=CarePlan)
def sample_plan() -> CarePlan:
    """The Maria Haddad plan from the companion UI. No model call."""
    return seed_sample_plan()


@app.get("/v1/plans/latest", response_model=CarePlan)
def latest_plan() -> CarePlan:
    """The plan produced from the most recent discharge upload."""
    store = CareStore()
    plan_id = store.latest_plan_id()
    if not plan_id:
        raise PlanNotFound("Upload a discharge report to create a care plan.")
    return store.get_plan(plan_id)


@app.get("/v1/plans/{plan_id}", response_model=CarePlan)
def get_plan(plan_id: str) -> CarePlan:
    return CareStore().get_plan(plan_id)


@app.post("/v1/check-ins")
def check_in(body: CheckInRequest) -> dict:
    reply = run_check_in(body.plan_id, body.session_id, body.message)
    payload = reply.model_dump()
    payload["session_id"] = normalize_session_id(body.session_id)
    return payload


@app.post("/v1/check-ins/proactive")
def proactive(body: ProactiveRequest) -> dict:
    """Scheduled recovery check-in. EventBridge can POST this, or call the AgentCore action."""
    reply = run_check_in(body.plan_id, body.session_id, PROACTIVE_CHECKIN)
    return reply.model_dump()


@app.post("/v1/agent")
def agent_entrypoint(payload: dict) -> dict:
    """Same JSON the AgentCore entrypoint accepts, for local callers."""
    return invoke_payload(payload)


@app.exception_handler(PlanNotFound)
async def _missing_plan(_request, exc: PlanNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(DocumentError)
async def _bad_document(_request, exc: DocumentError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(CareBridgeError)
async def _carebridge_error(_request, exc: CareBridgeError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _unexpected(request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)
    logger.exception("request failed")
    message = str(exc).split("\n", 1)[0]
    lowered = message.lower()
    if "credentials" in lowered or "unable to locate credentials" in lowered:
        detail = "AWS credentials are not configured, so Amazon Bedrock could not be called."
    elif "use case details" in lowered:
        detail = (
            "Amazon Bedrock refused the model until the Anthropic use case form is submitted "
            "for this account. Set CAREBRIDGE_MODEL_ID to a model this account can call."
        )
    elif "model" in lowered or "bedrock" in lowered:
        detail = message[:300]
    else:
        detail = "The care companion could not complete that request."
    return JSONResponse(status_code=503, content={"detail": detail})
