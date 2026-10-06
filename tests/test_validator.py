from core.diagram_types import DiagramKind, get_spec
from core.validator import sanitize, structural_check


def test_sanitize_strips_fences():
    raw = "```plantuml\n@startuml\nA -> B\n@enduml\n```"
    out = sanitize(raw)
    assert out.startswith("@startuml")
    assert out.rstrip().endswith("@enduml")
    assert "```" not in out


def test_sanitize_adds_enduml():
    out = sanitize("@startuml\nA -> B")
    assert out.rstrip().endswith("@enduml")


def test_structural_sequence_ok():
    spec = get_spec(DiagramKind.SEQUENCE)
    code = "@startuml\nA -> B: hi\n@enduml\n"
    assert structural_check(code, spec) is None


def test_structural_missing_token():
    spec = get_spec(DiagramKind.SEQUENCE)
    code = "@startuml\nclass Foo\n@enduml\n"
    err = structural_check(code, spec)
    assert err is not None
    assert "required" in err.lower()


def test_structural_unbalanced_braces():
    spec = get_spec(DiagramKind.CLASS)
    code = "@startuml\nclass Foo {\n@enduml\n"
    err = structural_check(code, spec)
    assert err is not None
