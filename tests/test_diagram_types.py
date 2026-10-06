from core.diagram_types import DiagramKind, REGISTRY, normalize_types


def test_normalize_sequential_alias():
    kinds, unknown = normalize_types(["sequential", "Component", "foo"])
    assert kinds == [DiagramKind.SEQUENCE, DiagramKind.COMPONENT]
    assert unknown == ["foo"]


def test_normalize_dedupe():
    kinds, unknown = normalize_types(["seq", "sequence", "sequential"])
    assert kinds == [DiagramKind.SEQUENCE]
    assert unknown == []


def test_all_kinds_registered():
    assert set(REGISTRY.keys()) == set(DiagramKind)


def test_examples_have_start_end():
    for spec in REGISTRY.values():
        assert "@startuml" in spec.example.lower()
        assert "@enduml" in spec.example.lower()
