from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.db import get_session, init_db
from core.diagram_types import DiagramKind
from core.generator import GeneratedDiagram
from core.intent import compose_prompt
from core.orchestrator import handle_chat, handle_generate
from core import repository as repo
from core.schemas import (
    ChatRequest,
    Component,
    DataStore,
    DesignModel,
    DomainEntity,
    FollowUpIntent,
    GenerateRequest,
    Interaction,
    PromptDiff,
)


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    from core.config import get_settings

    get_settings.cache_clear()
    import core.db as dbmod

    dbmod._engine = None
    init_db()
    yield
    get_settings.cache_clear()
    dbmod._engine = None


def _design(extra_component: bool = False, extra_entity: bool = False) -> DesignModel:
    components = [
        Component(name="Payment Portal", layer="Presentation"),
        Component(name="Payment Service", layer="Processing"),
    ]
    if extra_component:
        components.append(Component(name="Fraud Alerter", layer="Integration"))
    entities = [DomainEntity(name="Payment", attributes=["id", "amount"])]
    if extra_entity:
        entities.append(DomainEntity(name="Refund", attributes=["id"]))
    return DesignModel(
        system_name="Payments",
        components=components,
        data_stores=[DataStore(name="Payment DB")],
        entities=entities,
        main_flow=[
            Interaction(
                step=1,
                source="Payment Portal",
                target="Payment Service",
                message="pay",
            )
        ],
    )


def _fake_diagram(kind: DiagramKind) -> GeneratedDiagram:
    return GeneratedDiagram(
        kind=kind,
        title=f"{kind.value} diagram",
        plantuml="@startuml\nA -> B\n@enduml\n",
        svg="<svg/>",
        is_valid=True,
        error=None,
        attempts=1,
        latency_ms=10,
        model="test-model",
    )


async def _fake_gen(prompt, kind, design=None):
    return _fake_diagram(kind)


async def _fake_update(new_prompt, old_prompt, old, change_summary, design=None):
    g = _fake_diagram(DiagramKind(old.kind))
    g.title = "updated"
    return g


def _first_version(user_id: str, design: DesignModel):
    with (
        patch("core.orchestrator.generate_one", side_effect=_fake_gen) as gen,
        patch(
            "core.orchestrator.build_design_model",
            new=AsyncMock(return_value=(design, None)),
        ),
    ):
        resp = asyncio.run(
            handle_generate(
                GenerateRequest(
                    prompt="Design a small payment service with cards and webhooks.",
                    diagram_types=["sequence", "component"],
                    user_id=user_id,
                )
            )
        )
    return resp, gen


def _second_version(first, user_id: str, new_design: DesignModel, diff: PromptDiff):
    with (
        patch("core.orchestrator.generate_one", side_effect=_fake_gen),
        patch("core.orchestrator.update_one", side_effect=_fake_update) as upd,
        patch("core.orchestrator.invoke_structured", new=AsyncMock(return_value=diff)),
        patch(
            "core.orchestrator.update_design_model",
            new=AsyncMock(return_value=(new_design, None)),
        ),
    ):
        resp = asyncio.run(
            handle_generate(
                GenerateRequest(
                    prompt="Design a small payment service with cards and webhooks. Add fraud alerts.",
                    diagram_types=["sequence", "component"],
                    user_id=user_id,
                    conversation_id=first.conversation_id,
                )
            )
        )
    return resp, upd


def test_new_flow_shares_one_design_model():
    design = _design()
    resp, gen = _first_version("user-test-1", design)
    assert resp.version_no == 1
    assert len(resp.diagrams) == 2
    assert resp.design_model == design
    assert all(call.args[2] is design for call in gen.call_args_list)


def test_update_reuses_when_diff_and_model_slice_unchanged():
    first, _ = _first_version("user-test-2", _design())
    diff = PromptDiff(
        summary="Added refunds",
        affected_kinds=["sequence"],
        unaffected_kinds=["component"],
    )
    second, _ = _second_version(first, "user-test-2", _design(extra_entity=True), diff)
    assert second.version_no == 2
    reused = {d.kind for d in second.diagrams if d.reused}
    assert reused == {"component"}


def test_update_regenerates_when_model_slice_changes():
    first, _ = _first_version("user-test-3", _design())
    diff = PromptDiff(
        summary="Added alerts",
        affected_kinds=["sequence"],
        unaffected_kinds=["component"],
    )
    second, upd = _second_version(
        first, "user-test-3", _design(extra_component=True), diff
    )
    assert not any(d.reused for d in second.diagrams)
    assert {call.args[2].kind for call in upd.call_args_list} == {
        "sequence",
        "component",
    }


async def _collect_events(req: ChatRequest):
    events = []

    async def emit(event, data):
        events.append((event, data))

    await handle_chat(req, emit)
    return events


def test_handle_chat_recovers_when_no_versions():
    """A conversation with a user message but no versions can still generate."""
    design = _design()
    with get_session() as session:
        repo.get_or_create_user(session, "chat-recover")
        conv = repo.create_conversation(
            session, "chat-recover", "broken first try", base_prompt="broken first try"
        )
        cid = conv.id
        repo.add_message(session, cid, "user", "broken first try")  # type: ignore[arg-type]

    with (
        patch("core.orchestrator.generate_one", side_effect=_fake_gen),
        patch(
            "core.orchestrator.build_design_model",
            new=AsyncMock(return_value=(design, None)),
        ),
    ):
        events = asyncio.run(
            _collect_events(
                ChatRequest(
                    user_id="chat-recover",
                    message="Design a small payment service with cards and webhooks.",
                    conversation_id=cid,
                    diagram_types=["sequence", "component"],
                )
            )
        )
    assert events[-1][0] == "done"
    assert events[-1][1]["version_id"] is not None
    with get_session() as session:
        assert repo.latest_version(session, cid) is not None


