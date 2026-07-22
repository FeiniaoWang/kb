import kb.core.validate as validate_module
import pytest

from conftest import make_doc, make_kb
from kb.core.validate import (
    ValidateRequest,
    _canonical_numeric_id,
    _cycle_from,
    _reserved_slug_id,
    validate,
)


def _valid_synthetic_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "id": "KB-000001",
        "type": "spec",
        "title": "Note",
        "description": "A concise note.",
        "status": "current",
        "derived_from": ["CHAT-000001"],
        "timestamp": "2026-07-16T10:00:00Z",
        "last_human_touch": "2026-07-16T10:00:00Z",
    }
    values.update(overrides)
    return values


def _chat_values() -> dict[str, object]:
    return {
        "id": "CHAT-000001",
        "type": "chat",
        "ingested_at": "2026-07-16T09:00:00Z",
        "origin": "stdin",
        "title": "Session",
    }


def test_ac76_links_and_pending_upstream_are_legal_synthetic_keys(tmp_path) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/chats/session.md", _chat_values())
    make_doc(
        root,
        "synthetic/note.md",
        _valid_synthetic_values(
            links={"references": ["CHAT-000001"]},
            pending_upstream=["CHAT-000001"],
        ),
    )

    findings = validate(ValidateRequest(kb_root=root)).findings

    assert not any(
        finding.code == "FM1_KEY_FORBIDDEN"
        and finding.path == "synthetic/note.md"
        for finding in findings
    )


@pytest.mark.parametrize(
    ("relative", "values"),
    [
        (
            "raw/sources/source.md",
            {
                "id": "RAW-000001",
                "type": "raw-source",
                "ingested_at": "2026-07-16T08:00:00Z",
                "origin": "file",
            },
        ),
        (
            "governance/conventions.md",
            {
                "id": "GOVERNANCE-CONVENTIONS",
                "type": "conventions",
                "title": "Project Conventions",
                "description": "Standing conventions.",
            },
        ),
        (
            "synthetic/index.md",
            {
                "type": "index",
                "title": "Synthetic Documents",
                "description": "Synthetic documents.",
            },
        ),
    ],
)
def test_ac76_links_and_pending_upstream_are_forbidden_outside_synthetic(
    tmp_path, relative: str, values: dict[str, object]
) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(
        root,
        relative,
        {
            **values,
            "links": {"undeclared": ["KB-999999"]},
            "pending_upstream": ["KB-999999"],
        },
    )

    findings = validate(ValidateRequest(kb_root=root)).findings
    document_findings = [
        finding for finding in findings if finding.path == relative
    ]

    assert [finding.code for finding in document_findings] == [
        "FM1_KEY_FORBIDDEN",
        "FM1_KEY_FORBIDDEN",
    ]
    assert {finding.message.split("'")[1] for finding in document_findings} == {
        "links",
        "pending_upstream",
    }
    assert not any(
        finding.code
        in {"LINKTYPE_UNDECLARED", "LINK_UNRESOLVED", "PU_NOT_PARENT"}
        for finding in document_findings
    )


@pytest.mark.parametrize(
    "links",
    [
        ["KB-000002"],
        {"": []},
        {1: []},
        {"references": "KB-000002"},
        {"references": ["", 1]},
    ],
)
def test_ac77_links_shape_must_be_mapping_of_string_lists(tmp_path, links) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/chats/session.md", _chat_values())
    make_doc(
        root,
        "synthetic/note.md",
        _valid_synthetic_values(links=links),
    )

    findings = validate(ValidateRequest(kb_root=root)).findings
    document_findings = [
        finding for finding in findings if finding.path == "synthetic/note.md"
    ]

    assert any(
        finding.code == "FM1_FIELD_INVALID"
        and "mapping of link type to a list of non-empty strings" in finding.message
        for finding in document_findings
    )
    assert not any(
        finding.code
        in {"LINKTYPE_UNDECLARED", "LINK_UNRESOLVED", "PU_NOT_PARENT"}
        for finding in document_findings
    )


@pytest.mark.parametrize("pending_upstream", ["CHAT-000001", [""], [1]])
def test_ac77_pending_upstream_shape_must_be_string_list(
    tmp_path, pending_upstream
) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/chats/session.md", _chat_values())
    make_doc(
        root,
        "synthetic/note.md",
        _valid_synthetic_values(pending_upstream=pending_upstream),
    )

    findings = validate(ValidateRequest(kb_root=root)).findings
    document_findings = [
        finding for finding in findings if finding.path == "synthetic/note.md"
    ]

    assert any(
        finding.code == "FM1_FIELD_INVALID"
        and "list of non-empty strings" in finding.message
        for finding in document_findings
    )
    assert not any(
        finding.code
        in {"LINKTYPE_UNDECLARED", "LINK_UNRESOLVED", "PU_NOT_PARENT"}
        for finding in document_findings
    )


