from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    title: str
    base_prompt: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class DesignVersion(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "version_no", name="uq_designversion_conv_verno"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    version_no: int
    prompt: str
    diagram_types: list[str] = Field(sa_column=Column(JSON))
    parent_version_id: Optional[int] = Field(
        default=None, foreign_key="designversion.id"
    )
    change_summary: Optional[str] = None
    design_model: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    revisions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    instruction: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Diagram(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    version_id: int = Field(foreign_key="designversion.id", index=True)
    kind: str
    title: str
    plantuml: str
    svg: Optional[str] = None
    is_valid: bool = False
    error: Optional[str] = None
    attempts: int = 1
    latency_ms: int = 0
    model: str
    reused_from_id: Optional[int] = None
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id")
    version_id: int = Field(foreign_key="designversion.id")
    diagram_id: Optional[int] = Field(default=None, foreign_key="diagram.id")
    rating: int
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Trajectory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    diagram_id: Optional[int] = Field(default=None, foreign_key="diagram.id", index=True)
    task: str
    prompt_hash: str = Field(index=True)
    model: str
    messages: list[dict[str, Any]] = Field(sa_column=Column(JSON))
    metrics: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    reward: Optional[float] = None
    used_in_training: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str
    content: str
    intent: Optional[str] = None
    version_id: Optional[int] = Field(default=None, foreign_key="designversion.id")
    created_at: datetime = Field(default_factory=utcnow)
