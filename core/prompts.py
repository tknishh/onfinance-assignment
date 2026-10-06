from __future__ import annotations

from core.diagram_types import DiagramSpec


def system_generate(spec: DiagramSpec) -> str:
    return f"""You are a senior software architect and PlantUML expert.
Output ONLY JSON matching the schema with fields: title, plantuml, notes.
Rules:
- The plantuml field MUST start with @startuml and end with @enduml.
- No markdown fences.
- Use only syntax valid for a {spec.kind.value} diagram ({spec.category}).
- Hint: {spec.plantuml_hint}
- If a SHARED DESIGN MODEL is provided, it overrides your own choices: use its exact
  element names and do not add or drop actors, components, data stores, or external systems.
- Otherwise name domain entities explicitly from the user's prompt (services, actors, data stores).
- Keep the diagram to 40 elements or fewer.
- Quote identifiers that contain spaces.
- Title should be short and descriptive.

Example of valid PlantUML for this type (syntax reference only, not content):
{spec.example}
"""


def user_generate(prompt: str, spec: DiagramSpec, design_context: str = "") -> str:
    context = f"\n{design_context}\n" if design_context else ""
    return f"""Design a {spec.kind.value} UML diagram for this software:

{prompt}
{context}
Description of this diagram type: {spec.description}
Return JSON with title, plantuml, and optional notes about assumptions.
"""


def system_update(spec: DiagramSpec) -> str:
    return f"""You are a senior software architect and PlantUML expert.
Modify the existing {spec.kind.value} PlantUML diagram minimally to reflect the user's changes.
Preserve element names and layout where unaffected.
Output ONLY JSON: title, plantuml, notes.
plantuml MUST start with @startuml and end with @enduml. No markdown fences.
Hint: {spec.plantuml_hint}
"""


def user_update(
    new_prompt: str,
    old_prompt: str,
    old_plantuml: str,
    change_summary: str,
    design_context: str = "",
) -> str:
    context = f"\n{design_context}\n" if design_context else ""
    return f"""Previous prompt:
{old_prompt}

New prompt:
{new_prompt}

Change summary:
{change_summary}
{context}
Existing PlantUML:
{old_plantuml}

Return the updated diagram as JSON (title, plantuml, notes).
"""


def system_repair() -> str:
    return """You are a PlantUML syntax repair specialist.
Fix ONLY the syntax error. Do not change semantics or remove domain elements.
Output ONLY JSON: title, plantuml, notes.
plantuml MUST start with @startuml and end with @enduml. No markdown fences.
"""


def user_repair(plantuml: str, error: str, spec: DiagramSpec) -> str:
    return f"""Diagram type: {spec.kind.value}
PlantUML error:
{error}

Broken code:
{plantuml}

Hint for this type: {spec.plantuml_hint}
Return repaired JSON (title, plantuml, notes).
"""


def user_consistency_repair(
    plantuml: str, missing: list[str], spec: DiagramSpec, design_context: str
) -> str:
    return f"""Diagram type: {spec.kind.value}
This diagram is valid PlantUML but is inconsistent with the shared design model.
It is missing these required elements: {", ".join(missing)}

Add each missing element using its exact name (and alias), connect it as described
in the main flow, and keep everything that is already correct.

{design_context}

Current code:
{plantuml}

Hint for this type: {spec.plantuml_hint}
Return JSON (title, plantuml, notes).
"""


def system_design_model() -> str:
    return """You are a principal software architect. Before any UML is drawn, you define ONE
canonical design model that every diagram (sequence, component, class, deployment, ...)
will be generated from, so all diagrams of the system agree with each other.

Output ONLY JSON matching the schema. Rules:
- Names are Title Case, 1-4 words, no abbreviations, and unique across the whole model.
- If the system has human users, include them as actors AND include exactly one
  user-facing component in layer "Presentation" (e.g. a dashboard, portal, or API gateway).
- Group components into 3-5 layers, e.g. Presentation, Ingestion, Processing, Analysis,
  Integration. Use 4-10 components in total.
- List every persistent store as a separate data store (2-6), each with what it holds.
  Components never act as data stores.
- External systems are things the system does not own (regulator portals, email, Slack, ...).
- main_flow is the primary end-to-end scenario, ordered by step. It MUST start from an
  actor (or an external trigger/scheduler) via the Presentation component where relevant,
  and every component must appear in at least one step. source/target MUST be names
  defined in actors, components, data_stores, or external_systems.
- entities are the core domain classes with 3-6 attributes each and their relations.
- deployment places EVERY component and data store on exactly one node.
- lifecycle_entity is the most important stateful entity; lifecycle_states are 4-7 states in order.
"""