def test_ac77_empty_links_and_pending_upstream_are_well_shaped(tmp_path) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/chats/session.md", _chat_values())
    make_doc(
        root,
        "synthetic/note.md",
        _valid_synthetic_values(links={}, pending_upstream=[]),
    )

    findings = validate(ValidateRequest(kb_root=root)).findings

    assert findings == []


def test_ac75_charter_document_is_valid_under_governance(tmp_path) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(
        root,
        "governance/charter.md",
        {
            "id": "GOVERNANCE-CHARTER",
            "type": "charter",
            "title": "KB Charter",
            "description": "The KB's purpose.",
        },
    )

    findings = validate(ValidateRequest(kb_root=root)).findings

    assert [finding for finding in findings if finding.path == "governance/charter.md"] == []


def test_ac75_charter_type_outside_governance_flags_location(tmp_path) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(
        root,
        "synthetic/charter.md",
        {
            "id": "GOVERNANCE-CHARTER",
            "type": "charter",
            "title": "KB Charter",
            "description": "The KB's purpose.",
        },
    )

    findings = validate(ValidateRequest(kb_root=root)).findings

    assert any(
        finding.code == "LOC_TYPE_MISMATCH"
        and finding.path == "synthetic/charter.md"
        for finding in findings
    )


def test_canonical_numeric_id_has_exact_width_and_growth_rules() -> None:
    assert _canonical_numeric_id("KB-000042") == ("KB", "000042")
    assert _canonical_numeric_id("KB-1000001") == ("KB", "1000001")
    assert _canonical_numeric_id("KB-42") is None
    assert _canonical_numeric_id("KB-0000042") is None
    assert _canonical_numeric_id("kb-000042") is None


def test_reserved_slug_id_is_governance_only() -> None:
    assert _reserved_slug_id("GOVERNANCE-CONVENTIONS")
    assert _reserved_slug_id("GOVERNANCE-KB-CONFIG")
    assert not _reserved_slug_id("GOVERNANCE-000001")
    assert not _reserved_slug_id("CONV-CONVENTIONS")


def test_cycle_from_starts_and_ends_at_the_anchor() -> None:
    graph = {
        "KB-000001": ["KB-000002"],
        "KB-000002": ["KB-000003"],
        "KB-000003": ["KB-000001"],
        "KB-000099": ["KB-000002"],
    }
    assert _cycle_from("KB-000001", graph) == [
        "KB-000001",
        "KB-000002",
        "KB-000003",
        "KB-000001",
    ]
    assert _cycle_from("KB-000002", graph) == [
        "KB-000002",
        "KB-000003",
        "KB-000001",
        "KB-000002",
    ]
    assert _cycle_from("KB-000099", graph) is None


def test_cycle_from_handles_a_deep_acyclic_chain() -> None:
    graph = {
        f"KB-{number:06d}": [f"KB-{number + 1:06d}"]
        for number in range(1, 1_202)
    }
    graph["KB-001202"] = []

    assert _cycle_from("KB-000001", graph) is None


def test_cycle_discovery_visits_a_dense_acyclic_graph_linearly() -> None:
    class CountedTargets(list[str]):
        reads = 0

        def __iter__(self):
            for target in super().__iter__():
                type(self).reads += 1
                yield target

        def __getitem__(self, index):
            type(self).reads += 1
            return super().__getitem__(index)

    node_count = 32
    graph = {
        f"KB-{source:06d}": CountedTargets(
            f"KB-{target:06d}" for target in range(source + 1, node_count + 1)
        )
        for source in range(1, node_count + 1)
    }
    edge_count = node_count * (node_count - 1) // 2
    cycle_paths = getattr(validate_module, "_cycle_paths", None)

    assert callable(cycle_paths)
    CountedTargets.reads = 0
    assert cycle_paths(graph) == {}
    assert CountedTargets.reads <= edge_count * 4 + node_count


def test_cycle_discovery_returns_one_deterministic_path_per_participant() -> None:
    graph = {
        "KB-000001": ["KB-000002"],
        "KB-000002": ["KB-000003", "KB-000004"],
        "KB-000003": ["KB-000001"],
        "KB-000004": ["KB-000002"],
        "KB-000099": ["KB-000001"],
    }
    cycle_paths = getattr(validate_module, "_cycle_paths", None)

    assert callable(cycle_paths)
    first = cycle_paths(graph)
    assert first == cycle_paths(graph)
    assert set(first) == {"KB-000001", "KB-000002", "KB-000003", "KB-000004"}
    for participant, path in first.items():
        assert path[0] == participant == path[-1]
        assert all(target in graph[source] for source, target in zip(path, path[1:]))
