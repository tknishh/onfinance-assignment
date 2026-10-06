from __future__ import annotations

from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from core.models import Trajectory


def _msg_to_dict(msg: BaseMessage) -> dict[str, str]:
    if isinstance(msg, SystemMessage):
        role = "system"
    elif isinstance(msg, HumanMessage):
        role = "user"
    elif isinstance(msg, AIMessage):
        role = "assistant"
    else:
        role = getattr(msg, "type", "user")
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    return {"role": role, "content": content}


class TrajectoryRecorder:
    def __init__(self, task: str, model: str, prompt_hash: str):
        self.task = task
        self.model = model
        self.prompt_hash = prompt_hash
        self.items: list[dict[str, Any]] = []

    def record(self, messages: list[BaseMessage], output: str) -> None:
        openai_msgs = [_msg_to_dict(m) for m in messages]
        openai_msgs.append({"role": "assistant", "content": output})
        self.items.append({"messages": openai_msgs})

    def to_rows(
        self,
        diagram_id: Optional[int],
        metrics: dict[str, Any],
    ) -> list[Trajectory]:
        rows: list[Trajectory] = []
        for item in self.items:
            rows.append(
                Trajectory(
                    diagram_id=diagram_id,
                    task=self.task,
                    prompt_hash=self.prompt_hash,
                    model=self.model,
                    messages=item["messages"],
                    metrics=dict(metrics),
                    reward=None,
                    used_in_training=False,
                )
            )
        return rows
