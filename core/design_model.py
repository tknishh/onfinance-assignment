from __future__ import annotations

import json
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from core.cache import get_gen_cache, prompt_hash, set_gen_cache
from core.config import get_settings
from core.diagram_types import DiagramKind
from core.llm import invoke_structured
from core.prompts import (
    system_design_model,
    user_design_model,
    user_update_design_model,
)
from core.schemas import DeploymentNode, DesignModel
from core.tracing import TrajectoryRecorder

_FLOW_KINDS = {
    DiagramKind.SEQUENCE,
    DiagramKind.COMMUNICATION,
    DiagramKind.TIMING,
    DiagramKind.ACTIVITY,
    DiagramKind.INTERACTION_OVERVIEW,
    DiagramKind.USE_CASE,
}
_STRUCTURE_KINDS = {
    DiagramKind.COMPONENT,
    DiagramKind.PACKAGE,
    DiagramKind.PROFILE,
    DiagramKind.COMPOSITE,
}

KIND_GUIDANCE: dict[DiagramKind, str] = {
    DiagramKind.SEQUENCE: (
        "Declare participants left-to-right in this order: `actor` for actors, "
        "`boundary` for Presentation-layer components, `control`/`participant` for "
        "services, `database` for data stores, `entity`/`participant` for external "
        "systems. Follow the main flow step order exactly; replies become dashed "
        "return messages. You may add alt/opt/loop fragments but not new participants."
    ),
    DiagramKind.COMMUNICATION: (
        "One object per main-flow participant. Number every link with the main-flow "
        "step number (e.g. `3: extractRequirements()`)."
    ),
    DiagramKind.COMPONENT: (
        "One `package` per layer, named exactly as the layer, containing that layer's "
        "components. Put every data store as `database` inside a package named "
        "\"Data Stores\". External systems go outside as `cloud`. Draw arrows that "
        "match main-flow source/target pairs."
    ),
    DiagramKind.DEPLOYMENT: (
        "One `node` (or `cloud`) per deployment entry, named exactly as given. Inside "
        "each, place its hosted components as `artifact` and hosted data stores as "
        "`database`. Connect nodes where the main flow crosses nodes."
    ),
    DiagramKind.CLASS: (
        "One class per domain entity with exactly the listed attributes. Relations "
        "come from related_to. You may add one service class per component with "
        "operations named after its main-flow messages."
    ),
    DiagramKind.OBJECT: (
        "Instances of the domain entities (e.g. `object circular1`) with realistic "
        "sample values for the listed attributes."
    ),
    DiagramKind.PACKAGE: (
        "One package per layer, named exactly as the layer. Dependencies follow the "
        "direction of the main flow between layers."
    ),
    DiagramKind.PROFILE: (
        "Define one stereotype per layer (e.g. <<presentation>>, <<processing>>, "
        "<<datastore>>) and apply them to the components and data stores."
    ),
    DiagramKind.COMPOSITE: (
        "Pick the most central processing component. Its parts are its "
        "sub-responsibilities; its ports connect to its main-flow neighbours."
    ),
    DiagramKind.USE_CASE: (
        "Use the actors exactly as named. Derive use cases from the goals in the main "
        "flow. Name the system boundary rectangle after the system name."
    ),
    DiagramKind.ACTIVITY: (
        "One swimlane (`|Name|`) per actor/component that appears in the main flow, "
        "named exactly as given. Actions follow the main-flow order."
    ),
    DiagramKind.INTERACTION_OVERVIEW: (
        "Group the main flow into 3-6 phases and show each as `:ref <Phase>;`, "
        "using component names in the phase titles."
    ),
    DiagramKind.STATE: (
        "Model the lifecycle of the lifecycle entity using exactly the listed states, "
        "in order. Transition events come from main-flow messages."
    ),
    DiagramKind.TIMING: (
        "One lifeline per component in the main flow; time ticks follow main-flow "
        "step order."
    ),
}


