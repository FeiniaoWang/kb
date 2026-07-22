import pytest
import yaml

from kb.core.frontmatter import (
    render_synthetic_document,
    replace_document_body,
    replace_frontmatter_keys,
    replace_frontmatter_scalars,
    yaml_scalar,
)
from kb.core.model import SyntheticFrontmatter


def synthetic(**overrides: object) -> SyntheticFrontmatter:
    values: dict[str, object] = {
        "id": "KB-000001",
        "type": "spec",
        "title": "Retry: Policy",
        "description": "Rules.",
        "status": "draft",
        "derived_from": ["CHAT-000001"],
        "timestamp": "2026-07-16T10:00:00Z",
        "last_human_touch": "2026-07-16T10:00:00Z",
    }
    values.update(overrides)
    return SyntheticFrontmatter.model_validate(values)


def test_yaml_scalar_round_trips_yaml_sensitive_text() -> None:
    for value in ["plain", "yes", "a: b", "Résumé", "line # text"]:
        assert yaml.safe_load(yaml_scalar(value)) == value


def test_render_synthetic_document_pins_keys_sequences_and_body_boundary() -> None:
    rendered = render_synthetic_document(
        synthetic(
            tags=["api", "internal"],
            supersedes="KB-000000",
            instructions="Keep examples runnable.",
        ),
        "# Body\n",
    )
    assert rendered == """---
id: KB-000001
type: spec
title: 'Retry: Policy'
description: Rules.
status: draft
derived_from:
  - CHAT-000001
timestamp: 2026-07-16T10:00:00Z
last_human_touch: 2026-07-16T10:00:00Z
tags:
  - api
  - internal
supersedes: KB-000000
instructions: Keep examples runnable.
---
# Body
"""
    assert render_synthetic_document(synthetic(), "").endswith("---")


def test_replace_frontmatter_scalars_preserves_all_unmodified_bytes() -> None:
    source = b"""---\r
title: Old\r
status: 'current' # lifecycle\r
unknown: {style: flow}\r
type: spec\r
id: KB-000001\r
---\r
Body  \r
"""
    changed = replace_frontmatter_scalars(
        source,
        {
            "status": "superseded",
            "timestamp": "2026-07-16T10:00:00Z",
            "last_human_touch": "2026-07-16T10:00:00Z",
        },
        append_missing=("timestamp", "last_human_touch"),
    )
    assert changed == b"""---\r
title: Old\r
status: 'superseded' # lifecycle\r
unknown: {style: flow}\r
type: spec\r
id: KB-000001\r
timestamp: 2026-07-16T10:00:00Z\r
last_human_touch: 2026-07-16T10:00:00Z\r
---\r
Body  \r
"""


def test_replace_frontmatter_scalars_preserves_block_headers_and_boundaries() -> None:
    source = b"""---\r
status: |-\r
  current\r
timestamp: >-\r
  2026-06-02T14:11:08Z\r
last_human_touch: |-\r
  2026-06-02T14:11:08Z\r
unknown: {style: flow}\r
---\r
Body  \r
"""
    changed = replace_frontmatter_scalars(
        source,
        {
            "status": "superseded",
            "timestamp": "2026-07-16T10:00:00Z",
            "last_human_touch": "2026-07-16T10:00:00Z",
        },
    )
    assert changed == b"""---\r
status: |-\r
  superseded\r
timestamp: >-\r
  2026-07-16T10:00:00Z\r
last_human_touch: |-\r
  2026-07-16T10:00:00Z\r
unknown: {style: flow}\r
---\r
Body  \r
"""
    parsed = yaml.safe_load(changed.split(b"---", 2)[1])
    assert parsed["status"] == "superseded"
    assert parsed["timestamp"] == "2026-07-16T10:00:00Z"
    assert parsed["last_human_touch"] == "2026-07-16T10:00:00Z"


