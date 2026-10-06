from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core import feedback as feedback_svc
from core import repository as repo
from core.cache import prompt_hash
from core.config import get_settings
from core.db import get_session
from core.design_model import build_design_model, kind_signature, update_design_model
from core.diagram_types import DiagramKind, normalize_types
from core.examples import DEFAULT_KINDS
from core.feedback import compute_reward
from core.generator import (
    GeneratedDiagram,
    generate_one,
    reuse_diagram,
    run_parallel,
    update_one,
)
from core.intent import answer_question, classify_followup, compose_prompt
from core.llm import invoke_structured
from core.models import Diagram
from core.prompts import system_diff, user_diff
from core.schemas import (
    ChatRequest,
    DesignModel,
    DiagramResult,
    FeedbackRequest,
    GenerateRequest,
    GenerateResponse,
    PromptDiff,
)
from core.tracing import TrajectoryRecorder

logger = logging.getLogger(__name__)

Emit = Callable[[str, dict], Awaitable[None]]

# Keep references so fire-and-forget judge tasks are not GC'd mid-flight.
_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        return
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


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
        version_id=d.version_id,
    )


def _generated_payload(item: GeneratedDiagram) -> dict:
    return {
        "kind": item.kind.value,
        "title": item.title,
        "is_valid": item.is_valid,
        "error": item.error,
        "attempts": item.attempts,
        "latency_ms": item.latency_ms,
        "reused": item.reused,
        "warnings": list(item.warnings),
        "plantuml": item.plantuml,
        "svg": item.svg,
    }


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
            for row in rows:
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


async def _maybe_emit(cb, *args) -> None:
    if cb is None:
        return
    res = cb(*args)
    if asyncio.iscoroutine(res) or isinstance(res, Awaitable):
        await res  # type: ignore[misc]


