import yaml

from kb.core.frontmatter import (
    render_synthetic_document,
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