def test_replace_frontmatter_scalars_preserves_tags_anchors_and_aliases() -> None:
    source = b"""---
status: &lifecycle !!str 'current' # lifecycle
status_alias: *lifecycle
timestamp: !!str &created "2026-06-02T14:11:08Z"
timestamp_alias: *created
last_human_touch: &touch !!str 2026-06-02T14:11:08Z
touch_alias: *touch
---
Body
"""
    changed = replace_frontmatter_scalars(
        source,
        {
            "status": "superseded",
            "timestamp": "2026-07-16T10:00:00Z",
            "last_human_touch": "2026-07-16T10:00:00Z",
        },
    )
    assert changed == b"""---
status: &lifecycle !!str 'superseded' # lifecycle
status_alias: *lifecycle
timestamp: !!str &created "2026-07-16T10:00:00Z"
timestamp_alias: *created
last_human_touch: &touch !!str 2026-07-16T10:00:00Z
touch_alias: *touch
---
Body
"""
    parsed = yaml.safe_load(changed.split(b"---", 2)[1])
    assert parsed["status"] == parsed["status_alias"] == "superseded"
    assert parsed["timestamp"] == parsed["timestamp_alias"] == (
        "2026-07-16T10:00:00Z"
    )
    assert parsed["last_human_touch"] == parsed["touch_alias"] == (
        "2026-07-16T10:00:00Z"
    )


def test_replace_frontmatter_scalars_rejects_invalid_prepared_lifecycle() -> None:
    source = b"""---
id: KB-000001
type: spec
status: current
---
Body
"""

    with pytest.raises(ValueError, match="prepared frontmatter"):
        replace_frontmatter_scalars(source, {"status": "[superseded]"})


SOURCE = (
    b"---\n"
    b"id: KB-000001\n"
    b"type: spec\n"
    b"title: 'Quoted: title'\n"
    b"description: D.\n"
    b"status: draft\n"
    b"derived_from:\n"
    b"  - CHAT-000001\n"
    b"timestamp: 2026-07-01T00:00:00Z\n"
    b"last_human_touch: 2026-07-01T00:00:00Z\n"
    b"custom_key: kept  # comment survives\n"
    b"---\n"
    b"body line\n"
)


def test_replace_keys_preserves_untouched_bytes() -> None:
    result = replace_frontmatter_keys(
        SOURCE,
        set_keys={
            "derived_from": ["CHAT-000001", "RAW-000002"],
            "timestamp": "2026-07-22T00:00:00Z",
        },
    )
    text = result.decode()
    assert "title: 'Quoted: title'" in text
    assert "custom_key: kept  # comment survives" in text
    assert "  - RAW-000002\n" in text
    assert "timestamp: 2026-07-22T00:00:00Z" in text
    assert text.endswith("---\nbody line\n")


def test_replace_keys_appends_new_keys_at_end() -> None:
    result = replace_frontmatter_keys(
        SOURCE,
        set_keys={
            "links": {"references": ["KB-000009"]},
            "pending_upstream": ["CHAT-000001"],
        },
    )
    text = result.decode()
    block = text.split("---\n")[1]
    assert block.rstrip().endswith(
        "links:\n  references:\n    - KB-000009\n"
        "pending_upstream:\n  - CHAT-000001"
    )


def test_replace_keys_removes_keys() -> None:
    with_pending = replace_frontmatter_keys(
        SOURCE, set_keys={"pending_upstream": ["CHAT-000001"]}
    )
    cleared = replace_frontmatter_keys(
        with_pending, set_keys={}, remove_keys=("pending_upstream",)
    )
    assert b"pending_upstream" not in cleared


def test_replace_keys_rejects_duplicate_keys() -> None:
    duplicated = SOURCE.replace(
        b"status: draft\n", b"status: draft\nstatus: current\n"
    )
    with pytest.raises(ValueError):
        replace_frontmatter_keys(duplicated, set_keys={"timestamp": "x"})


def test_replace_keys_rejects_unsupported_values_and_non_scalar_keys() -> None:
    with pytest.raises(ValueError, match="unsupported frontmatter value"):
        replace_frontmatter_keys(SOURCE, set_keys={"status": 3})

    non_scalar_key = SOURCE.replace(
        b"custom_key: kept  # comment survives\n",
        b"? [custom, key]\n: kept\n",
    )
    with pytest.raises(ValueError, match="frontmatter keys must be scalars"):
        replace_frontmatter_keys(non_scalar_key, set_keys={"timestamp": "x"})


def test_replace_keys_preserves_crlf_and_renders_empty_collections() -> None:
    source = SOURCE.replace(b"\n", b"\r\n")

    changed = replace_frontmatter_keys(
        source,
        set_keys={"derived_from": [], "links": {"references": []}},
    )

    assert b"derived_from: []\r\n" in changed
    assert b"links:\r\n  references: []\r\n" in changed
    assert b"\n" not in changed.replace(b"\r\n", b"")