def user_design_model(prompt: str, kinds: list[str]) -> str:
    return f"""Software to design:
{prompt}

Diagrams that will be generated from this model: {", ".join(kinds)}

Return the shared design model as JSON.
"""


def user_update_design_model(
    old_model_json: str, old_prompt: str, new_prompt: str, kinds: list[str]
) -> str:
    return f"""The design has changed. Update the existing shared design model MINIMALLY:
keep every existing name unchanged unless the new prompt requires removing it, and
only add elements that the new prompt introduces.

Previous prompt:
{old_prompt}

New prompt:
{new_prompt}

Diagrams in scope: {", ".join(kinds)}

Existing design model:
{old_model_json}

Return the full updated design model as JSON.
"""


def system_intent() -> str:
    return """You classify a follow-up message in an ongoing UML design conversation. Return JSON with `intent`, `instruction`, and `target_kinds`.
- `question` applies when the user asks for an explanation, an opinion, or information, and requests no change. Examples: "why is there a gap analyzer?" and "what does the parser do?".
- `edit_diagrams` applies when the change is explicitly limited to named diagrams. Example: "in the sequence diagram, add retries". Set `target_kinds` to those diagrams.
- `add_diagrams` applies when the user asks for additional diagram types. Examples: "also give me a deployment diagram" and "add state machine". Set `target_kinds` to the new kinds.
- `remove_diagrams` applies when the user asks to drop diagram types. Set `target_kinds` to them.
- `new_design` applies when the message describes a completely different system that is unrelated to the current one.
- `revise` covers any other change to the system: new features, components, integrations, constraints, renames. It is also the default when unsure.
- `instruction` is a self-contained, imperative restatement of the request. It must make sense without the chat history.
- `target_kinds` may only contain these values: class, object, component, composite_structure, deployment, package, profile, use_case, activity, state_machine, sequence, communication, interaction_overview, timing.
"""


def user_intent(
    message: str, current_prompt: str, current_kinds: list[str], design_summary: str
) -> str:
    return f"""Current design prompt:
{current_prompt}

Current diagram kinds: {", ".join(current_kinds)}

Design summary:
{design_summary or "(none)"}

User follow-up:
{message}

Classify the follow-up. Return JSON with intent, instruction, target_kinds.
"""


def system_answer() -> str:
    return """You are the architect of this design. Answer the question using the shared design model and diagrams.
Be concise and use markdown.
Refer to elements by their exact names.
If the user seems to want a change, end with one line suggesting a follow-up they could send, for example "Reply with *add retries to the sequence diagram* to apply this."
"""


def user_answer(
    question: str, design_context: str, diagrams: list[tuple[str, str]]
) -> str:
    parts = []
    for kind, plantuml in diagrams:
        truncated = plantuml[:3000]
        parts.append(f"### {kind}\n```plantuml\n{truncated}\n```")
    diagrams_block = "\n\n".join(parts) if parts else "(no diagrams)"
    return f"""Question:
{question}

Shared design model:
{design_context or "(none)"}

Current diagrams:
{diagrams_block}
"""


def system_diff() -> str:
    return """You compare two software design prompts and decide which UML diagram kinds are affected.
Return JSON: summary (short), affected_kinds (list of kind strings), unaffected_kinds (list).
When unclear, mark the diagram as affected.
Only use the kind strings provided in the user message.
"""


def user_diff(old_prompt: str, new_prompt: str, kinds: list[str]) -> str:
    return f"""Old prompt:
{old_prompt}

New prompt:
{new_prompt}

Diagram kinds in scope: {", ".join(kinds)}

Classify each kind as affected or unaffected. Provide a short summary of what changed.
"""


def system_judge() -> str:
    return """You score how well a PlantUML diagram matches a design prompt.
Return JSON: score (0..1 float), reason (short).
Score coverage of requirements, correct UML for the diagram kind, and clarity.
"""


def user_judge(prompt: str, kind: str, plantuml: str) -> str:
    return f"""Prompt:
{prompt}

Diagram kind: {kind}

PlantUML:
{plantuml}

Score 0..1 and explain briefly.
"""