def alias(name: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Element"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _all_element_names(model: DesignModel) -> list[str]:
    return (
        [a.name for a in model.actors]
        + [c.name for c in model.components]
        + [d.name for d in model.data_stores]
        + [e.name for e in model.external_systems]
    )


def _flow_participants(model: DesignModel) -> list[str]:
    known = {_norm(n): n for n in _all_element_names(model)}
    seen: list[str] = []
    for step in sorted(model.main_flow, key=lambda s: s.step):
        for name in (step.source, step.target):
            canon = known.get(_norm(name))
            if canon and canon not in seen:
                seen.append(canon)
    return seen


def normalize_design_model(model: DesignModel) -> DesignModel:
    """Dedupe names and make sure every component/data store is deployed somewhere."""

    def dedupe(items):
        out, seen = [], set()
        for item in items:
            key = _norm(item.name)
            if key and key not in seen:
                seen.add(key)
                out.append(item)
        return out

    model.actors = dedupe(model.actors)
    model.components = dedupe(model.components)
    model.data_stores = dedupe(model.data_stores)
    model.external_systems = dedupe(model.external_systems)
    model.entities = dedupe(model.entities)
    model.deployment = dedupe(model.deployment)

    deployed = {_norm(h) for node in model.deployment for h in node.hosts}
    missing_components = [c.name for c in model.components if _norm(c.name) not in deployed]
    missing_stores = [d.name for d in model.data_stores if _norm(d.name) not in deployed]
    if missing_components:
        model.deployment.append(
            DeploymentNode(name="Application Server", node_type="node", hosts=missing_components)
        )
    if missing_stores:
        model.deployment.append(
            DeploymentNode(name="Database Server", node_type="node", hosts=missing_stores)
        )
    return model


def required_names(model: Optional[DesignModel], kind: DiagramKind) -> list[str]:
    """Names that must appear in a diagram of this kind for it to be consistent."""
    if model is None:
        return []
    if kind in (DiagramKind.SEQUENCE, DiagramKind.COMMUNICATION):
        return _flow_participants(model)
    if kind == DiagramKind.ACTIVITY:
        stores = {_norm(d.name) for d in model.data_stores}
        return [n for n in _flow_participants(model) if _norm(n) not in stores]
    if kind == DiagramKind.COMPONENT:
        return (
            [c.name for c in model.components]
            + [d.name for d in model.data_stores]
            + [e.name for e in model.external_systems]
        )
    if kind == DiagramKind.DEPLOYMENT:
        return [c.name for c in model.components] + [d.name for d in model.data_stores]
    if kind == DiagramKind.PACKAGE:
        return sorted({c.layer for c in model.components if c.layer})
    if kind == DiagramKind.CLASS:
        return [e.name for e in model.entities]
    if kind == DiagramKind.USE_CASE:
        return [a.name for a in model.actors]
    if kind == DiagramKind.STATE:
        return list(model.lifecycle_states)
    return []


def missing_names(code: str, model: Optional[DesignModel], kind: DiagramKind) -> list[str]:
    haystack = _norm(code)
    return [
        name
        for name in required_names(model, kind)
        if _norm(name) not in haystack and _norm(alias(name)) not in haystack
    ]


def kind_signature(model: Optional[DesignModel], kind: DiagramKind) -> str:
    """Hash of the part of the model a diagram kind depends on."""
    if model is None:
        return ""
    if kind in _FLOW_KINDS:
        data = model.model_dump(
            include={"actors", "components", "data_stores", "external_systems", "main_flow"}
        )
    elif kind in _STRUCTURE_KINDS:
        data = model.model_dump(
            include={"components", "data_stores", "external_systems", "main_flow"}
        )
    elif kind == DiagramKind.DEPLOYMENT:
        data = model.model_dump(include={"components", "data_stores", "deployment"})
    elif kind in (DiagramKind.CLASS, DiagramKind.OBJECT):
        data = model.model_dump(include={"entities"})
    elif kind == DiagramKind.STATE:
        data = model.model_dump(include={"lifecycle_entity", "lifecycle_states"})
    else:
        data = model.model_dump()
    return prompt_hash(json.dumps(data, sort_keys=True))


def model_hash(model: Optional[DesignModel]) -> str:
    if model is None:
        return ""
    return prompt_hash(model.model_dump_json())


def render_design_context(model: Optional[DesignModel], kind: DiagramKind) -> str:
    if model is None:
        return ""
    lines = [
        "SHARED DESIGN MODEL (single source of truth for ALL diagrams of this system)",
        f"System: {model.system_name}" + (f" - {model.summary}" if model.summary else ""),
    ]
    if model.actors:
        lines.append("Actors:")
        lines += [f"  - {a.name} (alias {alias(a.name)}): {a.description}" for a in model.actors]
    if model.components:
        lines.append("Components (grouped by layer):")
        layers: dict[str, list] = {}
        for c in model.components:
            layers.setdefault(c.layer or "Core", []).append(c)
        for layer, comps in layers.items():
            lines.append(f"  [{layer}]")
            lines += [
                f"    - {c.name} (alias {alias(c.name)}): {c.responsibility}" for c in comps
            ]
    if model.data_stores:
        lines.append("Data stores:")
        lines += [
            f"  - {d.name} (alias {alias(d.name)}, {d.technology}): holds {d.holds}"
            for d in model.data_stores
        ]
    if model.external_systems:
        lines.append("External systems:")
        lines += [
            f"  - {e.name} (alias {alias(e.name)}): {e.description}"
            for e in model.external_systems
        ]
    if model.entities:
        lines.append("Domain entities:")
        for e in model.entities:
            rel = f" -> related to {', '.join(e.related_to)}" if e.related_to else ""
            lines.append(f"  - {e.name}({', '.join(e.attributes)}){rel}")
    if model.main_flow:
        lines.append("Main flow (ordered):")
        for s in sorted(model.main_flow, key=lambda s: s.step):
            reply = f" (reply: {s.reply})" if s.reply else ""
            lines.append(f"  {s.step}. {s.source} -> {s.target}: {s.message}{reply}")
    if model.deployment:
        lines.append("Deployment:")
        lines += [
            f"  - {n.name} [{n.node_type}] hosts: {', '.join(n.hosts)}" for n in model.deployment
        ]
    if model.lifecycle_states:
        lines.append(
            f"Lifecycle of {model.lifecycle_entity}: {' -> '.join(model.lifecycle_states)}"
        )

    must = required_names(model, kind)
    lines += [
        "",
        f"RULES FOR THIS {kind.value.upper()} DIAGRAM:",
        "- Use the exact names above. Where syntax allows, declare elements as "
        '"Display Name" as Alias using the given alias.',
        "- Do NOT invent, rename, merge, or split actors, components, data stores, or "
        "external systems.",
        f"- {KIND_GUIDANCE.get(kind, '')}",
    ]
    if must:
        lines.append(f"- MUST include every one of: {', '.join(must)}")
    return "\n".join(lines)


async def build_design_model(
    prompt: str, kinds: list[DiagramKind]
) -> tuple[Optional[DesignModel], Optional[TrajectoryRecorder]]:
    settings = get_settings()
    key = prompt_hash("design_model", settings.gen_model, prompt)
    cached = get_gen_cache(key)
    if cached:
        return DesignModel.model_validate(cached), None

    recorder = TrajectoryRecorder("design_model", settings.gen_model, key)
    msgs = [
        SystemMessage(content=system_design_model()),
        HumanMessage(content=user_design_model(prompt, [k.value for k in kinds])),
    ]
    try:
        model = await invoke_structured("gen", DesignModel, msgs, recorder)
    except Exception:
        return None, recorder
    model = normalize_design_model(model)
    set_gen_cache(key, model.model_dump())
    return model, recorder


async def update_design_model(
    old: DesignModel,
    old_prompt: str,
    new_prompt: str,
    kinds: list[DiagramKind],
) -> tuple[Optional[DesignModel], Optional[TrajectoryRecorder]]:
    settings = get_settings()
    key = prompt_hash("design_model_update", settings.gen_model, old.model_dump_json(), new_prompt)
    cached = get_gen_cache(key)
    if cached:
        return DesignModel.model_validate(cached), None

    recorder = TrajectoryRecorder("design_model", settings.gen_model, key)
    msgs = [
        SystemMessage(content=system_design_model()),
        HumanMessage(
            content=user_update_design_model(
                old.model_dump_json(indent=2), old_prompt, new_prompt, [k.value for k in kinds]
            )
        ),
    ]
    try:
        model = await invoke_structured("gen", DesignModel, msgs, recorder)
    except Exception:
        return None, recorder
    model = normalize_design_model(model)
    set_gen_cache(key, model.model_dump())
    return model, recorder
