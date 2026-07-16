from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import yaml

TIMESTAMP = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


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


def split_document(path: Path) -> tuple[dict[str, object], str, str]:
    text = path.read_text(encoding="utf-8")
    opening, yaml_text, body = text.split("---", 2)
    assert opening == ""
    parsed = yaml.safe_load(yaml_text)
    assert isinstance(parsed, dict)
    return parsed, body.removeprefix("\n"), yaml_text


def write_existing(
    root: Path, relative: str, frontmatter: str, body: str = "body\n"
) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return path


def ingest_file(invoke_ingest, root: Path, source: Path, *extra: str):
    return invoke_ingest(
        root,
        "--class",
        "source",
        "--from",
        "file",
        str(source),
        *extra,
    )


def test_ac01_file_ingest_writes_exact_raw_frontmatter_and_only_expected_changes(
    tmp_path, initialized_kb, invoke_ingest
) -> None:
    source = tmp_path / "meeting_notes.md"
    source.write_text("hello\n", encoding="utf-8")
    before = snapshot(initialized_kb)
    result = ingest_file(invoke_ingest, initialized_kb, source)
    after = snapshot(initialized_kb)
    document = initialized_kb / "raw/sources/meeting-notes.md"
    frontmatter, body, yaml_text = split_document(document)
    assert result.exit_code == 0
    assert list(frontmatter) == ["id", "type", "ingested_at", "origin", "title"]
    assert frontmatter | {"ingested_at": "ignored"} == {
        "id": "RAW-000001",
        "type": "raw-source",
        "ingested_at": "ignored",
        "origin": str(source.resolve()),
        "title": "meeting notes",
    }
    datetime.fromisoformat(str(frontmatter["ingested_at"]).replace("Z", "+00:00"))
    assert body == "hello\n"
    assert changed(before, after) == {
        "log.md",
        "raw/sources/index.md",
        "raw/sources/meeting-notes.md",
    }


def test_ac02_lf_body_is_otherwise_byte_identical(
    tmp_path, initialized_kb, invoke_ingest
) -> None:
    source = tmp_path / "tricky.md"
    expected = "---\nUnicode café  \nlast\n"
    source.write_text(expected, encoding="utf-8", newline="")
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    assert split_document(initialized_kb / "raw/sources/tricky.md")[1] == expected


def test_ac03_crlf_and_cr_normalize_to_lf_and_one_trailing_newline(
    tmp_path, initialized_kb, invoke_ingest
) -> None:
    source = tmp_path / "mixed.md"
    source.write_bytes(b"one\r\ntwo\rthree")
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    assert split_document(initialized_kb / "raw/sources/mixed.md")[1] == (
        "one\ntwo\nthree\n"
    )


def test_ac04_only_target_index_listing_changes(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "meeting_notes.md"
    source.write_text("hello", encoding="utf-8")
    indexes = {path: path.read_bytes() for path in initialized_kb.rglob("index.md")}
    description = split_document(initialized_kb / "raw/sources/index.md")[0][
        "description"
    ]
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    text = (initialized_kb / "raw/sources/index.md").read_text(encoding="utf-8")
    assert "* [RAW-000001][meeting notes](meeting-notes.md)" in text
    assert " - " not in text.split("## Files\n", 1)[1]
    assert (
        split_document(initialized_kb / "raw/sources/index.md")[0]["description"]
        == description
    )
    assert all(
        path.read_bytes() == content
        for path, content in indexes.items()
        if path.name == "index.md" and path != initialized_kb / "raw/sources/index.md"
    )


def test_ac05_ingest_appends_exact_log_entry(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "meeting_notes.md"
    source.write_text("hello", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    last = (initialized_kb / "log.md").read_text(encoding="utf-8").splitlines()[-1]
    match = re.fullmatch(
        rf"- ({TIMESTAMP}) \| ingested \| kb-cli \| RAW-000001 \| "
        rf"raw/sources/meeting-notes.md from {re.escape(str(source.resolve()))}",
        last,
    )
    assert match is not None
    datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))


def test_ac06_text_output_is_sorted_then_has_result_line(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "meeting_notes.md"
    source.write_text("hello", encoding="utf-8")
    result = ingest_file(invoke_ingest, initialized_kb, source)
    assert result.stdout.splitlines() == [
        "created  raw/sources/meeting-notes.md",
        "updated  raw/sources/index.md",
        "ingested RAW-000001 as raw/sources/meeting-notes.md",
    ]


def test_ac07_explicit_kb_chat_stdin_uses_chat_class(
    tmp_path, initialized_kb, invoke_ingest
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    result = invoke_ingest(
        outside,
        "--class",
        "chat",
        "--from",
        "stdin",
        "--kb",
        str(initialized_kb),
        input="chat body",
    )
    frontmatter, _, _ = split_document(initialized_kb / "raw/chats/chat-000001.md")
    assert result.exit_code == 0
    assert frontmatter["id"] == "CHAT-000001"
    assert frontmatter["type"] == "chat"


def test_ac08_feedback_uses_feedback_id_and_about_last(
    initialized_kb, invoke_ingest
) -> None:
    write_existing(
        initialized_kb,
        "synthetic/webhook.md",
        "id: KB-000007\ntype: coding-spec\ntitle: Webhook\n",
    )
    result = invoke_ingest(
        initialized_kb,
        "--class",
        "feedback",
        "--from",
        "stdin",
        "--about",
        "KB-000007",
        input="feedback",
    )
    frontmatter, _, _ = split_document(initialized_kb / "raw/feedback/feed-000001.md")
    assert result.exit_code == 0
    assert frontmatter["id"] == "FEED-000001"
    assert frontmatter["type"] == "feedback"
    assert list(frontmatter)[-1] == "about"
    assert frontmatter["about"] == "KB-000007"


def test_ac09_id_allocation_is_max_plus_one(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    write_existing(
        initialized_kb,
        "raw/sources/one.md",
        "id: RAW-000001\ntype: raw-source\n",
    )
    write_existing(
        initialized_kb,
        "raw/sources/five.md",
        "id: RAW-000005\ntype: raw-source\n",
    )
    source = tmp_path / "six.md"
    source.write_text("six", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    assert split_document(initialized_kb / "raw/sources/six.md")[0]["id"] == (
        "RAW-000006"
    )


def test_ac10_custom_and_missing_prefix_configuration(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["id_prefixes"]["source"] = "SRC"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    first = tmp_path / "first.md"
    first.write_text("one", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, first).exit_code == 0
    assert split_document(initialized_kb / "raw/sources/first.md")[0]["id"] == (
        "SRC-000001"
    )
    config.pop("id_prefixes")
    config_path.write_text(json.dumps(config), encoding="utf-8")
    second = tmp_path / "second.md"
    second.write_text("two", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, second).exit_code == 0
    assert split_document(initialized_kb / "raw/sources/second.md")[0]["id"] == (
        "RAW-000001"
    )


def test_ac11_malformed_scan_blocks_all_writes(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    write_existing(initialized_kb, "raw/sources/bad.md", "type: [\n")
    source = tmp_path / "new.md"
    source.write_text("new", encoding="utf-8")
    before = snapshot(initialized_kb)
    result = ingest_file(invoke_ingest, initialized_kb, source)
    assert result.exit_code == 2
    assert "E_INGEST_MALFORMED" in result.stderr
    assert "raw/sources/bad.md" in result.stderr
    assert "kb validate" in result.stderr
    assert snapshot(initialized_kb) == before
