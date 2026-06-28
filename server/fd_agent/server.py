"""FastAPI HTTP server wrapping the FD ADK agent.

Endpoint: POST /run
  Body:    {"query": "<natural language question>"}
  Headers: Authorization: Bearer <jwt>  (forwarded to MCP tool calls in propagate mode)

Endpoint: GET /health
  Returns: {"status": "ok"}
"""

import asyncio
import logging
import os
import uuid
import warnings

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from .agent import plugin, root_agent

warnings.filterwarnings(
    "ignore",
    message=".*PydanticSerializationUnexpectedValue.*",
    category=UserWarning,
)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_APP_NAME = "fd_agent"

session_service = InMemorySessionService()
runner = Runner(
    app_name=_APP_NAME,
    agent=root_agent,
    session_service=session_service,
    plugins=[plugin] if plugin is not None else [],
)

_CANCEL_SCOPE_MSG = "Attempted to exit cancel scope in a different task than it was entered in"


def _asyncio_exception_handler(loop, context):
    exc = context.get("exception")
    if isinstance(exc, RuntimeError) and str(exc) == _CANCEL_SCOPE_MSG:
        logger.debug("MCP session teardown: %s", _CANCEL_SCOPE_MSG)
        return
    default = getattr(loop, "default_exception_handler", None)
    if default is not None:
        default(context)
    else:
        logger.exception("Unhandled asyncio exception: %s", context.get("message", context))


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_asyncio_exception_handler)
    yield


app = FastAPI(title="FD ADK Agent", version="1.0.0", lifespan=lifespan)


class RunRequest(BaseModel):
    query: str


@app.post("/run")
async def run(request: Request, body: RunRequest):
    user_id = "demo"
    session_id = str(uuid.uuid4())

    try:
        await session_service.create_session(
            app_name=_APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state={"headers": dict(request.headers)},
        )

        response_parts = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=body.query)],
            ),
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)

        return {"response": "\n".join(response_parts)}
    except Exception as e:
        logger.exception("Agent run failed")
        return JSONResponse(
            status_code=500,
            content={"detail": str(e), "type": type(e).__name__},
        )


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
