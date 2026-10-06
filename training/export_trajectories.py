from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# Allow running as script from repo root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import repository as repo
from core.db import get_session, init_db


def main(out_path: str = "data/train.jsonl") -> None:
    init_db()
    groups: dict[tuple[str, str], dict] = {}
    with get_session() as session:
        rows = repo.exportable_trajectories(session)
        for t in rows:
            # Derive kind from metrics or last diagram
            kind = (t.metrics or {}).get("kind")
            if not kind and t.diagram_id:
                d = repo.get_diagram(session, t.diagram_id)
                kind = d.kind if d else "unknown"
            key = (t.prompt_hash, str(kind))
            if key not in groups:
                # messages_prefix = all but last assistant
                msgs = t.messages or []
                prefix = msgs[:-1] if msgs and msgs[-1].get("role") == "assistant" else msgs
                completion = (
                    msgs[-1]["content"]
                    if msgs and msgs[-1].get("role") == "assistant"
                    else ""
                )
                groups[key] = {
                    "prompt_hash": t.prompt_hash,
                    "kind": kind,
                    "messages_prefix": prefix,
                    "samples": [],
                }
            msgs = t.messages or []
            completion = (
                msgs[-1]["content"]
                if msgs and msgs[-1].get("role") == "assistant"
                else ""
            )
            groups[key]["samples"].append(
                {"completion": completion, "reward": t.reward, "trajectory_id": t.id}
            )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for g in groups.values():
            f.write(json.dumps(g) + "\n")
    print(f"Wrote {len(groups)} groups to {out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "data/train.jsonl"
    main(out)
