import importlib.util
import json
import sys
import warnings

import pytest
from pydantic import ValidationError

import kb.core.model as model_module
from kb.core.ids import DocId
from kb.core.model import (
    Config,
    ConfigLoadError,
    DocClass,
    Frontmatter,
    GovernanceFrontmatter,
    IndexFrontmatter,
    OperationalFrontmatter,
    RawClass,
    load_config,
    parse_config_bytes,
)
from kb.core.model import RawFrontmatter
from kb.core.model import SyntheticFrontmatter


def test_shared_enums_have_pinned_values() -> None:
    assert [item.value for item in DocClass] == [
        "raw",
        "synthetic",
        "governance",
        "index",
        "operational",
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

    operational = OperationalFrontmatter.model_validate(
        {"type": "log", "custom": "preserved"}
    )
    assert operational.model_extra == {"custom": "preserved"}


def test_load_config_defaults_missing_fields_and_ignores_unknown_keys(tmp_path) -> None:
    (tmp_path / "kb-config.json").write_text(
        json.dumps({"schema": 1, "future": "ignored"}), encoding="utf-8"
    )
    config = load_config(tmp_path)
    assert config.schema == 1
    assert config.model_dump() == {
        "schema": 1,
        "types": [],
        "tags": [],
        "link_types": [],
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


def test_load_config_reports_invalid_utf8(tmp_path) -> None:
    (tmp_path / "kb-config.json").write_bytes(b'{"schema": "\xff"}')
    with pytest.raises(ConfigLoadError) as invalid:
        load_config(tmp_path)
    assert invalid.value.code == "E_CONFIG_INVALID"


def test_load_config_merges_missing_id_prefix_classes(tmp_path) -> None:
    (tmp_path / "kb-config.json").write_text(
        json.dumps({"id_prefixes": {"source": "SRC"}}), encoding="utf-8"
    )

    assert load_config(tmp_path).id_prefixes == {
        "synthetic": "KB",
        "source": "SRC",
        "chat": "CHAT",
        "feedback": "FEED",
    }


@pytest.mark.parametrize("prefix", ["lower", "BAD-PREFIX", 7, "GOVERNANCE"])
def test_load_config_rejects_invalid_id_prefix_values(tmp_path, prefix) -> None:
    (tmp_path / "kb-config.json").write_text(
        json.dumps({"id_prefixes": {"synthetic": prefix}}), encoding="utf-8"
    )

    with pytest.raises(ConfigLoadError) as raised:
        load_config(tmp_path)
    assert raised.value.code == "E_CONFIG_INVALID"


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


def test_config_model_definition_emits_no_warnings() -> None:
    module_name = "kb.core._model_warning_test"
    spec = importlib.util.spec_from_file_location(module_name, model_module.__file__)
    assert spec is not None
    assert spec.loader is not None
    isolated_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = isolated_module
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            spec.loader.exec_module(isolated_module)
    finally:
        del sys.modules[module_name]


def test_raw_frontmatter_accepts_unknown_keys_and_feedback_about() -> None:
    raw = RawFrontmatter.model_validate(
        {
            "id": "FEED-000001",
            "type": "feedback",
            "ingested_at": "2026-07-16T12:00:00Z",
            "origin": "stdin",
            "title": "FEED-000001",
            "about": "KB-000007",
            "future": True,
        }
    )
    assert raw.about == "KB-000007"
    assert raw.model_extra == {"future": True}


def test_synthetic_frontmatter_preserves_unknown_keys_and_optional_fields() -> None:
    frontmatter = SyntheticFrontmatter.model_validate(
        {
            "id": "KB-000001",
            "type": "spec",
            "title": "Retry Policy",
            "description": "Retry rules.",
            "status": "current",
            "derived_from": ["CHAT-000001"],
            "timestamp": "2026-07-16T10:00:00Z",
            "last_human_touch": "2026-07-16T10:00:00Z",
            "tags": ["api"],
            "supersedes": "KB-000000",
            "instructions": "Keep examples runnable.",
            "future": True,
        }
    )
    assert frontmatter.tags == ["api"]
    assert frontmatter.model_extra == {"future": True}


def test_synthetic_frontmatter_rejects_non_lifecycle_status() -> None:
    with pytest.raises(ValidationError):
        SyntheticFrontmatter(
            id="KB-000001",
            type="spec",
            title="Retry Policy",
            description="Retry rules.",
            status="unknown",
            derived_from=["CHAT-000001"],
            timestamp="2026-07-16T10:00:00Z",
            last_human_touch="2026-07-16T10:00:00Z",
        )


def test_governance_frontmatter_accepts_charter_type():
    fm = GovernanceFrontmatter(
        id="GOVERNANCE-CHARTER",
        type="charter",
        title="KB Charter",
        description="The KB's purpose. Human-maintained.",
    )
    assert fm.type == "charter"


def test_synthetic_frontmatter_accepts_links_and_pending_upstream():
    fm = SyntheticFrontmatter(
        id="KB-000001",
        type="spec",
        title="T",
        description="D.",
        status="current",
        derived_from=["CHAT-000001"],
        timestamp="2026-07-22T00:00:00Z",
        last_human_touch="2026-07-22T00:00:00Z",
        links={"references": ["KB-000002"]},
        pending_upstream=["CHAT-000001"],
    )
    assert fm.links == {"references": ["KB-000002"]}
    assert fm.pending_upstream == ["CHAT-000001"]


def test_config_link_types_defaults_empty_and_parses():
    assert Config().link_types == []
    config = parse_config_bytes(
        b'{"schema": 1, "link_types": ["references", "contradicts"]}'
    )
    assert config.link_types == ["references", "contradicts"]
