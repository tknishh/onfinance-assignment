from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.db import init_db
from core.diagram_types import DiagramKind
from core.generator import GeneratedDiagram
from core.orchestrator import handle_generate
from core.schemas import (
    Component,
    DataStore,
    DesignModel,
    DomainEntity,
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
        main_flow=[Interaction(step=1, source="Payment Portal", target="Payment Service", message="pay")],
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
    # every diagram call received the same shared model
    assert all(call.args[2] is design for call in gen.call_args_list)


def test_update_reuses_when_diff_and_model_slice_unchanged():
    first, _ = _first_version("user-test-2", _design())
    diff = PromptDiff(summary="Added refunds", affected_kinds=["sequence"], unaffected_kinds=["component"])
    # only entities changed, so the component slice of the model is identical
    second, _ = _second_version(first, "user-test-2", _design(extra_entity=True), diff)
    assert second.version_no == 2
    reused = {d.kind for d in second.diagrams if d.reused}
    assert reused == {"component"}


def test_update_regenerates_when_model_slice_changes():
    first, _ = _first_version("user-test-3", _design())
    diff = PromptDiff(summary="Added alerts", affected_kinds=["sequence"], unaffected_kinds=["component"])
    # a new component changes the component slice even though the diff said unaffected
    second, upd = _second_version(first, "user-test-3", _design(extra_component=True), diff)
    assert not any(d.reused for d in second.diagrams)
    assert {call.args[2].kind for call in upd.call_args_list} == {"sequence", "component"}
