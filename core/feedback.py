from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core import repository as repo
from core.config import get_settings
from core.db import get_session
from core.llm import invoke_structured
from core.models import Feedback
from core.prompts import system_judge, user_judge
from core.schemas import JudgeScore


def compute_reward(
    user_rating: Optional[int],
    syntax_valid: bool,
    attempts: int,
    judge: Optional[float],
    consistent: bool = True,
) -> float:
    syntax = 0.0 if not syntax_valid else (1.0 if attempts == 1 else 0.7 if attempts == 2 else 0.5)
    if not consistent:
        syntax *= 0.5
    parts: list[tuple[float, float]] = [(0.2, syntax)]
    if user_rating is not None:
        parts.append((0.6, (user_rating + 1) / 2))
    if judge is not None:
        parts.append((0.2, judge))
    total_w = sum(w for w, _ in parts)
    return round(sum(w * v for w, v in parts) / total_w, 4)


def apply_reward(fb: Feedback) -> None:
    with get_session() as session:
        if fb.diagram_id is not None:
            diagrams = [repo.get_diagram(session, fb.diagram_id)]
            trajectories = repo.trajectories_for_diagram(session, fb.diagram_id)
        else:
            diagrams = repo.list_diagrams(session, fb.version_id)
            trajectories = repo.trajectories_for_version(session, fb.version_id)

        diagram_map = {d.id: d for d in diagrams if d is not None and d.id is not None}
        for traj in trajectories:
            d = diagram_map.get(traj.diagram_id) if traj.diagram_id else None
            syntax_valid = bool(d.is_valid) if d else bool(traj.metrics.get("syntax_valid"))
            attempts = d.attempts if d else int(traj.metrics.get("attempts", 1))
            judge = traj.metrics.get("judge")
            consistent = not (d.warnings if d else None)
            traj.reward = compute_reward(fb.rating, syntax_valid, attempts, judge, consistent)
            traj.metrics = {
                **(traj.metrics or {}),
                "user_rating": fb.rating,
                "comment": fb.comment,
            }
            session.add(traj)
        session.commit()


async def judge_async(diagram_id: Optional[int]) -> None:
    if diagram_id is None or not get_settings().judge_enabled:
        return
    with get_session() as session:
        diagram = repo.get_diagram(session, diagram_id)
        if diagram is None:
            return
        version = repo.get_version(session, diagram.version_id)
        prompt = version.prompt if version else ""
        trajectories = repo.trajectories_for_diagram(session, diagram_id)

    msgs = [
        SystemMessage(content=system_judge()),
        HumanMessage(
            content=user_judge(prompt, diagram.kind, diagram.plantuml)
        ),
    ]
    try:
        score = await invoke_structured("fast", JudgeScore, msgs, None)
        judge_val = score.score
    except Exception:
        return

    with get_session() as session:
        trajectories = repo.trajectories_for_diagram(session, diagram_id)
        diagram = repo.get_diagram(session, diagram_id)
        for traj in trajectories:
            traj.metrics = {**(traj.metrics or {}), "judge": judge_val}
            user_rating = traj.metrics.get("user_rating")
            syntax_valid = bool(diagram.is_valid) if diagram else False
            attempts = diagram.attempts if diagram else 1
            traj.reward = compute_reward(
                user_rating if isinstance(user_rating, int) else None,
                syntax_valid,
                attempts,
                judge_val,
                not (diagram.warnings if diagram else None),
            )
            session.add(traj)
        session.commit()
