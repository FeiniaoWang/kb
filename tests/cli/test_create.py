from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import pytest
import yaml

TIMESTAMP = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
BASE_ARGS = (
    "--type", "spec",
    "--title", "Webhook Retry Policy",
    "--description", "Defines retry and backoff behavior for outbound webhooks.",
    "--derived-from", "CHAT-000001",
)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def changed(before: dict[str, bytes], after: dict[str, bytes]) -> set[str]:
    return {
        path
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    }


def write_doc(
    root: Path,
    relative: str,
    frontmatter: str,
    body: str = "body\n",
    *,
    newline: str = "\n",
) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"---\n{frontmatter}---\n{body}".replace("\n", newline)
    path.write_bytes(text.encode("utf-8"))
    return path


def add_chat(root: Path, doc_id: str = "CHAT-000001") -> Path:
    return write_doc(
        root,
        "raw/chats/planning.md",
        f"id: {doc_id}\ntype: chat\ningested_at: 2026-07-16T09:00:00Z\norigin: stdin\ntitle: Planning\n",
    )


def split_document(path: Path) -> tuple[dict[str, object], str, str]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        text = stream.read()
    assert text.startswith("---")
    _, yaml_text, remainder = text.split("---", 2)
    parsed = yaml.safe_load(yaml_text)
    assert isinstance(parsed, dict)
    return parsed, remainder.removeprefix("\n"), yaml_text


def invoke_valid(invoke_create, root: Path, *extra: str, input=None):
    return invoke_create(root, *BASE_ARGS, *extra, input=input)


def test_ac01_default_create_writes_pinned_frontmatter_and_only_expected_files(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb)
    after = snapshot(initialized_kb)
    path = initialized_kb / "synthetic/webhook-retry-policy.md"
    frontmatter, body, yaml_text = split_document(path)
    assert result.exit_code == 0
    assert list(frontmatter) == [
        "id", "type", "title", "description", "status", "derived_from",
        "timestamp", "last_human_touch",
    ]
    assert frontmatter | {"timestamp": "ignored", "last_human_touch": "ignored"} == {
        "id": "KB-000001",
        "type": "spec",
        "title": "Webhook Retry Policy",
        "description": "Defines retry and backoff behavior for outbound webhooks.",
        "status": "draft",
        "derived_from": ["CHAT-000001"],
        "timestamp": "ignored",
        "last_human_touch": "ignored",
    }
    assert "derived_from:\n  - CHAT-000001\n" in yaml_text
    assert body == ""
    assert changed(before, after) == {
        "log.md", "synthetic/index.md", "synthetic/webhook-retry-policy.md"
    }


