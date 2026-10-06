from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core.cache import prompt_hash
from core.config import get_settings
from core.design_model import render_design_context
from core.diagram_types import DiagramKind, normalize_types
from core.llm import _get_sem, get_chat, invoke_structured
from core.prompts import (
    system_answer,
    system_intent,
    user_answer,
    user_intent,
)
from core.schemas import DesignModel, FollowUpIntent
from core.tracing import TrajectoryRecorder


def compose_prompt(base: str, revisions: list[str]) -> str:
    if not revisions:
        return base
    numbered = "\n".join(f"{i}. {r}" for i, r in enumerate(revisions, 1))
    return f"{base}\n\nRevisions (apply all, later ones win):\n{numbered}"


def design_summary(model: Optional[DesignModel]) -> str:
    if model is None:
        return ""
    layers: dict[str, list[str]] = {}
    for c in model.components:
        layers.setdefault(c.layer or "Core", []).append(c.name)
    comps = "; ".join(
        f"{layer}: {', '.join(names)}" for layer, names in layers.items()
    )
    stores = ", ".join(d.name for d in model.data_stores) or "none"
    actors = ", ".join(a.name for a in model.actors) or "none"
    return (
        f"{model.system_name}. Actors: {actors}. "
        f"Components by layer: {comps or 'none'}. Data stores: {stores}."
    )


async def classify_followup(
    message: str,
    current_prompt: str,
    current_kinds: list[str],
    design: Optional[DesignModel],
) -> FollowUpIntent:
    settings = get_settings()
    recorder = TrajectoryRecorder(
        "intent",
        settings.fast_model,
        prompt_hash("intent", message, current_prompt),
    )
    msgs = [
        SystemMessage(content=system_intent()),
        HumanMessage(
            content=user_intent(
                message, current_prompt, current_kinds, design_summary(design)
            )
        ),
    ]
    try:
        intent = await invoke_structured("fast", FollowUpIntent, msgs, recorder)
    except Exception:
        return FollowUpIntent(intent="revise", instruction=message, target_kinds=[])

    kinds, _ = normalize_types(intent.target_kinds)
    target = [k.value for k in kinds]
    intent.target_kinds = target
    present = set(current_kinds)

    if intent.intent in ("edit_diagrams", "add_diagrams", "remove_diagrams") and not target:
        intent.intent = "revise"
        return intent

    if intent.intent == "add_diagrams":
        intent.target_kinds = [k for k in target if k not in present]
        if not intent.target_kinds:
            intent.intent = "revise"
    elif intent.intent == "remove_diagrams":
        intent.target_kinds = [k for k in target if k in present]
        if not intent.target_kinds:
            intent.intent = "revise"
        elif set(intent.target_kinds) >= present:
            intent.intent = "revise"
            intent.target_kinds = []

    # Attach recorder for orchestrator to save (via attribute)
    intent._recorder = recorder  # type: ignore[attr-defined]
    return intent


async def answer_question(
    question: str,
    design: Optional[DesignModel],
    diagrams: list[tuple[str, str]],
) -> str:
    context = (
        render_design_context(design, DiagramKind.COMPONENT) if design else ""
    )
    msgs = [
        SystemMessage(content=system_answer()),
        HumanMessage(content=user_answer(question, context, diagrams)),
    ]
    try:
        chat = get_chat("gen")
        async with _get_sem():
            resp = await chat.ainvoke(msgs)
        content = resp.content
        return content if isinstance(content, str) else str(content)
    except Exception:
        return "Sorry, I couldn't answer that right now. Please try again."
