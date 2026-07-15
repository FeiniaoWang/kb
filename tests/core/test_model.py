import json

import pytest

from kb.core.ids import DocId
from kb.core.model import (
    ConfigLoadError,
    DocClass,
    Frontmatter,
    GovernanceFrontmatter,
    IndexFrontmatter,
    RawClass,
    load_config,
)


def test_shared_enums_have_pinned_values() -> None:
    assert [item.value for item in DocClass] == [
        "raw",
        "synthetic",
        "governance",
        "index",
    ]
    assert [item.value for item in RawClass] == ["source", "chat", "feedback"]


def test_frontmatter_preserves_order_and_unknown_keys() -> None:
    frontmatter = Frontmatter.model_validate(
        {"title": "One", "custom": {"nested": True}, "type": "adr"}
    )
    assert list(frontmatter.root) == ["title", "custom", "type"]
    assert frontmatter.root["custom"] == {"nested": True}


def test_typed_frontmatter_accepts_unknown_keys() -> None:
    governance = GovernanceFrontmatter.model_validate(
        {
            "id": "GOVERNANCE-CONVENTIONS",
            "type": "conventions",
            "title": "Project Conventions",
            "description": "Standing conventions.",
            "custom": "preserved",
        }
    )
    index = IndexFrontmatter.model_validate(
        {"type": "index", "description": "A directory.", "custom": 7}
    )
    assert governance.model_extra == {"custom": "preserved"}
    assert index.model_extra == {"custom": 7}
    assert "id" not in index.model_dump()


def test_load_config_defaults_missing_fields_and_ignores_unknown_keys(tmp_path) -> None:
    (tmp_path / "kb-config.json").write_text(
        json.dumps({"schema": 1, "future": "ignored"}), encoding="utf-8"
    )
    config = load_config(tmp_path)
    assert config.model_dump() == {
        "schema": 1,
        "types": [],
        "tags": [],
        "id_prefixes": {
            "synthetic": "KB",
            "source": "RAW",
            "chat": "CHAT",
            "feedback": "FEED",
        },
        "propagation_auto_safe": [],
    }


def test_load_config_reports_invalid_and_unsupported_schema(tmp_path) -> None:
    config_path = tmp_path / "kb-config.json"
    config_path.write_text("not json", encoding="utf-8")
    with pytest.raises(ConfigLoadError) as invalid:
        load_config(tmp_path)
    assert invalid.value.code == "E_CONFIG_INVALID"

    config_path.write_text('{"schema": 2}', encoding="utf-8")
    with pytest.raises(ConfigLoadError) as unsupported:
        load_config(tmp_path)
    assert unsupported.value.code == "E_SCHEMA_UNSUPPORTED"


def test_doc_id_parses_formats_and_orders_numeric_ids() -> None:
    assert DocId.parse("KB-000042") == DocId(prefix="KB", number=42)
    assert DocId.parse("KB-1000001").format() == "KB-1000001"
    assert DocId(prefix="RAW", number=3).format() == "RAW-000003"
    assert sorted(
        [DocId.parse("RAW-000001"), DocId.parse("KB-000002"), DocId.parse("KB-000001")]
    ) == [
        DocId(prefix="KB", number=1),
        DocId(prefix="KB", number=2),
        DocId(prefix="RAW", number=1),
    ]
    with pytest.raises(ValueError, match="numeric document id"):
        DocId.parse("GOVERNANCE-CONVENTIONS")
