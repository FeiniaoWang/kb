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
