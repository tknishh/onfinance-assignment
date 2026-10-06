from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core import feedback as feedback_svc
from core import repository as repo
from core.cache import prompt_hash
from core.config import get_settings
from core.db import get_session
from core.design_model import build_design_model, kind_signature, update_design_model
from core.diagram_types import DiagramKind, normalize_types
from core.generator import (
    GeneratedDiagram,
    generate_one,
    reuse_diagram,
    run_parallel,
    update_one,
)
from core.llm import invoke_structured
from core.models import Diagram
from core.prompts import system_diff, user_diff
from core.schemas import (
    DesignModel,
    DiagramResult,
    FeedbackRequest,
    GenerateRequest,
    GenerateResponse,
    PromptDiff,
)
from core.tracing import TrajectoryRecorder


@dataclass
class DiagramSnapshot:
    """Detached copy of Diagram fields safe to use outside a Session."""

    id: Optional[int]
    kind: str
    title: str
    plantuml: str
    svg: Optional[str]
    is_valid: bool
    error: Optional[str]
    attempts: int
    latency_ms: int
    model: str
    warnings: list[str]


def _snapshot(d: Diagram) -> DiagramSnapshot:
    return DiagramSnapshot(
        id=d.id,
        kind=d.kind,
        title=d.title,
        plantuml=d.plantuml,
        svg=d.svg,
        is_valid=d.is_valid,
        error=d.error,
        attempts=d.attempts,
        latency_ms=d.latency_ms,
        model=d.model,
        warnings=list(d.warnings or []),
    )


def _to_result(d: Diagram, reused: bool = False) -> DiagramResult:
    return DiagramResult(
        diagram_id=d.id or 0,
        kind=d.kind,
        title=d.title,
        plantuml=d.plantuml,
        svg=d.svg,
        is_valid=d.is_valid,
        error=d.error,
        attempts=d.attempts,
        latency_ms=d.latency_ms,
        reused=reused or d.reused_from_id is not None,
        warnings=list(d.warnings or []),
    )


def _persist_generated(
    session,
    version_id: int,
    items: list[GeneratedDiagram],
) -> list[Diagram]:
    saved: list[Diagram] = []
    for item in items:
        diagram = Diagram(
            version_id=version_id,
            kind=item.kind.value,
            title=item.title,
            plantuml=item.plantuml,
            svg=item.svg,
            is_valid=item.is_valid,
            error=item.error,
            attempts=item.attempts,
            latency_ms=item.latency_ms,
            model=item.model,
            reused_from_id=item.reused_from_id,
            warnings=list(item.warnings),
        )
        diagram = repo.save_diagram(session, diagram)
        saved.append(diagram)
        if item.recorder:
            metrics = {
                "kind": item.kind.value,
                "syntax_valid": item.is_valid,
                "attempts": item.attempts,
                "latency_ms": item.latency_ms,
                "consistent": not item.warnings,
            }
            rows = item.recorder.to_rows(diagram.id, metrics)
            # Initial reward from syntax only (user feedback later)
            for row in rows:
                from core.feedback import compute_reward

                row.reward = compute_reward(
                    None, item.is_valid, item.attempts, None, not item.warnings
                )
            repo.save_trajectories(session, rows)
    return saved


def _save_recorder(session, recorder: Optional[TrajectoryRecorder]) -> None:
    if recorder and recorder.items:
        repo.save_trajectories(session, recorder.to_rows(None, {}))


def _load_design(raw: Optional[dict]) -> Optional[DesignModel]:
    if not raw:
        return None
    try:
        return DesignModel.model_validate(raw)
    except Exception:
        return None


async def _new_flow(
    user_id: str,
    prompt: str,
    kinds: list[DiagramKind],
    unknown: list[str],
    on_done: Optional[Callable[[GeneratedDiagram], None]],
) -> GenerateResponse:
    design, design_recorder = await build_design_model(prompt, kinds)

    with get_session() as session:
        conv = repo.create_conversation(session, user_id, prompt[:60])
        version = repo.create_version(
            session,
            conversation_id=conv.id,  # type: ignore[arg-type]
            version_no=1,
            prompt=prompt,
            diagram_types=[k.value for k in kinds],
            design_model=design.model_dump() if design else None,
        )
        _save_recorder(session, design_recorder)
        conversation_id = conv.id
        version_id = version.id
        version_no = version.version_no

    tasks = [generate_one(prompt, k, design) for k in kinds]
    items = await run_parallel(tasks, on_done=on_done)

    with get_session() as session:
        saved = _persist_generated(session, version_id, items)  # type: ignore[arg-type]
        diagrams = [_to_result(d, reused=False) for d in saved]

    return GenerateResponse(
        user_id=user_id,
        conversation_id=conversation_id,  # type: ignore[arg-type]
        version_id=version_id,  # type: ignore[arg-type]
        version_no=version_no,
        change_summary=None,
        unknown_types=unknown,
        diagrams=diagrams,
        design_model=design,
    )


