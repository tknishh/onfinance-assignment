from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=10, max_length=20_000)
    diagram_types: list[str] = Field(min_length=1, max_length=20)
    user_id: Optional[str] = Field(default=None, max_length=128)
    conversation_id: Optional[int] = None


class DiagramOut(BaseModel):
    title: str
    plantuml: str
    notes: Optional[str] = None


class PromptDiff(BaseModel):
    summary: str
    affected_kinds: list[str]
    unaffected_kinds: list[str]


class Actor(BaseModel):
    name: str
    description: str = ""


class Component(BaseModel):
    name: str
    layer: str
    responsibility: str = ""


class DataStore(BaseModel):
    name: str
    technology: str = ""
    holds: str = ""


class ExternalSystem(BaseModel):
    name: str
    description: str = ""


class DomainEntity(BaseModel):
    name: str
    attributes: list[str] = Field(default_factory=list)
    related_to: list[str] = Field(default_factory=list)


class Interaction(BaseModel):
    step: int
    source: str
    target: str
    message: str
    reply: Optional[str] = None


class DeploymentNode(BaseModel):
    name: str
    node_type: str = "node"
    hosts: list[str] = Field(default_factory=list)


class DesignModel(BaseModel):
    """Canonical architecture shared by every diagram of one design version."""

    system_name: str
    summary: str = ""
    actors: list[Actor] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    data_stores: list[DataStore] = Field(default_factory=list)
    external_systems: list[ExternalSystem] = Field(default_factory=list)
    entities: list[DomainEntity] = Field(default_factory=list)
    main_flow: list[Interaction] = Field(default_factory=list)
    deployment: list[DeploymentNode] = Field(default_factory=list)
    lifecycle_entity: str = ""
    lifecycle_states: list[str] = Field(default_factory=list)


class DiagramResult(BaseModel):
    diagram_id: int
    kind: str
    title: str
    plantuml: str
    svg: Optional[str]
    is_valid: bool
    error: Optional[str]
    attempts: int
    latency_ms: int
    reused: bool
    warnings: list[str] = Field(default_factory=list)
    version_id: Optional[int] = None


class GenerateResponse(BaseModel):
    user_id: str
    conversation_id: int
    version_id: int
    version_no: int
    change_summary: Optional[str]
    unknown_types: list[str]
    diagrams: list[DiagramResult]
    design_model: Optional[DesignModel] = None


class FeedbackRequest(BaseModel):
    user_id: str = Field(max_length=128)
    version_id: int
    diagram_id: Optional[int] = None
    rating: Literal[-1, 1]
    comment: Optional[str] = Field(default=None, max_length=4_000)
    apply_as_update: bool = False


class JudgeScore(BaseModel):
    score: float = Field(ge=0, le=1)
    reason: str


IntentName = Literal[
    "revise",
    "edit_diagrams",
    "add_diagrams",
    "remove_diagrams",
    "question",
    "new_design",
]


class FollowUpIntent(BaseModel):
    intent: IntentName
    instruction: str
    target_kinds: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    user_id: str = Field(max_length=128)
    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: Optional[int] = None
    diagram_types: list[str] = Field(default_factory=list, max_length=20)


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    intent: Optional[str]
    version_id: Optional[int]
    created_at: datetime


class VersionOut(BaseModel):
    id: int
    version_no: int
    prompt: str
    revisions: list[str]
    instruction: Optional[str]
    change_summary: Optional[str]
    diagram_types: list[str]
    design_model: Optional[DesignModel]
    diagrams: list[DiagramResult]
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    title: str
    base_prompt: Optional[str]
    latest_version_no: Optional[int]
    created_at: datetime


class TimelineOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    versions: list[VersionOut]


class RenderRequest(BaseModel):
    plantuml: str = Field(min_length=1, max_length=200_000)
    user_id: str = Field(max_length=128)
