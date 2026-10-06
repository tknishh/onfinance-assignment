from core.design_model import (
    missing_names,
    normalize_design_model,
    render_design_context,
    required_names,
)
from core.diagram_types import DiagramKind
from core.schemas import (
    Actor,
    Component,
    DataStore,
    DeploymentNode,
    DesignModel,
    Interaction,
)


def _model() -> DesignModel:
    return DesignModel(
        system_name="Compliance Monitor",
        actors=[Actor(name="Compliance Officer")],
        components=[
            Component(name="Compliance Dashboard", layer="Presentation"),
            Component(name="Circular Parser", layer="Ingestion"),
            Component(name="Gap Analyzer", layer="Analysis"),
        ],
        data_stores=[DataStore(name="Parsed Clauses"), DataStore(name="Gap Results")],
        main_flow=[
            Interaction(step=1, source="Compliance Officer", target="Compliance Dashboard", message="open"),
            Interaction(step=2, source="Compliance Dashboard", target="Gap Analyzer", message="analyze"),
            Interaction(step=3, source="Gap Analyzer", target="Gap Results", message="store"),
        ],
        deployment=[DeploymentNode(name="App Server", hosts=["Compliance Dashboard"])],
    )


def test_sequence_requires_actor_and_ui_from_flow():
    names = required_names(_model(), DiagramKind.SEQUENCE)
    assert names == ["Compliance Officer", "Compliance Dashboard", "Gap Analyzer", "Gap Results"]


def test_missing_names_accepts_quoted_names_and_aliases():
    code = (
        '@startuml\nactor "Compliance Officer" as ComplianceOfficer\n'
        "boundary ComplianceDashboard\ncontrol GapAnalyzer\n@enduml\n"
    )
    assert missing_names(code, _model(), DiagramKind.SEQUENCE) == ["Gap Results"]


def test_component_requires_every_data_store():
    code = "@startuml\n[Compliance Dashboard]\n[Circular Parser]\n[Gap Analyzer]\ndatabase \"Parsed Clauses\"\n@enduml"
    assert missing_names(code, _model(), DiagramKind.COMPONENT) == ["Gap Results"]


def test_normalize_deploys_everything():
    model = normalize_design_model(_model())
    hosted = {h for node in model.deployment for h in node.hosts}
    assert {"Circular Parser", "Gap Analyzer", "Parsed Clauses", "Gap Results"} <= hosted


def test_context_lists_must_include():
    ctx = render_design_context(_model(), DiagramKind.SEQUENCE)
    assert "SHARED DESIGN MODEL" in ctx
    assert "MUST include every one of: Compliance Officer, Compliance Dashboard" in ctx
