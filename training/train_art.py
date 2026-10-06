from __future__ import annotations

"""
Offline ART GRPO training for UML generation.

Important: ART is on-policy. Stored Groq completions are used as reward/rubric
signals (via RULER + user feedback), not as gradient tokens. The trainable model
rolls out its own completions.

Usage:
  python training/export_trajectories.py
  python training/train_art.py --dry-run          # no GPU
  python training/train_art.py                   # requires GPU + openpipe-art
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_groups(path: str) -> list[dict]:
    groups = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                groups.append(json.loads(line))
    return groups


def dry_run(path: str) -> None:
    groups = load_groups(path)
    print(f"Loaded {len(groups)} trajectory groups from {path}")
    for i, g in enumerate(groups[:5]):
        print(
            f"  [{i}] kind={g.get('kind')} samples={len(g.get('samples', []))} "
            f"hash={g.get('prompt_hash', '')[:12]}"
        )
    if len(groups) > 5:
        print(f"  ... and {len(groups) - 5} more")
    print("Dry-run OK. Install training/requirements-train.txt and a GPU to train.")


async def train(path: str, base_model: str, steps: int) -> None:
    try:
        import art
        from art.local import LocalBackend
    except ImportError as e:
        raise SystemExit(
            "openpipe-art not installed. pip install -r training/requirements-train.txt"
        ) from e

    from core.diagram_types import DiagramKind, get_spec
    from core.prompts import system_generate, user_generate
    from core.validator import sanitize
    from core.renderer import render_svg
    from core.feedback import compute_reward

    groups_data = load_groups(path)
    if not groups_data:
        raise SystemExit("No training groups. Run export_trajectories.py first.")

    # Hold out 10%
    split = max(1, len(groups_data) // 10)
    train_scenarios = groups_data[split:]
    eval_scenarios = groups_data[:split] or groups_data[:1]

    model = art.TrainableModel(
        name="uml-gen-v1",
        project="uml-studio",
        base_model=base_model,
    )
    backend = LocalBackend()
    await model.register(backend)

    async def rollout(model, scenario: dict) -> "art.Trajectory":
        kind_str = scenario.get("kind") or "sequence"
        try:
            kind = DiagramKind(kind_str)
        except ValueError:
            kind = DiagramKind.SEQUENCE
        spec = get_spec(kind)
        # The stored prefix is exactly what production sent, including the shared
        # design model context, so replay it to keep training on-distribution.
        prefix = [
            {"role": m["role"], "content": m["content"]}
            for m in scenario.get("messages_prefix", [])
            if m.get("role") in ("system", "user")
        ]
        if any(m["role"] == "user" for m in prefix):
            messages = prefix
        else:
            messages = [
                {"role": "system", "content": system_generate(spec)},
                {
                    "role": "user",
                    "content": user_generate(
                        f"Generate a {kind.value} diagram for a software system.", spec
                    ),
                },
            ]
        client = model.openai_client()
        completion = await client.chat.completions.create(
            model=model.name,
            messages=messages,
            max_tokens=2048,
            temperature=0.4,
        )
        choice = completion.choices[0]
        content = choice.message.content or ""
        # Parse plantuml from JSON if possible
        plantuml = content
        try:
            from core.llm import _extract_json
            from core.schemas import DiagramOut

            plantuml = DiagramOut.model_validate_json(_extract_json(content)).plantuml
        except Exception:
            pass
        code = sanitize(plantuml)
        ok, _, _ = await render_svg(code)
        # Incorporate historical user rewards into a soft prior
        hist = [s.get("reward") for s in scenario.get("samples", []) if s.get("reward") is not None]
        hist_avg = sum(hist) / len(hist) if hist else None
        reward = compute_reward(None, ok, 1, hist_avg)
        return art.Trajectory(
            messages_and_choices=[*messages, choice],
            reward=reward,
        )

    for step in range(steps):
        print(f"Training step {step + 1}/{steps}")
        traj_groups = []
        batch = train_scenarios[step % len(train_scenarios) : step % len(train_scenarios) + 2]
        if not batch:
            batch = train_scenarios[:2]
        for scenario in batch:
            tg = art.TrajectoryGroup(
                await asyncio.gather(*[rollout(model, scenario) for _ in range(4)])
            )
            # Optional RULER relative scoring if available
            try:
                await art.rewards.ruler_score_group(
                    tg, "groq/openai/gpt-oss-120b"
                )
            except Exception:
                pass
            traj_groups.append(tg)
        await model.train(traj_groups, config=art.TrainConfig(learning_rate=1e-5))

    # Eval
    rewards = []
    for scenario in eval_scenarios:
        t = await rollout(model, scenario)
        rewards.append(t.reward)
    avg = sum(rewards) / len(rewards) if rewards else 0
    print(f"Eval avg reward: {avg:.3f}")
    print(
        "If this beats your Groq baseline, serve with:\n"
        "  vllm serve ... --enable-lora\n"
        "  GEN_PROVIDER=openai_compat LLM_BASE_URL=..."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/train.jsonl")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-model", default="openai/gpt-oss-20b")
    parser.add_argument("--steps", type=int, default=5)
    args = parser.parse_args()
    if args.dry_run:
        if not Path(args.data).exists():
            # Create empty placeholder groups file for smoke test
            Path(args.data).parent.mkdir(parents=True, exist_ok=True)
            Path(args.data).write_text("", encoding="utf-8")
            print(f"No data at {args.data}; created empty file.")
        dry_run(args.data)
        return
    asyncio.run(train(args.data, args.base_model, args.steps))


if __name__ == "__main__":
    main()
