from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core.cache import get_gen_cache, prompt_hash, set_gen_cache
from core.config import get_settings
from core.design_model import model_hash, render_design_context
from core.diagram_types import DiagramKind, get_spec
from core.llm import invoke_structured
from core.models import Diagram
from core.prompts import (
    system_generate,
    system_update,
    user_generate,
    user_update,
)
from core.schemas import DesignModel, DiagramOut
from core.tracing import TrajectoryRecorder
from core.validator import enforce_consistency, validate_and_repair


@dataclass
class GeneratedDiagram:
    kind: DiagramKind
    title: str
    plantuml: str
    svg: Optional[str]
    is_valid: bool
    error: Optional[str]
    attempts: int
    latency_ms: int
    model: str
    reused: bool = False
    reused_from_id: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    recorder: Optional[TrajectoryRecorder] = field(default=None, repr=False)


def _missing_warning(missing: list[str]) -> list[str]:
    return [f"Missing from shared design model: {', '.join(missing)}"] if missing else []


async def _finalize(
    code: str,
    title: str,
    kind: DiagramKind,
    design: Optional[DesignModel],
    recorder: TrajectoryRecorder,
    t0: float,
) -> GeneratedDiagram:
    settings = get_settings()
    spec = get_spec(kind)
    code, ok, svg, err, attempts = await validate_and_repair(code, spec, recorder)
    missing: list[str] = []
    if ok:
        code, svg, missing = await enforce_consistency(code, svg, spec, design, recorder)
    return GeneratedDiagram(
        kind=kind,
        title=title,
        plantuml=code,
        svg=svg,
        is_valid=ok,
        error=err,
        attempts=attempts,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        model=settings.gen_model,
        warnings=_missing_warning(missing),
        recorder=recorder,
    )


async def generate_one(
    prompt: str, kind: DiagramKind, design: Optional[DesignModel] = None
) -> GeneratedDiagram:
    settings = get_settings()
    spec = get_spec(kind)
    cache_key = prompt_hash(settings.gen_model, kind.value, prompt, model_hash(design))
    cached = get_gen_cache(cache_key)
    if cached:
        return GeneratedDiagram(
            kind=kind,
            title=cached["title"],
            plantuml=cached["plantuml"],
            svg=cached.get("svg"),
            is_valid=cached.get("is_valid", False),
            error=cached.get("error"),
            attempts=cached.get("attempts", 1),
            latency_ms=cached.get("latency_ms", 0),
            model=settings.gen_model,
            warnings=cached.get("warnings", []),
        )

    t0 = time.perf_counter()
    recorder = TrajectoryRecorder("generate", settings.gen_model, cache_key)
    msgs = [
        SystemMessage(content=system_generate(spec)),
        HumanMessage(
            content=user_generate(prompt, spec, render_design_context(design, kind))
        ),
    ]
    try:
        out = await invoke_structured("gen", DiagramOut, msgs, recorder)
    except Exception as e:
        return GeneratedDiagram(
            kind=kind,
            title=kind.value,
            plantuml="",
            svg=None,
            is_valid=False,
            error=str(e),
            attempts=1,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=settings.gen_model,
            recorder=recorder,
        )

    result = await _finalize(out.plantuml, out.title or kind.value, kind, design, recorder, t0)
    if result.is_valid:
        set_gen_cache(
            cache_key,
            {
                "title": result.title,
                "plantuml": result.plantuml,
                "svg": result.svg,
                "is_valid": True,
                "error": None,
                "attempts": result.attempts,
                "latency_ms": result.latency_ms,
                "warnings": result.warnings,
            },
        )
    return result


async def update_one(
    new_prompt: str,
    old_prompt: str,
    old: Diagram | object,
    change_summary: str,
    design: Optional[DesignModel] = None,
) -> GeneratedDiagram:
    settings = get_settings()
    kind = DiagramKind(getattr(old, "kind"))
    old_plantuml = getattr(old, "plantuml")
    old_title = getattr(old, "title")
    old_svg = getattr(old, "svg", None)
    spec = get_spec(kind)
    cache_key = prompt_hash(
        settings.gen_model, "update", kind.value, new_prompt, old_plantuml, model_hash(design)
    )
    t0 = time.perf_counter()
    recorder = TrajectoryRecorder("update", settings.gen_model, cache_key)
    msgs = [
        SystemMessage(content=system_update(spec)),
        HumanMessage(
            content=user_update(
                new_prompt,
                old_prompt,
                old_plantuml,
                change_summary,
                render_design_context(design, kind),
            )
        ),
    ]
    try:
        out = await invoke_structured("gen", DiagramOut, msgs, recorder)
    except Exception as e:
        return GeneratedDiagram(
            kind=kind,
            title=old_title,
            plantuml=old_plantuml,
            svg=old_svg,
            is_valid=False,
            error=str(e),
            attempts=1,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=settings.gen_model,
            recorder=recorder,
        )

    return await _finalize(out.plantuml, out.title or old_title, kind, design, recorder, t0)


def reuse_diagram(old: Diagram | object) -> GeneratedDiagram:
    return GeneratedDiagram(
        kind=DiagramKind(getattr(old, "kind")),
        title=getattr(old, "title"),
        plantuml=getattr(old, "plantuml"),
        svg=getattr(old, "svg", None),
        is_valid=bool(getattr(old, "is_valid", False)),
        error=getattr(old, "error", None),
        attempts=int(getattr(old, "attempts", 1)),
        latency_ms=0,
        model=getattr(old, "model", ""),
        reused=True,
        reused_from_id=getattr(old, "id", None),
        warnings=list(getattr(old, "warnings", None) or []),
    )


async def run_parallel(
    tasks: list[Awaitable[GeneratedDiagram]],
    on_done: Optional[Callable[[GeneratedDiagram], None]] = None,
) -> list[GeneratedDiagram]:
    results: list[GeneratedDiagram] = []
    wrapped = [asyncio.create_task(t) for t in tasks]  # type: ignore[arg-type]
    for fut in asyncio.as_completed(wrapped):
        try:
            item = await fut
        except Exception as e:
            item = GeneratedDiagram(
                kind=DiagramKind.SEQUENCE,
                title="error",
                plantuml="",
                svg=None,
                is_valid=False,
                error=str(e),
                attempts=1,
                latency_ms=0,
                model=get_settings().gen_model,
            )
        results.append(item)
        if on_done:
            res = on_done(item)
            if inspect.isawaitable(res):
                await res
    return results
