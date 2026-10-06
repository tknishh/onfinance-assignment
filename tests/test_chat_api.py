from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


def test_chat_sse():
    async def fake_chat(req, emit):
        await emit("intent", {"intent": "new_design", "instruction": "x", "target_kinds": []})
        await emit("done", {"conversation_id": 1, "version_id": 1})

    with patch("api.handle_chat", new=fake_chat):
        with TestClient(app) as client:
            r = client.post(
                "/chat",
                json={
                    "user_id": "u1",
                    "message": "Design a URL shortener with analytics and caching.",
                    "diagram_types": ["sequence", "component"],
                },
            )
            assert r.status_code == 200
            assert "event: intent" in r.text
            assert "event: done" in r.text


def test_timeline_requires_owner():
    with TestClient(app) as client:
        missing = client.get("/conversations/99999/timeline?user_id=nobody")
        assert missing.status_code == 404
