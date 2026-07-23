from __future__ import annotations

import json
from pathlib import Path

import pytest

import kb.core.revise as revise_module

from kb.core.housekeeping import init_kb
from kb.core.revise import (
    ReviseFailure,
    ReviseRequest,
    ReviseResult,
    execute_revise,
    prepare_revise,
)
from kb.core.scan import read_frontmatter


CHAT = """---
id: CHAT-000001
type: chat
ingested_at: 2026-07-20T09:00:00Z
origin: stdin
title: Session
---
chat body
"""
RAW = """---
id: RAW-000002
type: raw-source
ingested_at: 2026-07-20T09:30:00Z
origin: file
title: Source
---
raw body
"""
TARGET = """---
id: KB-000001
type: spec
title: "Quoted title" # keep this comment
description: A concise note.
status: draft
derived_from:
- CHAT-000001
timestamp: 2026-07-20T10:00:00Z
last_human_touch: 2026-07-20T09:59:00Z
custom_key: kept
---
old body
"""


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _base(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "kb"
    init_kb(root)
    _write(root, "raw/chats/chat-000001.md", CHAT)
    _write(root, "raw/sources/raw-000002.md", RAW)
    return root, _write(root, "synthetic/kb-000001.md", TARGET)


def _synthetic(
    doc_id: str,
    parents: list[str],
    *,
    status: str = "draft",
    extra: str = "",
) -> str:
    parent_lines = "".join(f"- {parent}\n" for parent in parents)
    return (
        "---\n"
        f"id: {doc_id}\n"
        "type: spec\n"
        f"title: {doc_id}\n"
        "description: A concise note.\n"
        f"status: {status}\n"
        "derived_from:\n"
        f"{parent_lines}"
        "timestamp: 2026-07-20T10:00:00Z\n"
        "last_human_touch: 2026-07-20T09:59:00Z\n"
        f"{extra}"
        "---\nbody\n"
    )


def _revise(
    root: Path,
    ref: str = "KB-000001",
    *,
    body_data: bytes | None = None,
    **kwargs: object,
) -> ReviseResult:
    prepared = prepare_revise(ReviseRequest(ref=ref, kb_root=root, **kwargs))
    return execute_revise(prepared, body_data)


def _failure(
    root: Path,
    *,
    ref: str = "KB-000001",
    body_data: bytes | None = None,
    **kwargs: object,
) -> ReviseFailure:
    with pytest.raises(ReviseFailure) as raised:
        _revise(root, ref, body_data=body_data, **kwargs)
    return raised.value


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _values(path: Path) -> dict[str, object]:
    return read_frontmatter(path).root


def _revised_rows(root: Path) -> list[str]:
    return [
        line
        for line in (root / "log.md").read_text(encoding="utf-8").splitlines()
        if " | revised | " in line
    ]


def test_ac01_append_parent_is_lossless_and_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, target = _base(tmp_path)
    monkeypatch.setattr(revise_module, "utc_now", lambda: "2026-07-20T10:00:00Z")
    before = _values(target)
    result = _revise(root, add_parents=["RAW-000002"])
    values = _values(target)
    content = target.read_bytes()
    assert values["derived_from"] == ["CHAT-000001", "RAW-000002"]
    assert values["timestamp"] == "2026-07-20T10:00:01Z"
    assert values["last_human_touch"] == before["last_human_touch"]
    assert b'title: "Quoted title" # keep this comment\n' in content
    assert b"custom_key: kept\n" in content
    assert result.updated == ["synthetic/kb-000001.md"]
    row, = _revised_rows(root)
    assert " | revised | kb-cli | KB-000001 | synthetic/kb-000001.md" in row
    assert str(values["timestamp"]) in row

    _revise(root, status="current", human=True)
    values = _values(target)
    assert values["last_human_touch"] == values["timestamp"]


def test_ac03_target_and_parent_path_refs_are_canonical(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    result = _revise(
        root,
        "synthetic/kb-000001",
        add_parents=["raw/sources/raw-000002"],
    )
    assert result.id == "KB-000001"
    assert result.path == "synthetic/kb-000001.md"
    assert _values(target)["derived_from"][-1] == "RAW-000002"


def test_ac05_parent_failures_are_typed_and_atomic(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    cases = [
        (["CHAT-000001"], "E_REVISE_PARENT_DUPLICATE"),
        (["RAW-000002", "RAW-000002"], "E_REVISE_PARENT_DUPLICATE"),
        (["RAW-999999"], "E_REVISE_PARENT_UNRESOLVED"),
    ]
    for parents, code in cases:
        before = _snapshot(root)
        failure = _failure(root, add_parents=parents)
        assert (failure.code, failure.exit_code) == (code, 1)
        assert _snapshot(root) == before


def test_ac08_cycles_name_direct_and_transitive_walks(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    _write(
        root,
        "synthetic/kb-000002.md",
        _synthetic("KB-000002", ["CHAT-000001", "KB-000001"]),
    )
    direct = _failure(root, add_parents=["KB-000002"])
    assert direct.code == "E_REVISE_CYCLE"
    assert "KB-000001 -> KB-000002 -> KB-000001" in direct.message
    _write(
        root,
        "synthetic/kb-000003.md",
        _synthetic("KB-000003", ["CHAT-000001", "KB-000002"]),
    )
    transitive = _failure(root, add_parents=["KB-000003"])
    assert "KB-000001 -> KB-000003 -> KB-000002 -> KB-000001" in transitive.message


def test_ac10_raw_and_governance_parents_append(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, add_parents=["RAW-000002", "GOVERNANCE-CHARTER"])
    assert _values(target)["derived_from"][-2:] == [
        "RAW-000002",
        "GOVERNANCE-CHARTER",
    ]


def test_ac11_links_append_order_and_duplicates(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, links=["references=CHAT-000001"])
    _revise(
        root,
        links=["references=RAW-000002", "contradicts=CHAT-000001"],
    )
    links = _values(target)["links"]
    assert links == {
        "references": ["CHAT-000001", "RAW-000002"],
        "contradicts": ["CHAT-000001"],
    }
    before = _snapshot(root)
    failure = _failure(root, links=["references=RAW-000002"])
    assert failure.code == "E_REVISE_LINK_DUPLICATE"
    assert _snapshot(root) == before


def test_ac15_link_token_and_target_failures(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    for token in ["references", "=KB-000001", "references="]:
        with pytest.raises(ReviseFailure) as raised:
            prepare_revise(
                ReviseRequest(ref="KB-000001", links=[token], kb_root=root)
            )
        assert (raised.value.code, raised.value.exit_code) == (
            "E_REVISE_LINK_INVALID",
            2,
        )
    assert (
        _failure(root, links=["references=KB-999999"]).code
        == "E_REVISE_LINK_UNRESOLVED"
    )


def test_ac17_link_type_warnings_are_stable_and_once(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    assert _revise(root, links=["references=CHAT-000001"]).warnings == []
    result = _revise(root, links=["blocks=CHAT-000001", "blocks=RAW-000002"])
    assert result.warnings == [
        "warning: link type is not declared in kb-config.json: blocks"
    ]
    root2, _ = _base(tmp_path / "second")
    config_path = root2 / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["link_types"] = []
    config_path.write_text(json.dumps(config) + "\n", encoding="utf-8")
    assert _revise(
        root2, links=["references=CHAT-000001", "blocks=RAW-000002"]
    ).warnings == [
        "warning: link type is not declared in kb-config.json: references",
        "warning: link type is not declared in kb-config.json: blocks",
    ]


def test_ac19_status_transitions_and_frozen_target(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, status="current")
    assert _values(target)["status"] == "current"
    _revise(root, status="current")
    assert _values(target)["status"] == "current"
    _revise(root, status="retired")
    assert _values(target)["status"] == "retired"
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "status: retired", "status: superseded"
        ),
        encoding="utf-8",
    )
    assert _failure(root, status="draft").code == "E_REVISE_TARGET_INVALID"


def test_ac19_status_only_rewrite_changes_only_status_and_timestamp(
    tmp_path: Path,
) -> None:
    root, target = _base(tmp_path)
    before = target.read_bytes()
    _revise(root, status="current")
    after = target.read_bytes()
    assert before.replace(b"status: draft", b"status: current") != after
    before_without_timestamp = before.replace(
        b"status: draft", b"status: current"
    ).split(b"timestamp: 2026-07-20T10:00:00Z", 1)
    after_without_timestamp = after.split(b"timestamp:", 1)
    assert before_without_timestamp[0] == after_without_timestamp[0]
    assert before_without_timestamp[1].split(b"\n", 1)[1] == after_without_timestamp[1].split(
        b"\n", 1
    )[1]


def test_ac22_pending_lifecycle_and_failures(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, pending=["CHAT-000001"])
    assert _values(target)["pending_upstream"] == ["CHAT-000001"]
    assert _failure(root, pending=["CHAT-000001"]).code == "E_REVISE_PENDING_INVALID"
    assert _failure(root, pending=["RAW-000002"]).code == "E_REVISE_PENDING_INVALID"
    assert (
        _failure(root, pending=["CHAT-999999"]).code
        == "E_REVISE_PENDING_UNRESOLVED"
    )
    _revise(
        root,
        add_parents=["RAW-000002"],
        pending=["RAW-000002"],
        clear_pending=["CHAT-000001"],
    )
    assert _values(target)["pending_upstream"] == ["RAW-000002"]
    _revise(root, clear_pending=["RAW-000002"])
    assert "pending_upstream" not in _values(target)
    assert (
        _failure(root, clear_pending=["RAW-000002"]).code
        == "E_REVISE_PENDING_INVALID"
    )
    assert _failure(
        root,
        pending=["CHAT-000001"],
        clear_pending=["CHAT-000001"],
    ).code == "E_REVISE_PENDING_INVALID"


def test_ac27_body_decode_normalization_and_omission(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(
        root,
        body_change=True,
        body_data=b"new body\r\nsecond\r\n\r\n",
    )
    assert target.read_bytes().endswith(b"---\nnew body\nsecond\n")
    assert b'title: "Quoted title" # keep this comment\n' in target.read_bytes()
    _revise(root, body_change=True, body_data=b" \t\r\n")
    assert target.read_bytes().rstrip().endswith(b"---")
    before_body = target.read_bytes().split(b"---\n", 2)[-1]
    _revise(root, body_change=True, body_data=None)
    assert target.read_bytes().split(b"---\n", 2)[-1] == before_body
    before = _snapshot(root)
    failure = _failure(root, body_change=True, body_data=b"\xff\xfe")
    assert (failure.code, failure.exit_code) == ("E_REVISE_BODY_NOT_TEXT", 1)
    assert _snapshot(root) == before


def test_ac32_no_changes_and_target_errors(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    with pytest.raises(ReviseFailure) as raised:
        prepare_revise(ReviseRequest(ref="KB-000001", kb_root=root))
    assert (raised.value.code, raised.value.exit_code) == (
        "E_REVISE_NO_CHANGES",
        2,
    )
    assert (
        _failure(root, ref="KB-999999", status="current").code
        == "E_REVISE_TARGET_UNRESOLVED"
    )
    assert (
        _failure(root, ref="RAW-000002", status="current").code
        == "E_REVISE_TARGET_INVALID"
    )
    assert (
        _failure(root, ref="synthetic/index.md", status="current").code
        == "E_REVISE_TARGET_INVALID"
    )


def test_ac34_noneditable_shapes_and_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    for offset, replacement in enumerate(
        [
            TARGET.replace(
                "derived_from:\n- CHAT-000001", "derived_from: CHAT-000001"
            ),
            TARGET.replace(
                "description: A concise note.\n",
                "description: First.\ndescription: Second.\n",
            ),
        ]
    ):
        root, target = _base(tmp_path / str(offset))
        target.write_text(replacement, encoding="utf-8")
        assert _failure(root, status="current").code == "E_REVISE_NOT_EDITABLE"


def test_ac36_malformed_scan_blocks_and_names_path(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    _write(root, "synthetic/bad.md", "---\nid: KB-000099\n---\nbad\n")
    before = _snapshot(root)
    with pytest.raises(ReviseFailure) as raised:
        prepare_revise(
            ReviseRequest(ref="KB-000001", status="current", kb_root=root)
        )
    assert (raised.value.code, raised.value.exit_code) == (
        "E_REVISE_MALFORMED",
        2,
    )
    assert "synthetic/bad.md" in raised.value.message
    assert _snapshot(root) == before


def test_ac38_indexes_and_kb_are_untouched_on_preflight_failure(
    tmp_path: Path,
) -> None:
    root, _ = _base(tmp_path)
    indexes = {path: path.read_bytes() for path in root.rglob("index.md")}
    before = _snapshot(root)
    assert (
        _failure(root, links=["references=KB-999999"]).code
        == "E_REVISE_LINK_UNRESOLVED"
    )
    assert _snapshot(root) == before
    _revise(root, status="current")
    assert {path: path.read_bytes() for path in root.rglob("index.md")} == indexes


def test_ac40_core_result_and_failure_shapes_are_typed(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    result = _revise(root, status="current")
    assert result.model_dump() == {
        "id": "KB-000001",
        "path": "synthetic/kb-000001.md",
        "updated": ["synthetic/kb-000001.md"],
        "warnings": [],
    }
    failure = _failure(root, add_parents=["CHAT-000001"])
    assert failure.code == "E_REVISE_PARENT_DUPLICATE"
    assert isinstance(failure.message, str)
    assert failure.exit_code == 1


def test_ac41_combined_revision_is_one_log_row_with_actor(
    tmp_path: Path,
) -> None:
    root, target = _base(tmp_path)
    _revise(
        root,
        add_parents=["RAW-000002"],
        links=["references=RAW-000002"],
        status="current",
        pending=["RAW-000002"],
        body_change=True,
        body_data=b"combined\n",
        actor="agent-7",
    )
    values = _values(target)
    assert values["derived_from"][-1] == "RAW-000002"
    assert values["links"] == {"references": ["RAW-000002"]}
    assert values["pending_upstream"] == ["RAW-000002"]
    assert values["status"] == "current"
    assert target.read_bytes().endswith(b"combined\n")
    row, = _revised_rows(root)
    assert " | agent-7 | " in row


def test_ac43_target_schema_error_blocks_unrelated_error_does_not(
    tmp_path: Path,
) -> None:
    root, target = _base(tmp_path)
    target.write_text(
        TARGET.replace("description: A concise note.\n", ""),
        encoding="utf-8",
    )
    before = _snapshot(root)
    failure = _failure(root, status="current")
    assert (failure.code, failure.exit_code) == ("E_REVISE_VALIDATION", 1)
    assert "FM1_FIELD_MISSING" in failure.message
    assert _snapshot(root) == before

    target.write_text(TARGET, encoding="utf-8")
    _write(root, "synthetic/unrelated.md", _synthetic("KB-000099", []))
    assert _revise(root, status="current").id == "KB-000001"


def test_ac43_retained_target_cycle_is_validation_failure_and_atomic(
    tmp_path: Path,
) -> None:
    root, target = _base(tmp_path)
    target.write_text(
        _synthetic("KB-000001", ["CHAT-000001", "KB-000002"]),
        encoding="utf-8",
    )
    _write(
        root,
        "synthetic/kb-000002.md",
        _synthetic("KB-000002", ["CHAT-000001", "KB-000001"]),
    )
    before = _snapshot(root)
    failure = _failure(root, status="current")
    assert failure.code == "E_REVISE_VALIDATION"
    assert "DG2_CYCLE" in failure.message
    assert _snapshot(root) == before


def test_review_stale_target_replacement_is_rejected_before_mutation(
    tmp_path: Path,
) -> None:
    root, target = _base(tmp_path)
    prepared = prepare_revise(
        ReviseRequest(ref="KB-000001", status="current", kb_root=root)
    )
    target.write_text(
        _synthetic("KB-000099", ["CHAT-000001"]),
        encoding="utf-8",
    )
    after_replacement = _snapshot(root)
    with pytest.raises(ReviseFailure) as raised:
        execute_revise(prepared, None)
    assert (raised.value.code, raised.value.exit_code) == ("E_REVISE_IO", 2)
    assert _snapshot(root) == after_replacement


def test_review_unrelated_message_change_does_not_block_status_revision(
    tmp_path: Path,
) -> None:
    root, _ = _base(tmp_path)
    _write(
        root,
        "synthetic/unrelated.md",
        _synthetic(
            "KB-000099",
            ["CHAT-000001"],
            extra="supersedes: KB-000001\n",
        ),
    )
    result = _revise(root, status="current")
    assert result.id == "KB-000001"


def test_review_link_warning_dedup_uses_exact_type_equality(
    tmp_path: Path,
) -> None:
    root, target = _base(tmp_path)
    config_path = root / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["link_types"] = []
    config_path.write_text(json.dumps(config) + "\n", encoding="utf-8")
    target.write_text(
        TARGET.replace(
            "custom_key: kept\n",
            "links:\n  references:\n  - CHAT-000001\ncustom_key: kept\n",
        ),
        encoding="utf-8",
    )
    result = _revise(root, links=["ref=RAW-000002"])
    assert result.warnings == [
        "warning: link type is not declared in kb-config.json: ref",
        "warning: LINKTYPE_UNDECLARED: link type 'references' is not declared in the kb-config.json link_types vocabulary",
    ]


def test_ac02_human_flag_advances_touch_to_timestamp(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, status="current", human=True)
    values = _values(target)
    assert values["last_human_touch"] == values["timestamp"]


def test_ac04_parent_path_is_stored_as_canonical_id(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, add_parents=["raw/sources/raw-000002"])
    assert _values(target)["derived_from"][-1] == "RAW-000002"


def test_ac06_existing_parent_is_rejected(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    assert _failure(root, add_parents=["CHAT-000001"]).code == (
        "E_REVISE_PARENT_DUPLICATE"
    )


def test_ac07_unresolved_parent_is_rejected(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    assert _failure(root, add_parents=["RAW-999999"]).code == (
        "E_REVISE_PARENT_UNRESOLVED"
    )


def test_ac09_transitive_cycle_is_rejected(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    _write(
        root,
        "synthetic/kb-000002.md",
        _synthetic("KB-000002", ["CHAT-000001", "KB-000001"]),
    )
    _write(
        root,
        "synthetic/kb-000003.md",
        _synthetic("KB-000003", ["CHAT-000001", "KB-000002"]),
    )
    failure = _failure(root, add_parents=["KB-000003"])
    assert failure.code == "E_REVISE_CYCLE"


def test_ac12_existing_link_type_appends_in_prior_order(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, links=["references=CHAT-000001"])
    _revise(root, links=["references=RAW-000002"])
    assert _values(target)["links"]["references"] == [
        "CHAT-000001",
        "RAW-000002",
    ]


def test_ac13_distinct_link_types_follow_argument_order(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, links=["references=CHAT-000001", "blocks=RAW-000002"])
    assert list(_values(target)["links"]) == ["references", "blocks"]


def test_ac14_repeated_same_run_link_is_rejected(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    failure = _failure(
        root,
        links=["references=CHAT-000001", "references=CHAT-000001"],
    )
    assert failure.code == "E_REVISE_LINK_DUPLICATE"


def test_ac16_unresolved_link_is_rejected(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    assert _failure(root, links=["references=KB-999999"]).code == (
        "E_REVISE_LINK_UNRESOLVED"
    )


def test_ac18_empty_link_vocabulary_warns(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    config_path = root / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["link_types"] = []
    config_path.write_text(json.dumps(config) + "\n", encoding="utf-8")
    result = _revise(root, links=["ref=CHAT-000001"])
    assert result.warnings == [
        "warning: link type is not declared in kb-config.json: ref"
    ]


def test_ac20_superseded_target_is_invalid(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    target.write_text(
        TARGET.replace("status: draft", "status: superseded"),
        encoding="utf-8",
    )
    assert _failure(root, status="retired").code == "E_REVISE_TARGET_INVALID"


def test_ac21_same_status_is_an_idempotent_revision(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    old_timestamp = _values(target)["timestamp"]
    _revise(root, status="draft")
    assert _values(target)["status"] == "draft"
    assert _values(target)["timestamp"] != old_timestamp


def test_ac23_pending_added_parent_succeeds_in_same_run(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(
        root,
        add_parents=["RAW-000002"],
        pending=["RAW-000002"],
    )
    assert _values(target)["pending_upstream"] == ["RAW-000002"]


def test_ac24_repeated_same_run_pending_is_rejected(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    failure = _failure(
        root,
        pending=["CHAT-000001", "CHAT-000001"],
    )
    assert failure.code == "E_REVISE_PENDING_INVALID"


def test_ac25_clear_last_pending_removes_key(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, pending=["CHAT-000001"])
    _revise(root, clear_pending=["CHAT-000001"])
    assert "pending_upstream" not in _values(target)


def test_ac26_absent_clear_and_add_clear_conflict_are_rejected(
    tmp_path: Path,
) -> None:
    root, _ = _base(tmp_path)
    assert _failure(root, clear_pending=["CHAT-000001"]).code == (
        "E_REVISE_PENDING_INVALID"
    )
    assert _failure(
        root,
        pending=["CHAT-000001"],
        clear_pending=["CHAT-000001"],
    ).code == "E_REVISE_PENDING_INVALID"


def test_ac28_body_crlf_is_normalized(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, body_change=True, body_data=b"new\r\nsecond\r\n")
    assert target.read_bytes().endswith(b"---\nnew\nsecond\n")


def test_ac29_whitespace_body_is_empty(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, body_change=True, body_data=b" \t\r\n")
    assert target.read_bytes().rstrip().endswith(b"---")


def test_ac30_omitted_body_change_preserves_body_bytes(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    before_body = target.read_bytes().split(b"---\n", 2)[-1]
    _revise(root, body_change=False, body_data=None, status="current")
    assert target.read_bytes().split(b"---\n", 2)[-1] == before_body


def test_ac31_non_utf8_body_is_typed(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    failure = _failure(root, body_change=True, body_data=b"\xff\xfe")
    assert (failure.code, failure.exit_code) == ("E_REVISE_BODY_NOT_TEXT", 1)


def test_ac33_untouched_unknown_frontmatter_survives(tmp_path: Path) -> None:
    root, target = _base(tmp_path)
    _revise(root, status="current")
    assert b'title: "Quoted title" # keep this comment\n' in target.read_bytes()
    assert b"custom_key: kept\n" in target.read_bytes()


def test_ac35_non_synthetic_target_is_invalid(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    assert _failure(root, ref="RAW-000002", status="current").code == (
        "E_REVISE_TARGET_INVALID"
    )

    index = root / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "type: index\n", "type: index\nid: KB-000099\n"
        ),
        encoding="utf-8",
    )
    assert _failure(
        root, add_parents=["index.md"]
    ).code == "E_REVISE_PARENT_UNRESOLVED"

    invalid = _write(
        root,
        "raw/sources/invalid-id.md",
        RAW.replace("RAW-000002", "RAW-0000002"),
    )
    assert invalid.exists()
    assert _failure(
        root, links=["references=raw/sources/invalid-id.md"]
    ).code == "E_REVISE_LINK_UNRESOLVED"
    assert _failure(
        root, pending=["raw/sources/invalid-id.md"]
    ).code == "E_REVISE_PENDING_UNRESOLVED"


def test_referenced_document_identity_change_after_prepare_is_typed_and_atomic(
    tmp_path: Path,
) -> None:
    root, _ = _base(tmp_path)
    prepared = prepare_revise(
        ReviseRequest(
            ref="KB-000001",
            add_parents=["RAW-000002"],
            body_change=True,
            kb_root=root,
        )
    )
    referenced = root / "raw/sources/raw-000002.md"
    referenced.write_text(RAW.replace("raw body", "replacement"), encoding="utf-8")
    before = _snapshot(root)
    with pytest.raises(ReviseFailure) as raised:
        execute_revise(prepared, b"new body")
    assert (raised.value.code, raised.value.exit_code) == ("E_REVISE_IO", 2)
    assert _snapshot(root) == before


def test_referenced_document_replacement_after_validation_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, target = _base(tmp_path)
    referenced = root / "raw/sources/raw-000002.md"
    original_validate = revise_module._validate_proposed

    def validate_then_replace(*args, **kwargs):
        warnings = original_validate(*args, **kwargs)
        referenced.write_text(
            RAW.replace("raw body", "replacement"),
            encoding="utf-8",
        )
        return warnings

    monkeypatch.setattr(
        revise_module,
        "_validate_proposed",
        validate_then_replace,
    )
    prepared = prepare_revise(
        ReviseRequest(
            ref="KB-000001",
            add_parents=["RAW-000002"],
            kb_root=root,
        )
    )
    before_target = target.read_bytes()
    before_log = (root / "log.md").read_bytes()

    with pytest.raises(ReviseFailure) as raised:
        execute_revise(prepared, None)

    assert (raised.value.code, raised.value.exit_code) == ("E_REVISE_IO", 2)
    assert target.read_bytes() == before_target
    assert (root / "log.md").read_bytes() == before_log


def test_validation_uses_captured_referenced_document_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, target = _base(tmp_path)
    referenced = root / "raw/sources/raw-000002.md"
    original_snapshot = revise_module._snapshot_document

    def replace_then_snapshot(prepared, document):
        if document.path == Path("raw/sources/raw-000002.md"):
            referenced.write_text(
                RAW.replace("RAW-000002", "RAW-000099"),
                encoding="utf-8",
            )
        return original_snapshot(prepared, document)

    monkeypatch.setattr(
        revise_module,
        "_snapshot_document",
        replace_then_snapshot,
    )
    before_target = target.read_bytes()
    before_log = (root / "log.md").read_bytes()

    with pytest.raises(ReviseFailure) as raised:
        prepare_revise(
            ReviseRequest(
                ref="KB-000001",
                add_parents=["RAW-000002"],
                kb_root=root,
            )
        )

    assert (raised.value.code, raised.value.exit_code) == (
        "E_REVISE_VALIDATION",
        1,
    )
    assert "LINK_UNRESOLVED" in raised.value.message
    assert target.read_bytes() == before_target
    assert (root / "log.md").read_bytes() == before_log


def test_ac37_revised_log_row_starts_with_target_path(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    _revise(root, status="current", actor="reviewer")
    row, = _revised_rows(root)
    assert " | reviewer | KB-000001 | synthetic/kb-000001.md" in row


def test_ac39_each_representative_preflight_failure_preserves_kb_bytes(
    tmp_path: Path,
) -> None:
    cases = (
        {"add_parents": ["RAW-999999"]},
        {"links": ["references=RAW-999999"]},
        {"pending": ["RAW-999999"]},
        {"clear_pending": ["CHAT-000001"]},
        {"body_change": True, "body_data": b"\xff"},
        {"status": "current"},
    )
    for offset, options in enumerate(cases):
        root, target = _base(tmp_path / str(offset))
        if options == {"status": "current"}:
            target.write_text(
                TARGET.replace("description: A concise note.\n", ""),
                encoding="utf-8",
            )
        before = _snapshot(root)
        failure = _failure(root, **options)
        assert failure.exit_code in (1, 2)
        assert _snapshot(root) == before


def test_ac42_actor_is_written_to_revised_log(tmp_path: Path) -> None:
    root, _ = _base(tmp_path)
    _revise(root, status="current", actor="reviewer")
    assert " | reviewer | " in _revised_rows(root)[0]
