from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from core import repository as repo
from core.config import get_settings
from core.db import get_session, init_db
from core.design_model import missing_names
from core.diagram_types import REGISTRY, DiagramKind
from core.examples import EXAMPLES
from core.llm import check_models
from core.orchestrator import handle_chat, handle_feedback, handle_generate
from core.renderer import render_svg
from core.schemas import (
    ChatRequest,
    DesignModel,
    DiagramResult,
    FeedbackRequest,
    GenerateRequest,
    GenerateResponse,
    RenderRequest,
)
from core.validator import sanitize

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="UML Studio API", version="2.0.0", lifespan=lifespan)
# Browser traffic goes through the Next.js proxy; keep CORS narrow for direct calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/status")
async def status() -> dict[str, Any]:
    settings = get_settings()
    kroki_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.kroki_url.rstrip('/')}/")
            kroki_ok = r.status_code < 500
    except Exception:
        kroki_ok = False
    return {"kroki": kroki_ok, "models": await check_models()}


@app.get("/diagram-types")
def diagram_types() -> list[dict]:
    return [
        {
            "value": kind.value,
            "category": spec.category,
            "description": spec.description,
        }
        for kind, spec in REGISTRY.items()
    ]


@app.get("/examples")
def examples() -> list[dict]:
    return EXAMPLES


@app.get("/conversations")
def conversations(user_id: str = Query(..., max_length=128)) -> list[dict]:
    with get_session() as session:
        convs = repo.list_conversations(session, user_id)
        return [
            repo.conversation_out(session, c).model_dump(mode="json") for c in convs
        ]


@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int, user_id: str = Query(..., max_length=128)
) -> dict[str, bool]:
    with get_session() as session:
        conv = repo.get_conversation(session, conversation_id)
        if conv is None or conv.user_id != user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        repo.delete_conversation(session, conversation_id)
    return {"ok": True}


@app.get("/conversations/{conversation_id}/timeline")
def timeline(
    conversation_id: int, user_id: str = Query(..., max_length=128)
) -> dict:
    with get_session() as session:
        if repo.conversation_owned_by(session, conversation_id, user_id) is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        try:
            return repo.timeline(session, conversation_id).model_dump(mode="json")
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    try:
        return await handle_generate(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.exception("generate failed")
        raise HTTPException(status_code=500, detail="Generation failed") from None


@app.post("/feedback")
async def feedback(req: FeedbackRequest) -> dict:
    try:
        return await handle_feedback(req)
    except PermissionError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/diagrams/{diagram_id}/render", response_model=DiagramResult)
async def render_diagram(diagram_id: int, body: RenderRequest) -> DiagramResult:
    code = sanitize(body.plantuml)
    ok, svg, err = await render_svg(code)
    if not ok:
        raise HTTPException(status_code=422, detail=err or "Render failed")

    with get_session() as session:
        diag = repo.diagram_owned_by(session, diagram_id, body.user_id)
        if diag is None:
            raise HTTPException(status_code=404, detail="Diagram not found")
        version = repo.get_version(session, diag.version_id)
        design = None
        if version and version.design_model:
            try:
                design = DesignModel.model_validate(version.design_model)
            except Exception:
                design = None
        kind = (
            DiagramKind(diag.kind)
            if diag.kind in DiagramKind._value2member_map_
            else None
        )
        warnings: list[str] = []
        if kind and design:
            missing = missing_names(code, design, kind)
            if missing:
                warnings = [f"Missing from shared design model: {', '.join(missing)}"]
        diag.plantuml = code
        diag.svg = svg
        diag.is_valid = True
        diag.error = None
        diag.warnings = warnings
        session.add(diag)
        for t in repo.trajectories_for_diagram(session, diagram_id):
            t.metrics = {**(t.metrics or {}), "manual_edit": True}
            # Manual edits are syntax-valid but not training gold.
            syntax = 1.0
            t.reward = round(0.2 * syntax, 4)
            session.add(t)
        session.commit()
        session.refresh(diag)
        return DiagramResult(
            diagram_id=diag.id or 0,
            kind=diag.kind,
            title=diag.title,
            plantuml=diag.plantuml,
            svg=diag.svg,
            is_valid=diag.is_valid,
            error=diag.error,
            attempts=diag.attempts,
            latency_ms=diag.latency_ms,
            reused=diag.reused_from_id is not None,
            warnings=list(diag.warnings or []),
            version_id=diag.version_id,
        )


@app.post("/chat")
async def chat(req: ChatRequest):
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: str, data: Any) -> None:
        await queue.put((event, jsonable_encoder(data)))

    async def worker():
        try:
            await handle_chat(req, emit)
        except Exception as e:
            logger.exception("chat failed")
            await emit("error", {"message": str(e)})
            await emit(
                "done",
                {"conversation_id": req.conversation_id, "version_id": None},
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())

    async def stream():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if item is None:
                    break
                event, data = item
                yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
