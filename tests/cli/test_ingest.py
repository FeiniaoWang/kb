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


def test_ac12_origin_override_accepts_url_and_label(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "page.html"
    source.write_text("page", encoding="utf-8")
    first = ingest_file(
        invoke_ingest,
        initialized_kb,
        source,
        "--origin",
        "https://example.com/post",
    )
    parsed = split_document(initialized_kb / "raw/sources/page.md")[0]
    assert first.exit_code == 0
    assert parsed["origin"] == "https://example.com/post"
    assert (
        initialized_kb / "log.md"
    ).read_text(encoding="utf-8").splitlines()[-1].endswith(
        "from https://example.com/post"
    )
    second = invoke_ingest(
        initialized_kb,
        "--class",
        "chat",
        "--from",
        "stdin",
        "--origin",
        "meeting recording",
        input="chat",
    )
    assert second.exit_code == 0
    assert split_document(initialized_kb / "raw/chats/chat-000001.md")[0][
        "origin"
    ] == "meeting recording"


def test_ac13_explicit_title_is_verbatim_and_drives_slug(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "x.md"
    source.write_text("x", encoding="utf-8")
    result = ingest_file(
        invoke_ingest, initialized_kb, source, "--title", "Meeting Notes!"
    )
    assert result.exit_code == 0
    assert split_document(initialized_kb / "raw/sources/meeting-notes.md")[0][
        "title"
    ] == "Meeting Notes!"


def test_ac14_file_stem_derives_slug_and_title(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "q3_planning-notes.md"
    source.write_text("x", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    assert split_document(initialized_kb / "raw/sources/q3-planning-notes.md")[0][
        "title"
    ] == "q3 planning notes"


def test_ac15_collision_suffixes_without_overwrite(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    existing = write_existing(
        initialized_kb,
        "raw/sources/notes.md",
        "id: RAW-000001\ntype: raw-source\ntitle: Notes\n",
    )
    before = existing.read_bytes()
    source = tmp_path / "notes.md"
    source.write_text("new", encoding="utf-8")
    result = ingest_file(invoke_ingest, initialized_kb, source)
    assert result.exit_code == 0
    assert (initialized_kb / "raw/sources/notes-raw-000002.md").is_file()
    assert existing.read_bytes() == before


def test_ac16_empty_slug_falls_back_to_lowercase_id(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "x.md"
    source.write_text("x", encoding="utf-8")
    assert (
        ingest_file(invoke_ingest, initialized_kb, source, "--title", "!!!").exit_code
        == 0
    )
    assert (initialized_kb / "raw/sources/raw-000001.md").is_file()


def test_ac17_unicode_title_ascii_folds_for_filename(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "x.md"
    source.write_text("x", encoding="utf-8")
    assert (
        ingest_file(
            invoke_ingest,
            initialized_kb,
            source,
            "--title",
            "Résumé Über 2026",
        ).exit_code
        == 0
    )
    assert (initialized_kb / "raw/sources/resume-uber-2026.md").is_file()
    assert split_document(initialized_kb / "raw/sources/resume-uber-2026.md")[0][
        "title"
    ] == "Résumé Über 2026"


def test_ac18_identical_reingest_allocates_and_suffixes(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "same.md"
    source.write_text("same", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    first = (initialized_kb / "raw/sources/same.md").read_bytes()
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    assert split_document(initialized_kb / "raw/sources/same.md")[0]["id"] == (
        "RAW-000001"
    )
    assert split_document(initialized_kb / "raw/sources/same-raw-000002.md")[0][
        "id"
    ] == "RAW-000002"
    assert (initialized_kb / "raw/sources/same.md").read_bytes() == first


def test_ac19_stdin_defaults_to_id_name_title_and_origin(
    initialized_kb, invoke_ingest
) -> None:
    result = invoke_ingest(
        initialized_kb, "--class", "source", "--from", "stdin", input="piped"
    )
    frontmatter, body, _ = split_document(
        initialized_kb / "raw/sources/raw-000001.md"
    )
    assert result.exit_code == 0
    assert frontmatter["origin"] == "stdin"
    assert frontmatter["title"] == "RAW-000001"
    assert body == "piped\n"


def clipboard_tool(directory: Path, body: str, *, exit_code: int = 0) -> Path:
    tool = directory / "pbpaste"
    tool.write_text(
        f"#!/bin/sh\nprintf '%s' '{body}'\nexit {exit_code}\n", encoding="utf-8"
    )
    tool.chmod(0o755)
    return tool


def test_ac20_clipboard_adapter_reads_tool_stdout(
    initialized_kb, tmp_path, invoke_ingest, monkeypatch
) -> None:
    clipboard_tool(tmp_path, "clipboard text")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr("kb.core.ingest.platform.system", lambda: "Darwin")
    result = invoke_ingest(
        initialized_kb, "--class", "chat", "--from", "clipboard"
    )
    frontmatter, body, _ = split_document(
        initialized_kb / "raw/chats/chat-000001.md"
    )
    assert result.exit_code == 0
    assert frontmatter["origin"] == "clipboard"
    assert body == "clipboard text\n"


def test_ac21_clipboard_missing_or_nonzero_is_environment_error(
    initialized_kb, tmp_path, invoke_ingest, monkeypatch
) -> None:
    monkeypatch.setattr("kb.core.ingest.platform.system", lambda: "Darwin")
    monkeypatch.setenv("PATH", "")
    before = snapshot(initialized_kb)
    missing = invoke_ingest(
        initialized_kb, "--class", "chat", "--from", "clipboard"
    )
    assert missing.exit_code == 2 and "E_INGEST_CLIPBOARD" in missing.stderr
    clipboard_tool(tmp_path, "", exit_code=9)
    monkeypatch.setenv("PATH", str(tmp_path))
    nonzero = invoke_ingest(
        initialized_kb, "--class", "chat", "--from", "clipboard"
    )
    assert nonzero.exit_code == 2 and "E_INGEST_CLIPBOARD" in nonzero.stderr
    assert snapshot(initialized_kb) == before


def test_ac22_non_utf8_stdin_and_clipboard_are_findings(
    initialized_kb, tmp_path, invoke_ingest, monkeypatch
) -> None:
    before = snapshot(initialized_kb)
    stdin = invoke_ingest(
        initialized_kb,
        "--class",
        "source",
        "--from",
        "stdin",
        input=b"\xff",
    )
    assert stdin.exit_code == 1 and "E_INGEST_NOT_TEXT" in stdin.stderr
    monkeypatch.setattr(
        "kb.core.ingest.ADAPTERS",
        {
            **__import__("kb.core.ingest", fromlist=["ADAPTERS"]).ADAPTERS,
            "clipboard": lambda _: __import__(
                "kb.core.ingest", fromlist=["AdapterPayload"]
            ).AdapterPayload(
                data=b"\xff", default_origin="clipboard", source_filename=None
            ),
        },
    )
    clipboard = invoke_ingest(
        initialized_kb, "--class", "chat", "--from", "clipboard"
    )
    assert clipboard.exit_code == 1 and "E_INGEST_NOT_TEXT" in clipboard.stderr
    assert snapshot(initialized_kb) == before


def test_ac23_whitespace_file_and_empty_stdin_are_findings(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "blank.md"
    source.write_text(" \t\r\n", encoding="utf-8")
    before = snapshot(initialized_kb)
    file_result = ingest_file(invoke_ingest, initialized_kb, source)
    stdin_result = invoke_ingest(
        initialized_kb, "--class", "source", "--from", "stdin", input=""
    )
    assert file_result.exit_code == stdin_result.exit_code == 1
    assert "E_INGEST_EMPTY" in file_result.stderr
    assert "E_INGEST_EMPTY" in stdin_result.stderr
    assert snapshot(initialized_kb) == before