async def _new_flow(
    user_id: str,
    prompt: str,
    kinds: list[DiagramKind],
    unknown: list[str],
    on_done: Optional[Callable] = None,
    *,
    conversation_id: Optional[int] = None,
    on_design: Optional[Callable] = None,
    revisions: Optional[list[str]] = None,
    instruction: Optional[str] = None,
) -> GenerateResponse:
    design, design_recorder = await build_design_model(prompt, kinds)
    await _maybe_emit(on_design, design)

    with get_session() as session:
        if conversation_id is None:
            conv = repo.create_conversation(
                session, user_id, prompt[:60], base_prompt=prompt
            )
            conversation_id = conv.id
        else:
            conv = repo.get_conversation(session, conversation_id)
            if conv is not None and not conv.base_prompt:
                conv.base_prompt = prompt
                session.add(conv)
                session.commit()
        _save_recorder(session, design_recorder)

    # Generate before creating a version so a crash/cancel never leaves
    # an empty "latest" version.
    tasks = [(k, generate_one(prompt, k, design)) for k in kinds]
    items = await run_parallel(tasks, on_done=on_done)

    with get_session() as session:
        version = repo.create_version(
            session,
            conversation_id=conversation_id,  # type: ignore[arg-type]
            prompt=prompt,
            diagram_types=[k.value for k in kinds],
            design_model=design.model_dump() if design else None,
            revisions=list(revisions or []),
            instruction=instruction,
        )
        saved = _persist_generated(session, version.id, items)  # type: ignore[arg-type]
        diagrams = [_to_result(d, reused=False) for d in saved]
        version_id = version.id
        version_no = version.version_no

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
    on_done: Optional[Callable] = None,
    *,
    mode: Literal["revise", "edit", "add", "remove"] = "revise",
    instruction: Optional[str] = None,
    revisions: Optional[list[str]] = None,
    target_kinds: Optional[set[DiagramKind]] = None,
    on_design: Optional[Callable] = None,
) -> GenerateResponse:
    settings = get_settings()
    targets = set(target_kinds or set())
    with get_session() as session:
        prev = repo.latest_version(session, conversation_id)
        if prev is None:
            return await _new_flow(
                user_id,
                prompt,
                kinds,
                unknown,
                on_done,
                conversation_id=conversation_id,
                on_design=on_design,
                revisions=revisions,
                instruction=instruction,
            )
        prev_diagrams = repo.diagrams_by_kind(session, prev.id)  # type: ignore[arg-type]
        old_prompt = prev.prompt
        prev_id = prev.id
        prev_revisions = list(prev.revisions or [])
        old_design = _load_design(prev.design_model)
        prev_map = {k: _snapshot(prev_diagrams[k]) for k in prev_diagrams}

    kind_values = [k.value for k in kinds]
    change_summary = instruction or "Updated design"
    design = old_design
    design_recorder = None
    recorder = TrajectoryRecorder(
        "diff",
        settings.fast_model,
        prompt_hash("diff", old_prompt, prompt),
    )
    affected: set[DiagramKind] = set()
    unaffected_raw: set[DiagramKind] = set()

    if mode == "remove":
        change_summary = instruction or f"Removed {', '.join(k.value for k in targets)}"
        await _maybe_emit(on_design, design)
        reused_items = []
        for kind in kinds:
            old = prev_map.get(kind.value)
            if old is None:
                continue
            item = reuse_diagram(old)
            reused_items.append(item)
            await _maybe_emit(on_done, item)
        with get_session() as session:
            version = repo.create_version(
                session,
                conversation_id=conversation_id,
                prompt=prompt,
                diagram_types=kind_values,
                parent_version_id=prev_id,
                change_summary=change_summary,
                design_model=design.model_dump() if design else None,
                revisions=list(revisions if revisions is not None else prev_revisions),
                instruction=instruction,
            )
            saved = _persist_generated(session, version.id, reused_items)  # type: ignore[arg-type]
            diagrams = [_to_result(d, reused=True) for d in saved]
            return GenerateResponse(
                user_id=user_id,
                conversation_id=conversation_id,
                version_id=version.id,  # type: ignore[arg-type]
                version_no=version.version_no,
                change_summary=change_summary,
                unknown_types=unknown,
                diagrams=diagrams,
                design_model=design,
            )

    if mode == "add":
        change_summary = instruction or f"Added {', '.join(k.value for k in targets)}"
        if design is None:
            design, design_recorder = await build_design_model(prompt, kinds)
        await _maybe_emit(on_design, design)
        coros: list[tuple[DiagramKind, Awaitable[GeneratedDiagram]]] = []
        reused_items = []
        for kind in kinds:
            if kind in targets or kind.value not in prev_map:
                coros.append((kind, generate_one(prompt, kind, design)))
            else:
                item = reuse_diagram(prev_map[kind.value])
                reused_items.append(item)
                await _maybe_emit(on_done, item)
        generated = await run_parallel(coros, on_done=on_done) if coros else []
        all_items = generated + reused_items
        with get_session() as session:
            version = repo.create_version(
                session,
                conversation_id=conversation_id,
                prompt=prompt,
                diagram_types=kind_values,
                parent_version_id=prev_id,
                change_summary=change_summary,
                design_model=design.model_dump() if design else None,
                revisions=list(revisions if revisions is not None else prev_revisions),
                instruction=instruction,
            )
            saved = _persist_generated(session, version.id, all_items)  # type: ignore[arg-type]
            _save_recorder(session, design_recorder)
            diagrams = [
                _to_result(d, reused=d.reused_from_id is not None) for d in saved
            ]
            return GenerateResponse(
                user_id=user_id,
                conversation_id=conversation_id,
                version_id=version.id,  # type: ignore[arg-type]
                version_no=version.version_no,
                change_summary=change_summary,
                unknown_types=unknown,
                diagrams=diagrams,
                design_model=design,
            )

    # revise or edit
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

    if mode == "edit":
        change_summary = instruction or "Edited diagrams"
        if old_design is not None:
            design, design_recorder = await update_design_model(
                old_design, old_prompt, prompt, kinds
            )
            if design is None:
                design = old_design
        else:
            design, design_recorder = await build_design_model(prompt, kinds)
        await _maybe_emit(on_design, design)
        affected = set(targets)
        for kind in kinds:
            if old_design is None or kind_signature(old_design, kind) != kind_signature(
                design, kind
            ):
                affected.add(kind)
        unaffected_raw = {k for k in kinds if k not in affected}
    else:
        # revise
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
        change_summary = instruction or diff.summary
        await _maybe_emit(on_design, design)
        affected = {
            normalize_types([k])[0][0]
            for k in diff.affected_kinds
            if normalize_types([k])[0]
        }
        unaffected_raw = {
            normalize_types([k])[0][0]
            for k in diff.unaffected_kinds
            if normalize_types([k])[0]
        }

    coros = []
    reused_items: list[GeneratedDiagram] = []
    for kind in kinds:
        old = prev_map.get(kind.value)
        model_unchanged = old_design is not None and kind_signature(
            old_design, kind
        ) == kind_signature(design, kind)
        if old is None or old_design is None:
            coros.append((kind, generate_one(prompt, kind, design)))
        elif mode == "edit":
            if kind in affected:
                coros.append(
                    (kind, update_one(prompt, old_prompt, old, change_summary, design))
                )
            else:
                item = reuse_diagram(old)
                reused_items.append(item)
                await _maybe_emit(on_done, item)
        elif model_unchanged and kind in unaffected_raw and kind not in affected:
            item = reuse_diagram(old)
            reused_items.append(item)
            await _maybe_emit(on_done, item)
        else:
            coros.append(
                (kind, update_one(prompt, old_prompt, old, change_summary, design))
            )

    generated = await run_parallel(coros, on_done=on_done) if coros else []
    all_items = generated + reused_items

    with get_session() as session:
        version = repo.create_version(
            session,
            conversation_id=conversation_id,
            prompt=prompt,
            diagram_types=kind_values,
            parent_version_id=prev_id,
            change_summary=change_summary,
            design_model=design.model_dump() if design else None,
            revisions=list(revisions if revisions is not None else prev_revisions),
            instruction=instruction,
        )
        saved = _persist_generated(session, version.id, all_items)  # type: ignore[arg-type]
        if recorder.items:
            rows = recorder.to_rows(None, {"summary": change_summary})
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
        change_summary=change_summary,
        unknown_types=unknown,
        diagrams=diagrams,
        design_model=design,
    )