def test_replace_keys_rejects_setting_and_removing_the_same_key() -> None:
    with pytest.raises(ValueError, match="both set and removed"):
        replace_frontmatter_keys(
            SOURCE,
            set_keys={"status": "current"},
            remove_keys=("status",),
        )


def test_replace_body_swaps_and_empties() -> None:
    swapped = replace_document_body(SOURCE, "new body\n")
    assert swapped.decode().endswith("---\nnew body\n")
    emptied = replace_document_body(SOURCE, "")
    assert emptied.decode().rstrip("\n").endswith("---")
    assert b"body line" not in emptied


def test_replace_body_preserves_frontmatter_bytes_and_eol() -> None:
    source = SOURCE.replace(b"\n", b"\r\n")
    original_frontmatter = source.split(b"---\r\n", 2)[:2]

    changed = replace_document_body(source, "replacement")

    assert changed.split(b"---\r\n", 2)[:2] == original_frontmatter
    assert changed.endswith(b"---\r\nreplacement")


def test_replace_keys_preserves_inter_entry_and_trailing_comments() -> None:
    source = (
        b"---\n"
        b"status: draft  # touched comment may go\n"
        b"# Describes the untouched title.\n"
        b"title: 'Exact: untouched'  # exact inline comment\n"
        b"# trailing frontmatter comment\n"
        b"---\n"
        b"body\n"
    )
    untouched = (
        b"# Describes the untouched title.\n"
        b"title: 'Exact: untouched'  # exact inline comment\n"
        b"# trailing frontmatter comment\n"
    )

    updated = replace_frontmatter_keys(source, set_keys={"status": "current"})
    removed = replace_frontmatter_keys(
        source, set_keys={}, remove_keys=("status",)
    )

    assert updated == b"---\nstatus: current\n" + untouched + b"---\nbody\n"
    assert removed == b"---\n" + untouched + b"---\nbody\n"


def test_replace_keys_removing_only_key_emits_empty_mapping() -> None:
    source = b"---\nstatus: draft\n---\nbody\n"

    changed = replace_frontmatter_keys(
        source, set_keys={}, remove_keys=("status",)
    )

    assert changed == b"---\n{}\n---\nbody\n"
    assert yaml.safe_load(changed.split(b"---", 2)[1]) == {}


def test_replace_keys_noop_preserves_flow_empty_mapping() -> None:
    source = b"---\n{}\n---\nbody\n"

    assert replace_frontmatter_keys(source, set_keys={}) == source


def test_replace_keys_adds_first_key_to_flow_empty_mapping() -> None:
    source = b"---\n{}\n---\nbody\n"

    changed = replace_frontmatter_keys(source, set_keys={"status": "draft"})

    assert changed == b"---\nstatus: draft\n---\nbody\n"


def test_replace_keys_rejects_non_string_semantic_source_key() -> None:
    source = b"---\ntrue: value\n---\nbody\n"

    with pytest.raises(ValueError, match="frontmatter keys must be strings"):
        replace_frontmatter_keys(source, set_keys={})


def test_replace_keys_rejects_yaml_equivalent_duplicate_keys() -> None:
    source = b"---\ntrue: first\nyes: second\n---\nbody\n"

    with pytest.raises(ValueError, match="must occur exactly once"):
        replace_frontmatter_keys(source, set_keys={"status": "current"})


def test_replace_keys_renders_new_top_level_keys_yaml_safely() -> None:
    changed = replace_frontmatter_keys(SOURCE, set_keys={"true": "new"})
    frontmatter = yaml.safe_load(changed.split(b"---", 2)[1])

    assert b"'true': new\n" in changed
    assert frontmatter["true"] == "new"
    assert True not in frontmatter


@pytest.mark.parametrize(
    "invalid",
    [
        {"links": {"references": [1]}},
        {"links": {1: ["KB-000001"]}},
        {"links": {"references": ("KB-000001",)}},
        {"derived_from": ["CHAT-000001", 2]},
    ],
)
def test_replace_keys_rejects_invalid_nested_member_shapes(
    invalid: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="unsupported frontmatter"):
        replace_frontmatter_keys(SOURCE, set_keys=invalid)


def test_replace_body_handles_closing_delimiter_at_eof() -> None:
    source = b"---\ntype: spec\n---"

    assert replace_document_body(source, "replacement") == (
        b"---\ntype: spec\n---\nreplacement"
    )
    assert replace_document_body(source, "") == source