async def _update_flow(
    user_id: str,
    conversation_id: int,
    prompt: str,
    kinds: list[DiagramKind],
    unknown: list[str],
    on_done: Optional[Callable[[GeneratedDiagram], None]],
) -> GenerateResponse:
    settings = get_settings()
    with get_session() as session:
        prev = repo.latest_version(session, conversation_id)
        if prev is None:
            return await _new_flow(user_id, prompt, kinds, unknown, on_done)
        prev_diagrams = repo.diagrams_by_kind(session, prev.id)  # type: ignore[arg-type]
        old_prompt = prev.prompt
        prev_id = prev.id
        prev_no = prev.version_no
        old_design = _load_design(prev.design_model)
        prev_map = {k: _snapshot(prev_diagrams[k]) for k in prev_diagrams}

    kind_values = [k.value for k in kinds]
    recorder = TrajectoryRecorder(
        "diff",
        settings.fast_model,
        prompt_hash("diff", old_prompt, prompt),
    )

    async def run_diff() -> PromptDiff:
        try:
            return await invoke_structured(
                "fast",
                PromptDiff,
                [
                    SystemMessage(content=system_diff()),
                    HumanMessage(content=user_diff(old_prompt, prompt, kind_values)),
                ],
                recorder,
            )
        except Exception:
            return PromptDiff(
                summary="Full regenerate due to diff failure",
                affected_kinds=kind_values,
                unaffected_kinds=[],
            )

    if old_design is not None:
        diff, (design, design_recorder) = await asyncio.gather(
            run_diff(), update_design_model(old_design, old_prompt, prompt, kinds)
        )
        if design is None:
            design = old_design
    else:
        diff, (design, design_recorder) = await asyncio.gather(
            run_diff(), build_design_model(prompt, kinds)
        )

    affected = {normalize_types([k])[0][0] for k in diff.affected_kinds if normalize_types([k])[0]}
    unaffected_raw = {
        normalize_types([k])[0][0] for k in diff.unaffected_kinds if normalize_types([k])[0]
    }

    coros: list = []
    reused_items: list[GeneratedDiagram] = []
    for kind in kinds:
        old = prev_map.get(kind.value)
        model_unchanged = old_design is not None and kind_signature(
            old_design, kind
        ) == kind_signature(design, kind)
        if old is None or old_design is None:
            # Diagrams from before the shared model existed use their own naming,
            # so regenerate them against the model rather than editing them.
            coros.append(generate_one(prompt, kind, design))
        elif model_unchanged and kind in unaffected_raw and kind not in affected:
            item = reuse_diagram(old)
            reused_items.append(item)
            if on_done:
                on_done(item)
        else:
            coros.append(update_one(prompt, old_prompt, old, diff.summary, design))

    generated = await run_parallel(coros, on_done=on_done) if coros else []
    all_items = generated + reused_items

    with get_session() as session:
        version = repo.create_version(
            session,
            conversation_id=conversation_id,
            version_no=prev_no + 1,
            prompt=prompt,
            diagram_types=kind_values,
            parent_version_id=prev_id,
            change_summary=diff.summary,
            design_model=design.model_dump() if design else None,
        )
        saved = _persist_generated(session, version.id, all_items)  # type: ignore[arg-type]
        if recorder.items:
            rows = recorder.to_rows(None, {"summary": diff.summary})
            repo.save_trajectories(session, rows)
        _save_recorder(session, design_recorder)
        diagrams = [
            _to_result(d, reused=d.reused_from_id is not None) for d in saved
        ]
        version_id = version.id
        version_no = version.version_no

    return GenerateResponse(
        user_id=user_id,
        conversation_id=conversation_id,
        version_id=version_id,  # type: ignore[arg-type]
        version_no=version_no,
        change_summary=diff.summary,
        unknown_types=unknown,
        diagrams=diagrams,
        design_model=design,
    )


async def handle_generate(
    req: GenerateRequest,
    on_done: Optional[Callable[[GeneratedDiagram], None]] = None,
) -> GenerateResponse:
    kinds, unknown = normalize_types(req.diagram_types)
    if not kinds:
        raise ValueError(
            f"No valid diagram types. Unknown: {unknown}. "
            "Use names like sequence, component, class, activity."
        )
    user_id = req.user_id or str(uuid.uuid4())
    with get_session() as session:
        repo.get_or_create_user(session, user_id)
        latest = (
            repo.latest_version(session, req.conversation_id)
            if req.conversation_id is not None
            else None
        )

    if req.conversation_id is None or latest is None:
        return await _new_flow(user_id, req.prompt, kinds, unknown, on_done)
    return await _update_flow(
        user_id, req.conversation_id, req.prompt, kinds, unknown, on_done
    )


async def handle_feedback(req: FeedbackRequest) -> dict:
    with get_session() as session:
        fb = repo.add_feedback(session, req)
        fb_id = fb.id
        # re-load for reward after commit
        feedback_svc.apply_reward(fb)

    # Judge off the critical path when possible
    if req.diagram_id is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(feedback_svc.judge_async(req.diagram_id))
        except RuntimeError:
            await feedback_svc.judge_async(req.diagram_id)

    if req.apply_as_update and req.comment:
        with get_session() as session:
            v = repo.get_version(session, req.version_id)
            if v is None:
                return {"ok": True, "feedback_id": fb_id}
            prompt = v.prompt + "\n\nRevision request: " + req.comment
            types = list(v.diagram_types)
            cid = v.conversation_id
        resp = await handle_generate(
            GenerateRequest(
                prompt=prompt,
                diagram_types=types,
                user_id=req.user_id,
                conversation_id=cid,
            )
        )
        return {"ok": True, "feedback_id": fb_id, "generate": resp.model_dump()}

    return {"ok": True, "feedback_id": fb_id}
