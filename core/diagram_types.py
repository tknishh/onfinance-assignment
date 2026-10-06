from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class DiagramKind(str, Enum):
    CLASS = "class"
    OBJECT = "object"
    COMPONENT = "component"
    COMPOSITE = "composite_structure"
    DEPLOYMENT = "deployment"
    PACKAGE = "package"
    PROFILE = "profile"
    USE_CASE = "use_case"
    ACTIVITY = "activity"
    STATE = "state_machine"
    SEQUENCE = "sequence"
    COMMUNICATION = "communication"
    INTERACTION_OVERVIEW = "interaction_overview"
    TIMING = "timing"


@dataclass(frozen=True)
class DiagramSpec:
    kind: DiagramKind
    category: Literal["structure", "behavior", "interaction"]
    description: str
    plantuml_hint: str
    required_tokens: list[str]
    example: str


def _ex(body: str) -> str:
    return f"@startuml\n{body.strip()}\n@enduml"


REGISTRY: dict[DiagramKind, DiagramSpec] = {
    DiagramKind.CLASS: DiagramSpec(
        kind=DiagramKind.CLASS,
        category="structure",
        description="Domain/API design: classes, attributes, operations, associations.",
        plantuml_hint="Use class, interface, --> *-- o-- <|--. Show attributes and methods.",
        required_tokens=[r"class\s", r"interface\s"],
        example=_ex(
            """
class CircularFetcher {
  +fetchLatest() : List~Circular~
}
class ClauseParser {
  +parse(text) : Table
}
CircularFetcher --> ClauseParser : feeds
"""
        ),
    ),
    DiagramKind.OBJECT: DiagramSpec(
        kind=DiagramKind.OBJECT,
        category="structure",
        description="Runtime instance snapshot for examples and multiplicities.",
        plantuml_hint="Use object Name { field = value } and links between objects.",
        required_tokens=[r"object\s"],
        example=_ex(
            """
object circular1 {
  id = "SEBI/2024/01"
  status = "parsed"
}
object clauseTable1 {
  rows = 42
}
circular1 --> clauseTable1
"""
        ),
    ),
    DiagramKind.COMPONENT: DiagramSpec(
        kind=DiagramKind.COMPONENT,
        category="structure",
        description="High-level building blocks and provided/required interfaces.",
        plantuml_hint="Use component, [X], interface (), package, and --> between them.",
        required_tokens=[r"component\s", r"\[.+\]"],
        example=_ex(
            """
package "Ingestion" {
  [Circular Fetcher]
  [Clause Parser]
}
package "Analysis" {
  [Requirement Extractor]
  [Gap Analyzer]
}
[Circular Fetcher] --> [Clause Parser]
[Clause Parser] --> [Requirement Extractor]
[Requirement Extractor] --> [Gap Analyzer]
"""
        ),
    ),
    DiagramKind.COMPOSITE: DiagramSpec(
        kind=DiagramKind.COMPOSITE,
        category="structure",
        description="Internal wiring of a class/component: parts, ports, connectors.",
        plantuml_hint="Nest components with portin/portout and internal parts.",
        required_tokens=[r"portin", r"portout", r"port\s"],
        example=_ex(
            """
component GapAnalyzer {
  portin requirementsIn
  portout gapsOut
  component Matcher
  component Scorer
  requirementsIn --> Matcher
  Matcher --> Scorer
  Scorer --> gapsOut
}
"""
        ),
    ),
    DiagramKind.DEPLOYMENT: DiagramSpec(
        kind=DiagramKind.DEPLOYMENT,
        category="structure",
        description="Runtime topology: nodes, environments, artifacts.",
        plantuml_hint="Use node, cloud, database, artifact and -> between them.",
        required_tokens=[r"node\s", r"cloud\s", r"database\s"],
        example=_ex(
            """
cloud "SEBI Portal" as SEBI
node "Ingestion Worker" as Worker {
  artifact "fetcher.jar"
}
database "Clause DB" as DB
SEBI -> Worker : HTTPS
Worker -> DB : JDBC
"""
        ),
    ),
    DiagramKind.PACKAGE: DiagramSpec(
        kind=DiagramKind.PACKAGE,
        category="structure",
        description="Namespaces and dependencies for layering.",
        plantuml_hint="Use package blocks and ..> for dependencies.",
        required_tokens=[r"package\s"],
        example=_ex(
            """
package ingestion {}
package analysis {}
package reporting {}
analysis ..> ingestion
reporting ..> analysis
"""
        ),
    ),
    DiagramKind.PROFILE: DiagramSpec(
        kind=DiagramKind.PROFILE,
        category="structure",
        description="UML customization with stereotypes and tagged values.",
        plantuml_hint="Class diagram with <<stereotype>> and notes for tagged values.",
        required_tokens=[r"<<.+>>"],
        example=_ex(
            """
class Circular <<document>> {
  +id
  +issuedAt
}
note right of Circular
  taggedValue: pii = false
end note
"""
        ),
    ),
    DiagramKind.USE_CASE: DiagramSpec(
        kind=DiagramKind.USE_CASE,
        category="behavior",
        description="Actors and goals; system scope.",
        plantuml_hint="Use actor, usecase/(UC), rectangle System { }.",
        required_tokens=[r"actor\s", r"usecase\s", r"\(.+\)"],
        example=_ex(
            """
left to right direction
actor Officer
rectangle "Compliance Monitor" {
  (Ingest Circulars)
  (Run Gap Analysis)
  (Assess Impact)
}
Officer --> (Run Gap Analysis)
Officer --> (Assess Impact)
"""
        ),
    ),
    DiagramKind.ACTIVITY: DiagramSpec(
        kind=DiagramKind.ACTIVITY,
        category="behavior",
        description="Workflow: actions, decisions, forks, swimlanes.",
        plantuml_hint="New activity syntax: start, :action;, if () then, fork, |lane|, stop.",
        required_tokens=[r"start", r":.+;"],
        example=_ex(
            """
start
:Fetch SEBI circulars;
:Parse into clause table;
:Extract requirements;
:Gap analysis;
:IT/ops impact assessment;
stop
"""
        ),
    ),
    DiagramKind.STATE: DiagramSpec(
        kind=DiagramKind.STATE,
        category="behavior",
        description="Lifecycles: states, events, guards, entry/exit.",
        plantuml_hint="Use [*] --> S1, state blocks, S1 --> S2 : event [guard].",
        required_tokens=[r"\[\*\]"],
        example=_ex(
            """
[*] --> Received
Received --> Parsed : parse_ok
Parsed --> Analyzed : gaps_computed
Analyzed --> Reported : impact_ready
Reported --> [*]
"""
        ),
    ),
    DiagramKind.SEQUENCE: DiagramSpec(
        kind=DiagramKind.SEQUENCE,
        category="interaction",
        description="Time-ordered messages for API and request lifecycles.",
        plantuml_hint="participant, ->, -->, alt/else/end, loop, activate.",
        required_tokens=[r"->"],
        example=_ex(
            """
participant Fetcher
participant Parser
participant Analyzer
Fetcher -> Parser : raw circular
activate Parser
Parser --> Fetcher : clause table
deactivate Parser
Fetcher -> Analyzer : clauses
Analyzer --> Fetcher : gaps + impact
"""
        ),
    ),
    DiagramKind.COMMUNICATION: DiagramSpec(
        kind=DiagramKind.COMMUNICATION,
        category="interaction",
        description="Same interaction as sequence; emphasizes participant links.",
        plantuml_hint="object/rectangle nodes with numbered links: 1: msg(), 2: msg().",
        required_tokens=[r"\d+\s*:"],
        example=_ex(
            """
object Fetcher
object Parser
object Analyzer
Fetcher --> Parser : 1: parse(circular)
Parser --> Analyzer : 2: analyze(clauses)
"""
        ),
    ),
    DiagramKind.INTERACTION_OVERVIEW: DiagramSpec(
        kind=DiagramKind.INTERACTION_OVERVIEW,
        category="interaction",
        description="Storyboard stitching interactions with control flow.",
        plantuml_hint="Activity syntax; actions as :ref SequenceName; or partitions.",
        required_tokens=[r"start", r"ref"],
        example=_ex(
            """
start
:ref IngestSequence;
:ref GapAnalysisSequence;
:ref ImpactReportSequence;
stop
"""
        ),
    ),
    DiagramKind.TIMING: DiagramSpec(
        kind=DiagramKind.TIMING,
        category="interaction",
        description="State/value over time along lifelines (SLA/timeout).",
        plantuml_hint='robust "X" as X, concise "Y" as Y, @0, X is State.',
        required_tokens=[r"robust\s", r"concise\s", r"clock\s"],
        example=_ex(
            """
robust "Fetcher" as F
concise "Parser" as P
@0
F is Idle
P is Idle
@100
F is Fetching
@300
F is Done
P is Parsing
@500
P is Done
"""
        ),
    ),
}