def test_handle_chat_first_message():
    design = _design()
    with (
        patch("core.orchestrator.generate_one", side_effect=_fake_gen),
        patch(
            "core.orchestrator.build_design_model",
            new=AsyncMock(return_value=(design, None)),
        ),
    ):
        events = asyncio.run(
            _collect_events(
                ChatRequest(
                    user_id="chat-1",
                    message="Design a small payment service with cards and webhooks.",
                    diagram_types=["sequence", "component"],
                )
            )
        )
    names = [e[0] for e in events]
    assert names[0] == "conversation"
    assert names[1] == "intent"
    assert "design_model" in names
    assert names.count("diagram_started") == 2
    assert names.count("diagram") == 2
    assert "version" in names
    assert names[-1] == "done"
    cid = events[0][1]["id"]
    with get_session() as session:
        msgs = repo.list_messages(session, cid)
        assert any(m.role == "user" for m in msgs)
        assert any(m.role == "assistant" for m in msgs)


def test_handle_chat_question():
    design = _design()
    first, _ = _first_version("chat-q", design)
    intent = FollowUpIntent(
        intent="question", instruction="why payment portal?", target_kinds=[]
    )
    with (
        patch(
            "core.orchestrator.classify_followup",
            new=AsyncMock(return_value=(intent, None)),
        ),
        patch(
            "core.orchestrator.answer_question",
            new=AsyncMock(return_value="Because users need a UI."),
        ),
    ):
        events = asyncio.run(
            _collect_events(
                ChatRequest(
                    user_id="chat-q",
                    message="why is there a payment portal?",
                    conversation_id=first.conversation_id,
                )
            )
        )
    names = [e[0] for e in events]
    assert "answer" in names
    assert names[-1] == "done"
    done = events[-1][1]
    assert done["version_id"] is None
    with get_session() as session:
        versions = repo.list_versions(session, first.conversation_id)
        assert len(versions) == 1


def test_handle_chat_add_diagrams():
    design = _design()
    first, _ = _first_version("chat-add", design)
    intent = FollowUpIntent(
        intent="add_diagrams",
        instruction="add deployment",
        target_kinds=["deployment"],
    )
    with (
        patch(
            "core.orchestrator.classify_followup",
            new=AsyncMock(return_value=(intent, None)),
        ),
        patch("core.orchestrator.generate_one", side_effect=_fake_gen) as gen,
        patch("core.orchestrator.update_one", side_effect=_fake_update),
    ):
        events = asyncio.run(
            _collect_events(
                ChatRequest(
                    user_id="chat-add",
                    message="also add a deployment diagram",
                    conversation_id=first.conversation_id,
                )
            )
        )
    assert events[-1][0] == "done"
    gen_kinds = {call.args[1] for call in gen.call_args_list}
    assert gen_kinds == {DiagramKind.DEPLOYMENT}
    version = next(e[1] for e in events if e[0] == "version")
    assert len(version["diagrams"]) == 3
    assert sum(1 for d in version["diagrams"] if d["reused"]) == 2


def test_handle_chat_remove_diagrams():
    design = _design()
    first, _ = _first_version("chat-rm", design)
    intent = FollowUpIntent(
        intent="remove_diagrams",
        instruction="remove component",
        target_kinds=["component"],
    )
    with (
        patch(
            "core.orchestrator.classify_followup",
            new=AsyncMock(return_value=(intent, None)),
        ),
        patch("core.orchestrator.generate_one", side_effect=_fake_gen) as gen,
        patch("core.orchestrator.update_one", side_effect=_fake_update) as upd,
    ):
        events = asyncio.run(
            _collect_events(
                ChatRequest(
                    user_id="chat-rm",
                    message="drop the component diagram",
                    conversation_id=first.conversation_id,
                )
            )
        )
    assert gen.call_count == 0
    assert upd.call_count == 0
    version = next(e[1] for e in events if e[0] == "version")
    assert len(version["diagrams"]) == 1
    assert version["diagrams"][0]["kind"] == "sequence"


def test_handle_chat_revise_stores_revisions():
    design = _design()
    first, _ = _first_version("chat-rev", design)
    intent = FollowUpIntent(
        intent="revise",
        instruction="add Slack alerts for fraud",
        target_kinds=[],
    )
    with (
        patch(
            "core.orchestrator.classify_followup",
            new=AsyncMock(return_value=(intent, None)),
        ),
        patch("core.orchestrator.generate_one", side_effect=_fake_gen),
        patch("core.orchestrator.update_one", side_effect=_fake_update),
        patch(
            "core.orchestrator.invoke_structured",
            new=AsyncMock(
                return_value=PromptDiff(
                    summary="alerts",
                    affected_kinds=["sequence", "component"],
                    unaffected_kinds=[],
                )
            ),
        ),
        patch(
            "core.orchestrator.update_design_model",
            new=AsyncMock(return_value=(design, None)),
        ),
    ):
        events = asyncio.run(
            _collect_events(
                ChatRequest(
                    user_id="chat-rev",
                    message="add Slack alerts for fraud",
                    conversation_id=first.conversation_id,
                )
            )
        )
    version = next(e[1] for e in events if e[0] == "version")
    assert version["revisions"] == ["add Slack alerts for fraud"]
    with get_session() as session:
        conv = repo.get_conversation(session, first.conversation_id)
        base = conv.base_prompt or first.diagrams[0].plantuml  # fallback unused
        v = repo.get_version(session, version["id"])
        assert v is not None
        assert v.prompt == compose_prompt(
            conv.base_prompt or "Design a small payment service with cards and webhooks.",
            ["add Slack alerts for fraud"],
        )
