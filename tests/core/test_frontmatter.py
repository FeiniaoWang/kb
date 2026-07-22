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
