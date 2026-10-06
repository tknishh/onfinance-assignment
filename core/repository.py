from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from core.models import (
    Conversation,
    DesignVersion,
    Diagram,
    Feedback,
    Message,
    Trajectory,
    User,
)
from core.schemas import (
    ConversationOut,
    DesignModel,
    DiagramResult,
    FeedbackRequest,
    MessageOut,
    TimelineOut,
    VersionOut,
)


def get_or_create_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def create_conversation(
    session: Session,
    user_id: str,
    title: str,
    base_prompt: Optional[str] = None,
) -> Conversation:
    conv = Conversation(
        user_id=user_id,
        title=title[:60] or "Untitled design",
        base_prompt=base_prompt,
    )
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return conv


def get_conversation(session: Session, conversation_id: int) -> Optional[Conversation]:
    return session.get(Conversation, conversation_id)


def list_conversations(session: Session, user_id: str) -> list[Conversation]:
    return list(
        session.exec(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(col(Conversation.created_at).desc())
        ).all()
    )


def user_has_conversations(session: Session, user_id: str) -> bool:
    return session.exec(
        select(Conversation).where(Conversation.user_id == user_id).limit(1)
    ).first() is not None


def next_version_no(session: Session, conversation_id: int) -> int:
    latest = latest_version(session, conversation_id)
    return (latest.version_no + 1) if latest else 1


def create_version(
    session: Session,
    conversation_id: int,
    prompt: str,
    diagram_types: list[str],
    parent_version_id: Optional[int] = None,
    change_summary: Optional[str] = None,
    design_model: Optional[dict] = None,
    revisions: Optional[list[str]] = None,
    instruction: Optional[str] = None,
    version_no: Optional[int] = None,
) -> DesignVersion:
    """Allocate the next version_no with retries on unique-constraint races."""
    last_err: Optional[Exception] = None
    for _ in range(5):
        no = version_no if version_no is not None else next_version_no(session, conversation_id)
        version_no = None  # re-allocate on retry
        version = DesignVersion(
            conversation_id=conversation_id,
            version_no=no,
            prompt=prompt,
            diagram_types=diagram_types,
            parent_version_id=parent_version_id,
            change_summary=change_summary,
            design_model=design_model,
            revisions=list(revisions or []),
            instruction=instruction,
        )
        session.add(version)
        try:
            session.commit()
            session.refresh(version)
            return version
        except IntegrityError as e:
            session.rollback()
            last_err = e
    raise RuntimeError(
        f"Could not allocate version for conversation {conversation_id}"
    ) from last_err


def latest_version(
    session: Session, conversation_id: int
) -> Optional[DesignVersion]:
    return session.exec(
        select(DesignVersion)
        .where(DesignVersion.conversation_id == conversation_id)
        .order_by(col(DesignVersion.version_no).desc())
    ).first()


def get_version(session: Session, version_id: int) -> Optional[DesignVersion]:
    return session.get(DesignVersion, version_id)


def list_versions(session: Session, conversation_id: int) -> list[DesignVersion]:
    return list(
        session.exec(
            select(DesignVersion)
            .where(DesignVersion.conversation_id == conversation_id)
            .order_by(col(DesignVersion.version_no).asc())
        ).all()
    )


def save_diagram(session: Session, diagram: Diagram) -> Diagram:
    session.add(diagram)
    session.commit()
    session.refresh(diagram)
    return diagram


def get_diagram(session: Session, diagram_id: int) -> Optional[Diagram]:
    return session.get(Diagram, diagram_id)


def list_diagrams(session: Session, version_id: int) -> list[Diagram]:
    return list(
        session.exec(
            select(Diagram).where(Diagram.version_id == version_id)
        ).all()
    )


def diagrams_by_kind(
    session: Session, version_id: int
) -> dict[str, Diagram]:
    return {d.kind: d for d in list_diagrams(session, version_id)}


def add_feedback(session: Session, req: FeedbackRequest) -> Feedback:
    fb = Feedback(
        user_id=req.user_id,
        version_id=req.version_id,
        diagram_id=req.diagram_id,
        rating=req.rating,
        comment=req.comment,
    )
    session.add(fb)
    session.commit()
    session.refresh(fb)
    return fb


def save_trajectory(session: Session, trajectory: Trajectory) -> Trajectory:
    session.add(trajectory)
    session.commit()
    session.refresh(trajectory)
    return trajectory


def save_trajectories(session: Session, rows: list[Trajectory]) -> None:
    for row in rows:
        session.add(row)
    session.commit()


def trajectories_for_diagram(
    session: Session, diagram_id: int
) -> list[Trajectory]:
    return list(
        session.exec(
            select(Trajectory).where(Trajectory.diagram_id == diagram_id)
        ).all()
    )


