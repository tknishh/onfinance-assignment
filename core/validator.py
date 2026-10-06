from __future__ import annotations

import re
from typing import Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from core.config import get_settings
from core.design_model import missing_names, render_design_context
from core.diagram_types import DiagramSpec
from core.llm import invoke_structured
from core.prompts import system_repair, user_consistency_repair, user_repair
from core.renderer import render_svg
from core.schemas import DesignModel, DiagramOut
from core.tracing import TrajectoryRecorder


def sanitize(code: str) -> str:
    """Strip fences, ensure @startuml/@enduml, normalize newlines."""
    text = code.replace("\r\n", "\n").replace("\r", "\n").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:plantuml|puml|uml)?\s*\n?", "", text, flags=re.I)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    # Drop leading prose before @startuml
    idx = text.lower().find("@startuml")
    if idx > 0:
        text = text[idx:]
    elif idx < 0:
        text = f"@startuml\n{text}"

    if not text.lower().rstrip().endswith("@enduml"):
        # trim trailing prose after last @enduml if present mid-text
        end_idx = text.lower().rfind("@enduml")
        if end_idx >= 0:
            text = text[: end_idx + len("@enduml")]
        else:
            text = text.rstrip() + "\n@enduml"

    return text.strip() + "\n"


def _balanced_braces(code: str) -> bool:
    depth = 0
    for ch in code:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _sequence_fragments_ok(code: str) -> bool:
    """Basic alt/loop/opt ... end balance for sequence diagrams."""
    opens = len(re.findall(r"^\s*(alt|loop|opt|par|group|critical|break)\b", code, re.M | re.I))
    ends = len(re.findall(r"^\s*end\b", code, re.M | re.I))
    # else doesn't need matching; allow slight imbalance for nested cases
    return ends >= opens or opens == 0


def structural_check(code: str, spec: DiagramSpec) -> Optional[str]:
    """Returns error message or None."""
    lower = code.lower()
    if "@startuml" not in lower:
        return "Missing @startuml"
    if "@enduml" not in lower:
        return "Missing @enduml"
    if not any(re.search(tok, code, re.I | re.M) for tok in spec.required_tokens):
        return (
            f"Missing required tokens for {spec.kind.value}: "
            f"{', '.join(spec.required_tokens)}"
        )
    if not _balanced_braces(code):
        return "Unbalanced { } braces"
    if spec.kind.value == "sequence" and not _sequence_fragments_ok(code):
        return "Unbalanced alt/loop/opt ... end fragments"
    return None


async def compile_check(code: str) -> Tuple[bool, Optional[str], Optional[str]]:
    return await render_svg(code)


async def validate_and_repair(
    code: str,
    spec: DiagramSpec,
    recorder: TrajectoryRecorder,
) -> Tuple[str, bool, Optional[str], Optional[str], int]:
    """
    Returns (code, is_valid, svg, error, attempts).
    attempts counts LLM generation + repairs (1 = first try ok).
    """
    settings = get_settings()
    last_err: Optional[str] = "Unknown validation error"
    attempts = 0
    max_rounds = settings.max_repair_attempts + 1

    for round_i in range(max_rounds):
        attempts = round_i + 1
        code = sanitize(code)
        err = structural_check(code, spec)
        if err is None:
            ok, svg, compile_err = await compile_check(code)
            if ok:
                return code, True, svg, None, attempts
            last_err = compile_err or "Kroki compile failed"
        else:
            last_err = err

        if round_i >= settings.max_repair_attempts:
            break

        msgs = [
            SystemMessage(content=system_repair()),
            HumanMessage(content=user_repair(code, last_err or "", spec)),
        ]
        try:
            out = await invoke_structured("fast", DiagramOut, msgs, recorder)
            code = out.plantuml
        except Exception as e:
            last_err = f"Repair failed: {e}"
            break

    return code, False, None, last_err, attempts


async def enforce_consistency(
    code: str,
    svg: Optional[str],
    spec: DiagramSpec,
    model: Optional[DesignModel],
    recorder: TrajectoryRecorder,
) -> Tuple[str, Optional[str], list[str]]:
    """
    For a diagram that already compiles, add any shared-model elements it left out.
    One repair attempt; if the repaired code doesn't compile, the original is kept.
    Returns (code, svg, still_missing).
    """
    missing = missing_names(code, model, spec.kind)
    if not missing:
        return code, svg, []

    context = render_design_context(model, spec.kind)
    msgs = [
        SystemMessage(content=system_repair()),
        HumanMessage(content=user_consistency_repair(code, missing, spec, context)),
    ]
    try:
        out = await invoke_structured("fast", DiagramOut, msgs, recorder)
    except Exception:
        return code, svg, missing

    candidate = sanitize(out.plantuml)
    if structural_check(candidate, spec) is not None:
        return code, svg, missing
    ok, new_svg, _ = await compile_check(candidate)
    if not ok:
        return code, svg, missing

    still_missing = missing_names(candidate, model, spec.kind)
    if len(still_missing) >= len(missing):
        return code, svg, missing
    return candidate, new_svg, still_missing