def test_ac02_creation_timestamps_are_equal_utc_seconds(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    assert invoke_valid(invoke_create, initialized_kb).exit_code == 0
    frontmatter, _, yaml_text = split_document(
        initialized_kb / "synthetic/webhook-retry-policy.md"
    )
    assert frontmatter["timestamp"] == frontmatter["last_human_touch"]
    timestamp = re.search(rf"(?m)^timestamp: ({TIMESTAMP})$", yaml_text)
    touched = re.search(rf"(?m)^last_human_touch: ({TIMESTAMP})$", yaml_text)
    assert timestamp is not None and touched is not None
    assert timestamp.group(1) == touched.group(1)
    datetime.fromisoformat(timestamp.group(1).replace("Z", "+00:00"))


def test_ac03_body_normalizes_only_line_endings_and_trailing_newline(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    body_file = tmp_path / "body.md"
    body_file.write_bytes("---\r\nUnicode café  \rlast".encode())
    result = invoke_valid(
        invoke_create, initialized_kb, "--body-file", str(body_file)
    )
    assert result.exit_code == 0
    assert split_document(
        initialized_kb / "synthetic/webhook-retry-policy.md"
    )[1] == "---\nUnicode café  \nlast\n"


def test_ac04_omitted_or_whitespace_body_ends_at_closing_delimiter(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    omitted = invoke_valid(invoke_create, initialized_kb)
    assert omitted.exit_code == 0
    assert (initialized_kb / "synthetic/webhook-retry-policy.md").read_bytes().endswith(b"---")
    blank = tmp_path / "blank.md"
    blank.write_text(" \t\r\n", encoding="utf-8", newline="")
    second = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Blank", "--description", "Blank.",
        "--derived-from", "CHAT-000001", "--body-file", str(blank),
    )
    assert second.exit_code == 0
    assert (initialized_kb / "synthetic/blank.md").read_bytes().endswith(b"---")


def test_ac05_stdin_body_is_normalized_and_written(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    result = invoke_valid(
        invoke_create, initialized_kb, "--body-file", "-", input="one\r\ntwo"
    )
    assert result.exit_code == 0
    assert split_document(
        initialized_kb / "synthetic/webhook-retry-policy.md"
    )[1] == "one\ntwo\n"


def test_ac06_only_synthetic_index_listing_and_frontmatter_are_correct(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    indexes = {path: path.read_bytes() for path in initialized_kb.rglob("index.md")}
    description = split_document(initialized_kb / "synthetic/index.md")[0]["description"]
    assert invoke_valid(invoke_create, initialized_kb).exit_code == 0
    index = (initialized_kb / "synthetic/index.md").read_text(encoding="utf-8")
    assert "* [KB-000001][Webhook Retry Policy](webhook-retry-policy.md) - Defines retry and backoff behavior for outbound webhooks." in index
    assert split_document(initialized_kb / "synthetic/index.md")[0]["description"] == description
    assert all(
        path.read_bytes() == content
        for path, content in indexes.items()
        if path != initialized_kb / "synthetic/index.md"
    )


def test_ac07_create_appends_exact_default_actor_log_entry(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    assert invoke_valid(invoke_create, initialized_kb).exit_code == 0
    last = (initialized_kb / "log.md").read_text(encoding="utf-8").splitlines()[-1]
    match = re.fullmatch(
        rf"- ({TIMESTAMP}) \| created \| kb-cli \| KB-000001 \| synthetic/webhook-retry-policy.md",
        last,
    )
    assert match is not None
    datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))


def test_ac08_text_output_sorts_changes_then_prints_result(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb)
    assert result.stdout.splitlines() == [
        "updated  synthetic/index.md",
        "created  synthetic/webhook-retry-policy.md",
        "created KB-000001 as synthetic/webhook-retry-policy.md",
    ]


def test_ac09_current_status_is_accepted_at_creation(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb, "--status", "current")
    assert result.exit_code == 0
    assert split_document(
        initialized_kb / "synthetic/webhook-retry-policy.md"
    )[0]["status"] == "current"


def test_ac10_synthetic_id_is_max_plus_one_without_gap_reuse(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    write_doc(initialized_kb, "synthetic/one.md", "id: KB-000001\ntype: spec\nstatus: draft\n")
    write_doc(initialized_kb, "synthetic/five.md", "id: KB-000005\ntype: spec\nstatus: current\n")
    assert invoke_valid(invoke_create, initialized_kb).exit_code == 0
    assert split_document(
        initialized_kb / "synthetic/webhook-retry-policy.md"
    )[0]["id"] == "KB-000006"


def test_ac11_custom_and_missing_synthetic_prefix_use_config_contract(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["id_prefixes"]["synthetic"] = "SYN"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    assert invoke_valid(invoke_create, initialized_kb).exit_code == 0
    assert split_document(initialized_kb / "synthetic/webhook-retry-policy.md")[0]["id"] == "SYN-000001"
    (initialized_kb / "synthetic/webhook-retry-policy.md").unlink()
    config.pop("id_prefixes")
    config_path.write_text(json.dumps(config), encoding="utf-8")
    assert invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Default", "--description", "Default.",
        "--derived-from", "CHAT-000001",
    ).exit_code == 0
    assert split_document(initialized_kb / "synthetic/default.md")[0]["id"] == "KB-000001"


def test_ac12_malformed_scan_blocks_all_writes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    write_doc(initialized_kb, "synthetic/bad.md", "type: [\n")
    before = snapshot(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb)
    assert result.exit_code == 2
    assert "E_CREATE_MALFORMED" in result.stderr
    assert "synthetic/bad.md" in result.stderr
    assert "kb validate" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac13_parent_order_is_preserved_across_document_classes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    write_doc(initialized_kb, "raw/sources/source.md", "id: RAW-000002\ntype: raw-source\n")
    write_doc(initialized_kb, "synthetic/old.md", "id: KB-000001\ntype: spec\nstatus: current\n")
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Ordered", "--description", "Ordered.",
        "--derived-from", "RAW-000002", "--derived-from", "CHAT-000001",
        "--derived-from", "KB-000001",
    )
    assert result.exit_code == 0
    assert split_document(initialized_kb / "synthetic/ordered.md")[0]["derived_from"] == [
        "RAW-000002", "CHAT-000001", "KB-000001"
    ]


def test_ac14_duplicate_parents_keep_first_occurrence(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    write_doc(initialized_kb, "raw/sources/source.md", "id: RAW-000002\ntype: raw-source\n")
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Unique", "--description", "Unique.",
        "--derived-from", "CHAT-000001", "--derived-from", "RAW-000002",
        "--derived-from", "CHAT-000001",
    )
    assert result.exit_code == 0
    assert split_document(initialized_kb / "synthetic/unique.md")[0]["derived_from"] == [
        "CHAT-000001", "RAW-000002"
    ]


def test_ac15_path_and_reserved_slug_parents_store_canonical_ids(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    first = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Paths", "--description", "Paths.",
        "--derived-from", "raw/chats/planning.md",
        "--derived-from", "governance/conventions.md",
    )
    assert first.exit_code == 0
    assert split_document(initialized_kb / "synthetic/paths.md")[0]["derived_from"] == [
        "CHAT-000001", "GOVERNANCE-CONVENTIONS"
    ]


def test_ac16_unknown_parent_id_is_reference_finding_without_writes(
    initialized_kb, invoke_create
) -> None:
    before = snapshot(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Bad", "--description", "Bad.",
        "--derived-from", "KB-999999",
    )
    assert result.exit_code == 1
    assert "E_CREATE_PARENT_UNRESOLVED" in result.stderr
    assert "KB-999999" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac17_index_parent_without_id_is_reference_finding(
    initialized_kb, invoke_create
) -> None:
    before = snapshot(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Bad", "--description", "Bad.",
        "--derived-from", "index.md",
    )
    assert result.exit_code == 1
    assert "E_CREATE_PARENT_UNRESOLVED" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac18_no_parent_is_usage_failure_without_writes(
    initialized_kb, invoke_create
) -> None:
    before = snapshot(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Orphan", "--description", "Orphan.",
    )
    assert result.exit_code == 2
    assert "E_CREATE_NO_PARENTS" in result.stderr
    assert snapshot(initialized_kb) == before