def trajectories_for_version(
    session: Session, version_id: int
) -> list[Trajectory]:
    diagrams = list_diagrams(session, version_id)
    ids = [d.id for d in diagrams if d.id is not None]
    if not ids:
        return []
    return list(
        session.exec(select(Trajectory).where(col(Trajectory.diagram_id).in_(ids))).all()
    )


def exportable_trajectories(session: Session) -> list[Trajectory]:
    rows = session.exec(
        select(Trajectory).where(Trajectory.used_in_training == False)  # noqa: E712
    ).all()
    return [
        t
        for t in rows
        if t.task in ("generate", "update") and t.reward is not None
    ]


def add_message(
    session: Session,
    conversation_id: int,
    role: str,
    content: str,
    intent: Optional[str] = None,
    version_id: Optional[int] = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        intent=intent,
        version_id=version_id,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


def list_messages(session: Session, conversation_id: int) -> list[Message]:
    return list(
        session.exec(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(col(Message.created_at).asc(), col(Message.id).asc())
        ).all()
    )


def conversation_owned_by(
    session: Session, conversation_id: int, user_id: str
) -> Optional[Conversation]:
    conv = get_conversation(session, conversation_id)
    if conv is None or conv.user_id != user_id:
        return None
    return conv


def version_owned_by(
    session: Session, version_id: int, user_id: str
) -> Optional[DesignVersion]:
    version = get_version(session, version_id)
    if version is None:
        return None
    if conversation_owned_by(session, version.conversation_id, user_id) is None:
        return None
    return version


def diagram_owned_by(
    session: Session, diagram_id: int, user_id: str
) -> Optional[Diagram]:
    diagram = get_diagram(session, diagram_id)
    if diagram is None:
        return None
    if version_owned_by(session, diagram.version_id, user_id) is None:
        return None
    return diagram


def delete_conversation(session: Session, conversation_id: int) -> None:
    versions = list_versions(session, conversation_id)
    for v in versions:
        diagrams = list_diagrams(session, v.id)  # type: ignore[arg-type]
        for d in diagrams:
            for t in trajectories_for_diagram(session, d.id):  # type: ignore[arg-type]
                session.delete(t)
            fbs = session.exec(
                select(Feedback).where(Feedback.diagram_id == d.id)
            ).all()
            for fb in fbs:
                session.delete(fb)
            session.delete(d)
        fbs_v = session.exec(
            select(Feedback).where(Feedback.version_id == v.id)
        ).all()
        for fb in fbs_v:
            session.delete(fb)
        session.delete(v)
    for msg in list_messages(session, conversation_id):
        session.delete(msg)
    conv = get_conversation(session, conversation_id)
    if conv is not None:
        session.delete(conv)
    session.commit()


def _diagram_result(d: Diagram) -> DiagramResult:
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
        reused=d.reused_from_id is not None,
        warnings=list(d.warnings or []),
        version_id=d.version_id,
    )


def conversation_out(session: Session, conv: Conversation) -> ConversationOut:
    latest = latest_version(session, conv.id)  # type: ignore[arg-type]
    return ConversationOut(
        id=conv.id or 0,
        title=conv.title,
        base_prompt=conv.base_prompt,
        latest_version_no=latest.version_no if latest else None,
        created_at=conv.created_at,
    )


def version_out(session: Session, version_id: int) -> VersionOut:
    v = get_version(session, version_id)
    if v is None:
        raise ValueError(f"Version {version_id} not found")
    design = None
    if v.design_model:
        try:
            design = DesignModel.model_validate(v.design_model)
        except Exception:
            design = None
    diagrams = [_diagram_result(d) for d in list_diagrams(session, version_id)]
    return VersionOut(
        id=v.id or 0,
        version_no=v.version_no,
        prompt=v.prompt,
        revisions=list(v.revisions or []),
        instruction=v.instruction,
        change_summary=v.change_summary,
        diagram_types=list(v.diagram_types or []),
        design_model=design,
        diagrams=diagrams,
        created_at=v.created_at,
    )


def timeline(session: Session, conversation_id: int) -> TimelineOut:
    conv = get_conversation(session, conversation_id)
    if conv is None:
        raise ValueError(f"Conversation {conversation_id} not found")
    messages = [
        MessageOut(
            id=m.id or 0,
            role=m.role,
            content=m.content,
            intent=m.intent,
            version_id=m.version_id,
            created_at=m.created_at,
        )
        for m in list_messages(session, conversation_id)
    ]
    versions = [version_out(session, v.id) for v in list_versions(session, conversation_id) if v.id]
    return TimelineOut(
        conversation=conversation_out(session, conv),
        messages=messages,
        versions=versions,
    )