async def handle_generate(
    req: GenerateRequest,
    on_done: Optional[Callable] = None,
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
        if repo.version_owned_by(session, req.version_id, req.user_id) is None:
            raise PermissionError("Version not found")
        if req.diagram_id is not None:
            if repo.diagram_owned_by(session, req.diagram_id, req.user_id) is None:
                raise PermissionError("Diagram not found")
        fb = repo.add_feedback(session, req)
        fb_id = fb.id
        feedback_svc.apply_reward(fb)

    if req.diagram_id is not None:
        _spawn(feedback_svc.judge_async(req.diagram_id))

    return {"ok": True, "feedback_id": fb_id}


async def handle_chat(req: ChatRequest, emit: Emit) -> None:
    with get_session() as session:
        repo.get_or_create_user(session, req.user_id)

    message = req.message
    hint_kinds = list(req.diagram_types or [])
    stripped = message.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and "prompt" in data:
                message = data["prompt"]
                hint_kinds = list(data.get("diagram_types") or hint_kinds)
        except Exception:
            pass

    kinds, unknown = normalize_types(hint_kinds or DEFAULT_KINDS)
    if not kinds:
        kinds, unknown = normalize_types(DEFAULT_KINDS)

    async def on_design(d: Optional[DesignModel]) -> None:
        await emit("design_model", d.model_dump() if d else None)

    async def on_done(item: GeneratedDiagram) -> None:
        await emit("diagram", _generated_payload(item))

    async def started(ks: list[DiagramKind]) -> None:
        for k in ks:
            await emit("diagram_started", {"kind": k.value})

    async def finish_new(
        cid: int,
        title: str,
        *,
        already_saved_user: bool = False,
    ) -> None:
        if not already_saved_user:
            with get_session() as session:
                repo.add_message(session, cid, "user", req.message)
        await emit("conversation", {"id": cid, "title": title})
        await emit(
            "intent",
            {
                "intent": "new_design",
                "instruction": message,
                "target_kinds": [k.value for k in kinds],
            },
        )
        await started(kinds)
        try:
            resp = await _new_flow(
                req.user_id,
                message,
                kinds,
                unknown,
                on_done,
                conversation_id=cid,
                on_design=on_design,
            )
        except Exception as e:
            logger.exception("new_flow failed for conversation %s", cid)
            with get_session() as session:
                repo.add_message(
                    session,
                    cid,
                    "assistant",
                    "Generation failed. Please try again.",
                    intent="error",
                )
            await emit("error", {"message": str(e)})
            await emit("done", {"conversation_id": cid, "version_id": None})
            return
        summary = f"Generated {len(resp.diagrams)} diagrams"
        with get_session() as session:
            repo.add_message(
                session,
                cid,
                "assistant",
                summary,
                intent="new_design",
                version_id=resp.version_id,
            )
            version_payload = repo.version_out(session, resp.version_id)
        await emit("version", version_payload.model_dump(mode="json"))
        await emit(
            "done",
            {"conversation_id": cid, "version_id": resp.version_id},
        )

    # --- First message / no conversation ---
    if req.conversation_id is None:
        with get_session() as session:
            conv = repo.create_conversation(
                session, req.user_id, message[:60], base_prompt=message
            )
            cid = conv.id
            title = conv.title
            repo.add_message(session, cid, "user", req.message)  # type: ignore[arg-type]
        await finish_new(cid, title, already_saved_user=True)  # type: ignore[arg-type]
        return

    # --- Existing conversation ---
    cid = req.conversation_id
    with get_session() as session:
        conv = repo.get_conversation(session, cid)
        if conv is None:
            await emit("error", {"message": f"Conversation {cid} not found"})
            await emit("done", {"conversation_id": cid, "version_id": None})
            return
        if conv.user_id != req.user_id:
            await emit("error", {"message": "Conversation not owned by this user"})
            await emit("done", {"conversation_id": cid, "version_id": None})
            return
        latest = repo.latest_version(session, cid)
        title = conv.title
        if latest is None:
            # Prior generation never produced a version — recover as new design.
            base_prompt = conv.base_prompt or message
            if not conv.base_prompt:
                conv.base_prompt = base_prompt
                session.add(conv)
                session.commit()
            recover = True
            prev_kinds_raw: list[str] = []
            revisions: list[str] = []
            design = None
            latest_prompt = base_prompt
            diagrams_for_q: list[tuple[str, str]] = []
        else:
            recover = False
            base_prompt = conv.base_prompt
            if not base_prompt:
                v1 = repo.list_versions(session, cid)
                base_prompt = v1[0].prompt if v1 else latest.prompt
                conv.base_prompt = base_prompt
                session.add(conv)
                session.commit()
            prev_kinds_raw = list(latest.diagram_types or [])
            revisions = list(latest.revisions or [])
            design = _load_design(latest.design_model)
            latest_prompt = latest.prompt
            latest_id = latest.id
            diagrams_for_q = [
                (d.kind, d.plantuml)
                for d in repo.list_diagrams(session, latest_id)  # type: ignore[arg-type]
            ]

    if recover:
        await finish_new(cid, title)
        return

    # Classify before persisting the user message so new_design does not
    # leave an orphan message on the old conversation.
    intent, intent_recorder = await classify_followup(
        message, latest_prompt, prev_kinds_raw, design
    )
    if intent_recorder:
        with get_session() as session:
            _save_recorder(session, intent_recorder)

    if intent.intent == "new_design":
        with get_session() as session:
            conv = repo.create_conversation(
                session, req.user_id, message[:60], base_prompt=message
            )
            new_cid = conv.id
            title = conv.title
            repo.add_message(session, new_cid, "user", req.message)  # type: ignore[arg-type]
        await finish_new(new_cid, title, already_saved_user=True)  # type: ignore[arg-type]
        return

    with get_session() as session:
        repo.add_message(session, cid, "user", req.message)

    await emit("conversation", {"id": cid, "title": title})
    await emit(
        "intent",
        {
            "intent": intent.intent,
            "instruction": intent.instruction,
            "target_kinds": intent.target_kinds,
        },
    )

    if intent.intent == "question":
        answer = await answer_question(
            intent.instruction or message, design, diagrams_for_q
        )
        await emit("answer", {"content": answer})
        with get_session() as session:
            repo.add_message(
                session, cid, "assistant", answer, intent="question", version_id=None
            )
        await emit("done", {"conversation_id": cid, "version_id": None})
        return

    prev_kinds, _ = normalize_types(prev_kinds_raw)
    targets, _ = normalize_types(intent.target_kinds)
    target_set = set(targets)
    mode: Literal["revise", "edit", "add", "remove"] = "revise"
    out_kinds = prev_kinds
    out_revisions = revisions
    out_prompt = latest_prompt

    if intent.intent == "revise":
        out_revisions = revisions + [intent.instruction]
        out_prompt = compose_prompt(base_prompt, out_revisions)
        mode = "revise"
        out_kinds = prev_kinds
    elif intent.intent == "edit_diagrams":
        out_revisions = revisions + [intent.instruction]
        out_prompt = compose_prompt(base_prompt, out_revisions)
        mode = "edit"
        out_kinds = prev_kinds
    elif intent.intent == "add_diagrams":
        mode = "add"
        out_kinds = list(prev_kinds)
        for t in targets:
            if t not in out_kinds:
                out_kinds.append(t)
        out_prompt = latest_prompt
        out_revisions = revisions
    elif intent.intent == "remove_diagrams":
        mode = "remove"
        out_kinds = [k for k in prev_kinds if k not in target_set]
        out_prompt = latest_prompt
        out_revisions = revisions

    if not out_kinds:
        await emit("error", {"message": "At least one diagram type is required"})
        await emit("done", {"conversation_id": cid, "version_id": None})
        return

    await started(out_kinds)
    resp = await _update_flow(
        req.user_id,
        cid,
        out_prompt,
        out_kinds,
        unknown,
        on_done,
        mode=mode,
        instruction=intent.instruction,
        revisions=out_revisions,
        target_kinds=target_set,
        on_design=on_design,
    )
    summary = resp.change_summary or f"Updated ({intent.intent})"
    with get_session() as session:
        repo.add_message(
            session,
            cid,
            "assistant",
            summary,
            intent=intent.intent,
            version_id=resp.version_id,
        )
        version_payload = repo.version_out(session, resp.version_id)
    await emit("version", version_payload.model_dump(mode="json"))
    await emit(
        "done",
        {"conversation_id": cid, "version_id": resp.version_id},
    )
