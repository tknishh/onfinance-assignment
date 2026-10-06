from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from core.intent import classify_followup, compose_prompt
from core.schemas import FollowUpIntent


def test_compose_prompt_empty():
    assert compose_prompt("base", []) == "base"


def test_compose_prompt_numbered():
    out = compose_prompt("base", ["add alerts", "rename parser"])
    assert out.startswith("base")
    assert "1. add alerts" in out
    assert "2. rename parser" in out


def test_edit_empty_targets_becomes_revise():
    raw = FollowUpIntent(intent="edit_diagrams", instruction="fix something", target_kinds=[])
    with patch("core.intent.invoke_structured", new=AsyncMock(return_value=raw)):
        result, recorder = asyncio.run(
            classify_followup("fix something", "prompt", ["sequence"], None)
        )
    assert result.intent == "revise"
    assert recorder is not None


def test_add_drops_existing_kinds():
    raw = FollowUpIntent(
        intent="add_diagrams",
        instruction="add deployment",
        target_kinds=["sequence", "deployment"],
    )
    with patch("core.intent.invoke_structured", new=AsyncMock(return_value=raw)):
        result, _ = asyncio.run(
            classify_followup("add deployment", "prompt", ["sequence"], None)
        )
    assert result.intent == "add_diagrams"
    assert result.target_kinds == ["deployment"]


def test_classify_exception_defaults_to_revise():
    with patch(
        "core.intent.invoke_structured",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result, recorder = asyncio.run(
            classify_followup("please update", "prompt", ["sequence"], None)
        )
    assert result.intent == "revise"
    assert result.instruction == "please update"
    assert recorder is None