_ALIAS_MAP: dict[str, DiagramKind] = {
    "sequence": DiagramKind.SEQUENCE,
    "sequential": DiagramKind.SEQUENCE,
    "seq": DiagramKind.SEQUENCE,
    "sequencediagram": DiagramKind.SEQUENCE,
    "component": DiagramKind.COMPONENT,
    "components": DiagramKind.COMPONENT,
    "class": DiagramKind.CLASS,
    "classdiagram": DiagramKind.CLASS,
    "usecase": DiagramKind.USE_CASE,
    "state": DiagramKind.STATE,
    "statemachine": DiagramKind.STATE,
    "activity": DiagramKind.ACTIVITY,
    "flow": DiagramKind.ACTIVITY,
    "workflow": DiagramKind.ACTIVITY,
    "deployment": DiagramKind.DEPLOYMENT,
    "infra": DiagramKind.DEPLOYMENT,
    "package": DiagramKind.PACKAGE,
    "object": DiagramKind.OBJECT,
    "composite": DiagramKind.COMPOSITE,
    "compositestructure": DiagramKind.COMPOSITE,
    "profile": DiagramKind.PROFILE,
    "communication": DiagramKind.COMMUNICATION,
    "collaboration": DiagramKind.COMMUNICATION,
    "interactionoverview": DiagramKind.INTERACTION_OVERVIEW,
    "timing": DiagramKind.TIMING,
}


def _canon(raw: str) -> str:
    return re.sub(r"[\s\-_]+", "", raw.strip().lower())


ALIASES: dict[str, DiagramKind] = dict(_ALIAS_MAP)
# Also accept canonical enum values
for kind in DiagramKind:
    ALIASES[_canon(kind.value)] = kind


def normalize_types(raw: list[str]) -> tuple[list[DiagramKind], list[str]]:
    """Returns (valid kinds deduped in input order, unknown inputs)."""
    seen: set[DiagramKind] = set()
    kinds: list[DiagramKind] = []
    unknown: list[str] = []
    for item in raw:
        key = _canon(item)
        kind = ALIASES.get(key)
        if kind is None:
            unknown.append(item)
            continue
        if kind not in seen:
            seen.add(kind)
            kinds.append(kind)
    return kinds, unknown


def get_spec(kind: DiagramKind) -> DiagramSpec:
    return REGISTRY[kind]
