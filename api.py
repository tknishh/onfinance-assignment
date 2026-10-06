from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from core import repository as repo
from core.config import get_settings
from core.db import get_session, init_db
from core.llm import check_models
from core.orchestrator import handle_feedback, handle_generate
from core.schemas import FeedbackRequest, GenerateRequest, GenerateResponse

app = FastAPI(title="UML Studio API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    kroki_ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.kroki_url.rstrip('/')}/")
            kroki_ok = r.status_code < 500
    except Exception:
        kroki_ok = False
    return {"kroki": kroki_ok, "models": check_models()}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    try:
        return await handle_generate(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/feedback")
async def feedback(req: FeedbackRequest) -> dict:
    return await handle_feedback(req)


@app.get("/conversations/{user_id}")
def conversations(user_id: str) -> list[dict]:
    with get_session() as session:
        convs = repo.list_conversations(session, user_id)
        return [
            {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()}
            for c in convs
        ]


@app.get("/versions/{conversation_id}")
def versions(conversation_id: int) -> list[dict]:
    with get_session() as session:
        vs = repo.list_versions(session, conversation_id)
        out = []
        for v in vs:
            diagrams = repo.list_diagrams(session, v.id)  # type: ignore[arg-type]
            out.append(
                {
                    "id": v.id,
                    "version_no": v.version_no,
                    "prompt": v.prompt,
                    "change_summary": v.change_summary,
                    "diagram_types": v.diagram_types,
                    "diagrams": [
                        {
                            "id": d.id,
                            "kind": d.kind,
                            "title": d.title,
                            "is_valid": d.is_valid,
                            "attempts": d.attempts,
                            "latency_ms": d.latency_ms,
                            "reused": d.reused_from_id is not None,
                        }
                        for d in diagrams
                    ],
                }
            )
        return out
