from kb.core.validate import _canonical_numeric_id, _cycle_from, _reserved_slug_id


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
