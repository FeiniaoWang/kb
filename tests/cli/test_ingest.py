from __future__ import annotations

import errno
import json
import os
import re
import shutil
import stat
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from kb.core.scan import scan

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
    initialized_kb, tmp_path, invoke_ingest, monkeypatch
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

    from typer.testing import CliRunner
    from kb.cli.app import app

    index_source = tmp_path / "index.md"
    index_source.write_text("new nested evidence", encoding="utf-8")
    for json_output in (False, True):
        nested_root = tmp_path / f"nested-text-{'json' if json_output else 'text'}"
        assert (
            CliRunner().invoke(app, ["init", "--root", str(nested_root)]).exit_code
            == 0
        )
        arguments = ["--dest", "a/b"]
        if json_output:
            arguments.append("--json")
        nested = ingest_file(
            invoke_ingest,
            nested_root,
            index_source,
            *arguments,
        )
        document_relative = "raw/sources/a/b/index-raw-000001.md"
        nested_index = nested_root / "raw/sources/a/b/index.md"
        created = [
            document_relative,
            "raw/sources/a/b/index.md",
            "raw/sources/a/index.md",
        ]
        assert nested.exit_code == 0
        assert (nested_root / document_relative).is_file()
        assert "[index](index-raw-000001.md)" in nested_index.read_text(
            encoding="utf-8"
        )
        if json_output:
            assert json.loads(nested.stdout) == {
                "ok": True,
                "id": "RAW-000001",
                "path": document_relative,
                "original": None,
                "created": created,
                "updated": ["raw/sources/index.md"],
            }
        else:
            assert nested.stdout.splitlines() == [
                *(f"created  {path}" for path in created),
                "updated  raw/sources/index.md",
                f"ingested RAW-000001 as {document_relative}",
            ]

    import kb.core.ingest as ingest_core

    real_prepare = ingest_core.prepare_write
    prepared_births: list[Path] = []

    def record_birth(context, intent):
        prepared_births.append(intent.birth.path)
        return real_prepare(context, intent)

    monkeypatch.setattr(ingest_core, "prepare_write", record_birth)
    source_before = index_source.read_bytes()
    for json_output in (False, True):
        damaged_root = tmp_path / f"damaged-ingest-{'json' if json_output else 'text'}"
        assert (
            CliRunner().invoke(app, ["init", "--root", str(damaged_root)]).exit_code
            == 0
        )
        damaged = damaged_root / "raw/sources/damaged"
        damaged.mkdir()
        before_damaged = snapshot(damaged_root)
        arguments = ["--dest", "damaged"]
        if json_output:
            arguments.append("--json")

        result = ingest_file(
            invoke_ingest,
            damaged_root,
            index_source,
            *arguments,
        )

        assert result.exit_code == 2
        assert isinstance(result.exception, SystemExit)
        if json_output:
            assert json.loads(result.stdout)["error"]["code"] == "E_INGEST_IO"
            assert result.stderr == ""
        else:
            assert "E_INGEST_IO" in result.stderr
            assert result.stdout == ""
        assert prepared_births[-1] == Path(
            "raw/sources/damaged/index-raw-000001.md"
        )
        assert snapshot(damaged_root) == before_damaged
        assert index_source.read_bytes() == source_before


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
    monkeypatch.setattr("kb.cli.ingest_adapters.platform.system", lambda: "Darwin")
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
    monkeypatch.setattr("kb.cli.ingest_adapters.platform.system", lambda: "Darwin")
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
        "kb.cli.ingest_adapters._ADAPTERS",
        {
            **__import__(
                "kb.cli.ingest_adapters", fromlist=["_ADAPTERS"]
            )._ADAPTERS,
            "clipboard": lambda _: __import__(
                "kb.core.ingest", fromlist=["AdapterPayload"]
            ).AdapterPayload(
                source_kind="clipboard",
                data=b"\xff",
                default_origin="clipboard",
                source_filename=None,
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


def test_ac24_binary_file_creates_byte_identical_original_and_exact_stub(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "Q3 Report.pdf"
    source.write_bytes(b"%PDF-\xff\x00")
    result = ingest_file(invoke_ingest, initialized_kb, source, "--title", "Q3 Report")
    original = initialized_kb / "raw/sources/q3-report.pdf"
    stub = initialized_kb / "raw/sources/q3-report.md"
    assert result.exit_code == 0
    frontmatter, body, _ = split_document(stub)
    assert original.read_bytes() == source.read_bytes()
    assert list(frontmatter) == ["id", "type", "ingested_at", "origin", "title"]
    assert body == "Non-text original stored alongside this stub: [q3-report.pdf](q3-report.pdf)\n"
    assert result.stdout.splitlines()[:2] == [
        "created  raw/sources/q3-report.md",
        "created  raw/sources/q3-report.pdf",
    ]


def test_ac25_binary_collision_suffixes_both_files(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    write_existing(initialized_kb, "raw/sources/q3-report.md", "id: RAW-000001\ntype: raw-source\n")
    source = tmp_path / "Q3 Report.pdf"
    source.write_bytes(b"\xffbinary")
    result = ingest_file(invoke_ingest, initialized_kb, source, "--title", "Q3 Report")
    assert result.exit_code == 0
    assert (initialized_kb / "raw/sources/q3-report-raw-000002.pdf").read_bytes() == source.read_bytes()
    assert split_document(initialized_kb / "raw/sources/q3-report-raw-000002.md")[1] == (
        "Non-text original stored alongside this stub: "
        "[q3-report-raw-000002.pdf](q3-report-raw-000002.pdf)\n"
    )

    from typer.testing import CliRunner
    from kb.cli.app import app

    index_source = tmp_path / "index.pdf"
    index_source.write_bytes(b"%PDF-index-\xff\x00")
    for json_output in (False, True):
        nested_root = tmp_path / f"nested-binary-{'json' if json_output else 'text'}"
        assert (
            CliRunner().invoke(app, ["init", "--root", str(nested_root)]).exit_code
            == 0
        )
        arguments = ["--dest", "a/b"]
        if json_output:
            arguments.append("--json")
        nested = ingest_file(
            invoke_ingest,
            nested_root,
            index_source,
            *arguments,
        )
        stub_relative = "raw/sources/a/b/index-raw-000001.md"
        original_relative = "raw/sources/a/b/index-raw-000001.pdf"
        stub = nested_root / stub_relative
        original = nested_root / original_relative
        index = nested_root / "raw/sources/a/b/index.md"
        assert nested.exit_code == 0
        assert nested.exception is None
        assert original.read_bytes() == index_source.read_bytes()
        assert split_document(stub)[1] == (
            "Non-text original stored alongside this stub: "
            "[index-raw-000001.pdf](index-raw-000001.pdf)\n"
        )
        assert index.read_text(encoding="utf-8") == (
            "---\ntype: index\n"
            "description: Documents under raw/sources/a/b/.\n---\n"
            "# b\n\n"
            "<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->\n\n"
            "## Files\n"
            "* [RAW-000001][index](index-raw-000001.md)\n"
        )
        created = [
            stub_relative,
            original_relative,
            "raw/sources/a/b/index.md",
            "raw/sources/a/index.md",
        ]
        if json_output:
            assert json.loads(nested.stdout) == {
                "ok": True,
                "id": "RAW-000001",
                "path": stub_relative,
                "original": original_relative,
                "created": created,
                "updated": ["raw/sources/index.md"],
            }
        else:
            assert nested.stdout.splitlines() == [
                *(f"created  {path}" for path in created),
                "updated  raw/sources/index.md",
                f"ingested RAW-000001 as {stub_relative}",
            ]


def test_ac26_index_lists_stub_but_not_binary(initialized_kb, tmp_path, invoke_ingest) -> None:
    source = tmp_path / "Q3 Report.pdf"
    source.write_bytes(b"\xffbinary")
    assert ingest_file(invoke_ingest, initialized_kb, source, "--title", "Q3 Report").exit_code == 0
    index = (initialized_kb / "raw/sources/index.md").read_text(encoding="utf-8")
    assert "* [RAW-000001][Q3 Report](q3-report.md)" in index
    assert "q3-report.pdf" not in index


def test_ac27_binary_extension_is_lowercase_absent_or_markdown_original(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    photo = tmp_path / "Photo.JPG"
    photo.write_bytes(b"\xffjpg")
    assert ingest_file(invoke_ingest, initialized_kb, photo).exit_code == 0
    assert (initialized_kb / "raw/sources/photo.jpg").is_file()
    assert "[photo.jpg](photo.jpg)" in split_document(initialized_kb / "raw/sources/photo.md")[1]
    dump = tmp_path / "dump"
    dump.write_bytes(b"\xffdump")
    assert ingest_file(invoke_ingest, initialized_kb, dump).exit_code == 0
    assert (initialized_kb / "raw/sources/dump").is_file()
    assert "[dump](dump)" in split_document(initialized_kb / "raw/sources/dump.md")[1]

    markdown = tmp_path / "Binary Note.MD"
    markdown.write_bytes(b"\xffmarkdown binary")
    first = ingest_file(invoke_ingest, initialized_kb, markdown)
    stub = initialized_kb / "raw/sources/binary-note.md"
    original = initialized_kb / "raw/sources/binary-note.md.original"
    assert first.exit_code == 0
    assert original.read_bytes() == markdown.read_bytes()
    assert split_document(stub)[1] == (
        "Non-text original stored alongside this stub: "
        "[binary-note.md.original](binary-note.md.original)\n"
    )
    document_paths = {
        document.path.as_posix() for document in scan(initialized_kb).documents
    }
    assert "raw/sources/binary-note.md" in document_paths
    assert "raw/sources/binary-note.md.original" not in document_paths
    index = (initialized_kb / "raw/sources/index.md").read_text(encoding="utf-8")
    assert "* [RAW-000003][Binary Note](binary-note.md)" in index
    assert "binary-note.md.original" not in index

    second = ingest_file(invoke_ingest, initialized_kb, markdown)
    suffixed_stub = initialized_kb / "raw/sources/binary-note-raw-000004.md"
    suffixed_original = (
        initialized_kb / "raw/sources/binary-note-raw-000004.md.original"
    )
    assert second.exit_code == 0
    assert suffixed_original.read_bytes() == markdown.read_bytes()
    assert "[binary-note-raw-000004.md.original]" in split_document(suffixed_stub)[1]


def test_binary_suffixed_collision_refuses_to_overwrite_partial_original(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    write_existing(
        initialized_kb,
        "raw/sources/q3-report.md",
        "id: RAW-000001\ntype: raw-source\n",
    )
    partial_original = initialized_kb / "raw/sources/q3-report-raw-000002.pdf"
    partial_original.write_bytes(b"partial original")
    source = tmp_path / "Q3 Report.pdf"
    source.write_bytes(b"\xffnew original")
    before = snapshot(initialized_kb)

    result = ingest_file(invoke_ingest, initialized_kb, source, "--title", "Q3 Report")

    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert partial_original.read_bytes() == b"partial original"
    assert snapshot(initialized_kb) == before


def test_ac28_new_dest_has_born_current_index_and_updates_class_index(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    untouched = {
        path: path.read_bytes()
        for path in [initialized_kb / "index.md", initialized_kb / "raw/index.md"]
    }
    result = ingest_file(invoke_ingest, initialized_kb, source, "--dest", "api")
    assert result.exit_code == 0
    index = (initialized_kb / "raw/sources/api/index.md").read_text(encoding="utf-8")
    assert index == (
        "---\ntype: index\ndescription: Documents under raw/sources/api/.\n---\n"
        "# api\n\n<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->\n\n"
        "## Files\n* [RAW-000001][doc](doc.md)\n"
    )
    parent = (initialized_kb / "raw/sources/index.md").read_text(encoding="utf-8")
    assert "* [api](api/index.md) - Documents under raw/sources/api/." in parent
    assert all(path.read_bytes() == content for path, content in untouched.items())


def test_ac29_nested_new_dest_indexes_are_born_current_bottom_up(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    result = ingest_file(invoke_ingest, initialized_kb, source, "--dest", "a/b")
    assert result.exit_code == 0
    a_index = (initialized_kb / "raw/sources/a/index.md").read_text(encoding="utf-8")
    b_index = (initialized_kb / "raw/sources/a/b/index.md").read_text(encoding="utf-8")
    assert "* [b](b/index.md) - Documents under raw/sources/a/b/." in a_index
    assert "* [RAW-000001][doc](doc.md)" in b_index
    assert result.stdout.splitlines() == [
        "created  raw/sources/a/b/doc.md",
        "created  raw/sources/a/b/index.md",
        "created  raw/sources/a/index.md",
        "updated  raw/sources/index.md",
        "ingested RAW-000001 as raw/sources/a/b/doc.md",
    ]


@pytest.mark.parametrize("json_output", [False, True])
def test_new_nested_dest_reserves_born_index_filename_during_ingest_collision_naming(
    json_output, initialized_kb, tmp_path, invoke_ingest
) -> None:
    source = tmp_path / "index.md"
    source.write_text("evidence", encoding="utf-8")
    arguments = ["--dest", "a/b"]
    if json_output:
        arguments.append("--json")

    result = ingest_file(
        invoke_ingest,
        initialized_kb,
        source,
        *arguments,
    )

    document = initialized_kb / "raw/sources/a/b/index-raw-000001.md"
    index = initialized_kb / "raw/sources/a/b/index.md"
    assert result.exit_code == 0
    assert result.exception is None
    assert document.is_file()
    assert index.read_text(encoding="utf-8") == (
        "---\ntype: index\n"
        "description: Documents under raw/sources/a/b/.\n---\n"
        "# b\n\n"
        "<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->\n\n"
        "## Files\n"
        "* [RAW-000001][index](index-raw-000001.md)\n"
    )
    if json_output:
        assert json.loads(result.stdout) == {
            "ok": True,
            "id": "RAW-000001",
            "path": "raw/sources/a/b/index-raw-000001.md",
            "original": None,
            "created": [
                "raw/sources/a/b/index-raw-000001.md",
                "raw/sources/a/b/index.md",
                "raw/sources/a/index.md",
            ],
            "updated": ["raw/sources/index.md"],
        }
    else:
        assert result.stdout.splitlines() == [
            "created  raw/sources/a/b/index-raw-000001.md",
            "created  raw/sources/a/b/index.md",
            "created  raw/sources/a/index.md",
            "updated  raw/sources/index.md",
            "ingested RAW-000001 as raw/sources/a/b/index-raw-000001.md",
        ]


def test_ac30_existing_dest_updates_only_its_index(initialized_kb, tmp_path, invoke_ingest) -> None:
    api = initialized_kb / "raw/sources/api"
    api.mkdir()
    (api / "index.md").write_text(
        "---\ntype: index\ndescription: Documents under raw/sources/api/.\n---\n# api\n\n"
        "<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->\n",
        encoding="utf-8",
    )
    parent_before = (initialized_kb / "raw/sources/index.md").read_bytes()
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    result = ingest_file(invoke_ingest, initialized_kb, source, "--dest", "api")
    assert result.exit_code == 0
    assert result.stdout.splitlines()[1] == "updated  raw/sources/api/index.md"
    assert (initialized_kb / "raw/sources/index.md").read_bytes() == parent_before


def test_ac31_trailing_slash_dest_is_normalized(initialized_kb, tmp_path, invoke_ingest) -> None:
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    result = ingest_file(invoke_ingest, initialized_kb, source, "--dest", "api/")
    assert result.exit_code == 0
    assert (initialized_kb / "raw/sources/api/doc.md").is_file()


def test_ac32_unsafe_or_escaping_dest_is_rejected_without_writes(
    initialized_kb, tmp_path, invoke_ingest, monkeypatch
) -> None:
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    source_before = source.read_bytes()
    before = snapshot(initialized_kb)
    import kb.cli.ingest_adapters as ingest_adapters

    acquired: list[str | None] = []

    def forbidden_adapter(value: str | None):
        acquired.append(value)
        raise AssertionError("destination validation must precede acquisition")

    monkeypatch.setitem(ingest_adapters._ADAPTERS, "file", forbidden_adapter)
    invalid_values = [
        "/abs",
        "../escape",
        r"nested\escape",
        "C:/escape",
        r"C:\escape",
        "C:escape",
        r"\\server\share",
        "//server/share",
    ]
    for value in invalid_values:
        result = ingest_file(invoke_ingest, initialized_kb, source, "--dest", value)
        assert result.exit_code == 2
        assert "E_INGEST_DEST_INVALID" in result.stderr
        assert value in result.stderr
        assert snapshot(initialized_kb) == before

    in_class_target = initialized_kb / "raw/sources/in-class-target"
    in_class_target.mkdir()
    (in_class_target / "index.md").write_text(
        "---\ntype: index\ndescription: In-class target.\n---\n# target\n",
        encoding="utf-8",
    )
    sentinel = in_class_target / "sentinel.bin"
    sentinel.write_bytes(b"target bytes")
    linked = initialized_kb / "raw/sources/linked"
    try:
        linked.symlink_to(in_class_target, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    link_text = os.readlink(linked)
    before_links = snapshot(initialized_kb)
    for value in ("linked", "linked/child"):
        for json_output in (False, True):
            arguments = ["--dest", value]
            if json_output:
                arguments.append("--json")
            result = ingest_file(
                invoke_ingest,
                initialized_kb,
                source,
                *arguments,
            )
            assert result.exit_code == 2
            assert isinstance(result.exception, SystemExit)
            if json_output:
                error = json.loads(result.stdout)["error"]
                assert error["code"] == "E_INGEST_DEST_INVALID"
                assert value in error["message"]
                assert result.stderr == ""
            else:
                assert "E_INGEST_DEST_INVALID" in result.stderr
                assert value in result.stderr
                assert result.stdout == ""
            assert snapshot(initialized_kb) == before_links
            assert linked.is_symlink() and os.readlink(linked) == link_text
            assert sentinel.read_bytes() == b"target bytes"
            assert source.read_bytes() == source_before

    junction = initialized_kb / "raw/sources/junction"
    junction.mkdir()
    (junction / "index.md").write_text(
        "---\ntype: index\ndescription: Junction target.\n---\n# junction\n",
        encoding="utf-8",
    )
    before_junction = snapshot(initialized_kb)
    real_lstat = Path.lstat

    def simulated_junction_lstat(path: Path):
        metadata = real_lstat(path)
        if path == junction:
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return metadata

    monkeypatch.setattr(Path, "lstat", simulated_junction_lstat)
    for value in ("junction", "junction/child"):
        result = ingest_file(
            invoke_ingest,
            initialized_kb,
            source,
            "--dest",
            value,
        )
        assert result.exit_code == 2
        assert isinstance(result.exception, SystemExit)
        assert "E_INGEST_DEST_INVALID" in result.stderr
        assert value in result.stderr
        assert snapshot(initialized_kb) == before_junction
        assert source.read_bytes() == source_before

    assert acquired == []


def test_destination_preflight_preserves_context_and_surface_validation_order(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    from kb.cli.app import app
    from typer.testing import CliRunner

    source = tmp_path / "ordering-source.md"
    source.write_text("source", encoding="utf-8")
    malformed_root = tmp_path / "malformed-ordering-kb"
    assert (
        CliRunner().invoke(app, ["init", "--root", str(malformed_root)]).exit_code
        == 0
    )
    write_existing(malformed_root, "synthetic/broken.md", "id: [\ntype: spec\n")
    malformed_before = snapshot(malformed_root)

    malformed = ingest_file(
        invoke_ingest,
        malformed_root,
        source,
        "--dest",
        "../escape",
    )

    assert malformed.exit_code == 2
    assert "E_INGEST_MALFORMED" in malformed.stderr
    assert "E_INGEST_DEST_INVALID" not in malformed.stderr
    assert snapshot(malformed_root) == malformed_before

    target = initialized_kb / "raw/feedback/in-class-target"
    target.mkdir()
    linked = initialized_kb / "raw/feedback/linked"
    try:
        linked.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    before = snapshot(initialized_kb)

    usage = invoke_ingest(
        initialized_kb,
        "--class",
        "feedback",
        "--from",
        "file",
        str(source),
        "--dest",
        "linked",
    )

    assert usage.exit_code == 2
    assert "E_INGEST_USAGE" in usage.stderr
    assert "--about is required" in usage.stderr
    assert "E_INGEST_DEST_INVALID" not in usage.stderr
    assert snapshot(initialized_kb) == before


@pytest.mark.parametrize(
    "destination",
    ["linked.md", "linked.md/child"],
    ids=["final-component", "intermediate-component"],
)
@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_md_named_destination_link_found_by_context_is_exact_destination_error(
    destination,
    json_output,
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.cli.ingest_adapters as ingest_adapters

    source = tmp_path / "context-destination-source.md"
    source.write_text("source\n", encoding="utf-8")
    external = tmp_path / "destination-target"
    external.mkdir()
    sentinel = external / "sentinel.bin"
    sentinel.write_bytes(b"target bytes")
    linked = initialized_kb / "raw/sources/linked.md"
    try:
        linked.symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    link_text = os.readlink(linked)
    before = snapshot(initialized_kb)
    source_before = source.read_bytes()
    acquired: list[str | None] = []

    def forbidden_adapter(value: str | None):
        acquired.append(value)
        raise AssertionError("context destination failure must precede acquisition")

    monkeypatch.setitem(ingest_adapters._ADAPTERS, "file", forbidden_adapter)
    arguments = ["--dest", destination]
    if json_output:
        arguments.append("--json")

    result = ingest_file(
        invoke_ingest,
        initialized_kb,
        source,
        *arguments,
    )

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_INGEST_DEST_INVALID"
        assert destination in error["message"]
        assert result.stderr == ""
    else:
        assert "E_INGEST_DEST_INVALID" in result.stderr
        assert destination in result.stderr
        assert result.stdout == ""
    assert acquired == []
    assert snapshot(initialized_kb) == before
    assert linked.is_symlink() and os.readlink(linked) == link_text
    assert sentinel.read_bytes() == b"target bytes"
    assert source.read_bytes() == source_before


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_requested_destination_directory_race_keeps_exact_invalid_envelope(
    json_output,
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.cli.ingest_adapters as ingest_adapters
    import kb.core.safeio as safeio

    source = tmp_path / "race-source.md"
    source.write_bytes(b"source\n")
    raced = initialized_kb / "raw/sources/raced.md"
    raced.mkdir()
    raced.joinpath("index.md").write_text(
        "---\ntype: index\ndescription: Raced.\n---\n# Raced\n",
        encoding="utf-8",
    )
    sources_status = (initialized_kb / "raw/sources").stat()
    outside = tmp_path / "outside-destination"
    outside.mkdir()
    sentinel = outside / "sentinel.bin"
    sentinel.write_bytes(b"outside")
    log_before = (initialized_kb / "log.md").read_bytes()
    class_index_before = (initialized_kb / "raw/sources/index.md").read_bytes()
    source_before = source.read_bytes()
    real_open = safeio.os.open
    injected = False
    acquired: list[str | None] = []

    def replace_listed_destination(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected
        if path == "raced.md" and dir_fd is not None and not injected:
            parent_status = os.fstat(dir_fd)
            if (
                parent_status.st_dev == sources_status.st_dev
                and parent_status.st_ino == sources_status.st_ino
            ):
                injected = True
                os.rename(
                    "raced.md",
                    "raced-original",
                    src_dir_fd=dir_fd,
                    dst_dir_fd=dir_fd,
                )
                os.symlink(outside, "raced.md", dir_fd=dir_fd)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    def forbidden_adapter(value: str | None):
        acquired.append(value)
        raise AssertionError("context failure must precede adapter acquisition")

    monkeypatch.setattr(safeio.os, "open", replace_listed_destination)
    monkeypatch.setitem(ingest_adapters._ADAPTERS, "file", forbidden_adapter)
    arguments = ["--dest", "raced.md/child"]
    if json_output:
        arguments.append("--json")

    result = ingest_file(
        invoke_ingest,
        initialized_kb,
        source,
        *arguments,
    )

    assert injected
    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_INGEST_DEST_INVALID"
        assert result.stderr == ""
    else:
        assert "E_INGEST_DEST_INVALID" in result.stderr
        assert result.stdout == ""
    assert acquired == []
    assert source.read_bytes() == source_before
    assert raced.is_symlink() and os.readlink(raced) == str(outside)
    assert (initialized_kb / "raw/sources/raced-original/index.md").is_file()
    assert sentinel.read_bytes() == b"outside"
    assert (initialized_kb / "raw/sources/index.md").read_bytes() == class_index_before
    assert (initialized_kb / "log.md").read_bytes() == log_before


@pytest.mark.parametrize(
    ("arguments", "absent_code"),
    [
        (["--dest", "../escape"], "E_INGEST_DEST_INVALID"),
        (
            ["--class", "feedback", "--from", "file"],
            "E_INGEST_USAGE",
        ),
    ],
    ids=["invalid-destination-syntax", "surface-error"],
)
def test_unrelated_md_link_context_failure_stays_generic_and_keeps_precedence(
    arguments,
    absent_code,
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.cli.ingest_adapters as ingest_adapters

    source = tmp_path / "unrelated-context-source.md"
    source.write_text("source\n", encoding="utf-8")
    external = tmp_path / "unrelated-target"
    external.mkdir()
    linked = initialized_kb / "synthetic/unrelated.md"
    try:
        linked.symlink_to(external, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    before = snapshot(initialized_kb)
    acquired: list[str | None] = []

    def forbidden_adapter(value: str | None):
        acquired.append(value)
        raise AssertionError("context failure must precede acquisition")

    monkeypatch.setitem(ingest_adapters._ADAPTERS, "file", forbidden_adapter)
    command = [*arguments]
    if "--class" not in command:
        command = ["--class", "source", "--from", "file", *command]
    command.insert(command.index("--from") + 2, str(source))

    result = invoke_ingest(initialized_kb, *command)

    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert absent_code not in result.stderr
    assert acquired == []
    assert snapshot(initialized_kb) == before


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_destination_metadata_error_is_exact_before_adapter(
    json_output, initialized_kb, tmp_path, invoke_ingest, monkeypatch
) -> None:
    source = tmp_path / "metadata-source.md"
    source.write_text("source", encoding="utf-8")
    source_before = source.read_bytes()
    inaccessible = initialized_kb / "raw/sources/inaccessible"
    inaccessible.mkdir()
    (inaccessible / "index.md").write_text(
        "---\ntype: index\ndescription: Inaccessible target.\n---\n# inaccessible\n",
        encoding="utf-8",
    )
    sentinel = inaccessible / "sentinel.bin"
    sentinel.write_bytes(b"target bytes")
    before = snapshot(initialized_kb)
    real_lstat = Path.lstat

    def denied_lstat(path: Path):
        if path == inaccessible:
            raise PermissionError(errno.EACCES, "component metadata denied", path)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", denied_lstat)
    import kb.cli.ingest_adapters as ingest_adapters

    acquired: list[str | None] = []

    def forbidden_adapter(value: str | None):
        acquired.append(value)
        raise AssertionError("destination metadata failure must precede acquisition")

    monkeypatch.setitem(ingest_adapters._ADAPTERS, "file", forbidden_adapter)
    arguments = ["--dest", "inaccessible/child"]
    if json_output:
        arguments.append("--json")

    result = ingest_file(
        invoke_ingest,
        initialized_kb,
        source,
        *arguments,
    )

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_INGEST_DEST_INVALID"
        assert "component metadata denied" in error["message"]
        assert result.stderr == ""
    else:
        assert "E_INGEST_DEST_INVALID" in result.stderr
        assert "component metadata denied" in result.stderr
        assert result.stdout == ""
    assert acquired == []
    assert snapshot(initialized_kb) == before
    assert sentinel.read_bytes() == b"target bytes"
    assert source.read_bytes() == source_before


@pytest.mark.parametrize(
    ("raw_class", "class_relative"),
    [
        ("source", "raw/sources"),
        ("chat", "raw/chats"),
        ("feedback", "raw/feedback"),
    ],
)
def test_missing_required_class_root_is_invalid_before_adapter(
    raw_class,
    class_relative,
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
) -> None:
    source = tmp_path / f"missing-{raw_class}-root.md"
    source.write_text("source", encoding="utf-8")
    write_existing(
        initialized_kb,
        "synthetic/about.md",
        "id: KB-000001\ntype: spec\n",
    )
    shutil.rmtree(initialized_kb / class_relative)
    before = snapshot(initialized_kb)
    import kb.cli.ingest_adapters as ingest_adapters

    acquired: list[str | None] = []

    def forbidden_adapter(value: str | None):
        acquired.append(value)
        raise AssertionError("missing class root must precede acquisition")

    monkeypatch.setitem(ingest_adapters._ADAPTERS, "file", forbidden_adapter)
    arguments = [
        "--class",
        raw_class,
        "--from",
        "file",
        str(source),
    ]
    if raw_class == "feedback":
        arguments.extend(["--about", "KB-000001"])

    result = invoke_ingest(initialized_kb, *arguments)

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    assert "E_INGEST_DEST_INVALID" in result.stderr
    assert acquired == []
    assert snapshot(initialized_kb) == before
    assert not (initialized_kb / class_relative).exists()


def test_ac33_feedback_path_ref_stores_canonical_id(initialized_kb, invoke_ingest) -> None:
    write_existing(initialized_kb, "synthetic/specs/webhook.md", "id: KB-000007\ntype: coding-spec\n")
    result = invoke_ingest(
        initialized_kb, "--class", "feedback", "--from", "stdin",
        "--about", "synthetic/specs/webhook.md", input="feedback",
    )
    assert result.exit_code == 0
    assert split_document(initialized_kb / "raw/feedback/feed-000001.md")[0]["about"] == "KB-000007"


def test_ac34_unknown_about_id_is_reference_finding(initialized_kb, invoke_ingest) -> None:
    before = snapshot(initialized_kb)
    result = invoke_ingest(
        initialized_kb, "--class", "feedback", "--from", "stdin",
        "--about", "KB-999999", input="feedback",
    )
    assert result.exit_code == 1 and "E_INGEST_ABOUT_UNRESOLVED" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac35_about_index_without_id_is_reference_finding(initialized_kb, invoke_ingest) -> None:
    before = snapshot(initialized_kb)
    result = invoke_ingest(
        initialized_kb, "--class", "feedback", "--from", "stdin", "--about", "index.md", input="x"
    )
    assert result.exit_code == 1 and "E_INGEST_ABOUT_UNRESOLVED" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac36_about_class_pairing_is_usage_error(initialized_kb, invoke_ingest) -> None:
    before = snapshot(initialized_kb)
    missing = invoke_ingest(initialized_kb, "--class", "feedback", "--from", "stdin", input="x")
    forbidden = invoke_ingest(
        initialized_kb, "--class", "source", "--from", "stdin", "--about", "KB-000001", input="x"
    )
    assert missing.exit_code == forbidden.exit_code == 2
    assert "E_INGEST_USAGE" in missing.stderr and "--about is required" in missing.stderr
    assert "E_INGEST_USAGE" in forbidden.stderr and "--about is forbidden" in forbidden.stderr
    assert snapshot(initialized_kb) == before


def test_ac37_source_adapter_pairing_is_usage_error(initialized_kb, invoke_ingest) -> None:
    before = snapshot(initialized_kb)
    missing = invoke_ingest(initialized_kb, "--class", "source", "--from", "file")
    forbidden = invoke_ingest(
        initialized_kb, "--class", "source", "--from", "stdin", "source.md", input="x"
    )
    assert missing.exit_code == forbidden.exit_code == 2
    assert "E_INGEST_USAGE" in missing.stderr and "required" in missing.stderr
    assert "E_INGEST_USAGE" in forbidden.stderr and "forbidden" in forbidden.stderr
    assert snapshot(initialized_kb) == before


def test_ac38_missing_or_directory_source_is_environment_error(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    before = snapshot(initialized_kb)
    missing = ingest_file(invoke_ingest, initialized_kb, tmp_path / "absent")
    directory = ingest_file(invoke_ingest, initialized_kb, tmp_path)
    assert missing.exit_code == directory.exit_code == 2
    assert "E_INGEST_SOURCE_NOT_FOUND" in missing.stderr
    assert "E_INGEST_SOURCE_NOT_FOUND" in directory.stderr
    assert snapshot(initialized_kb) == before


def test_ac39_bad_enums_and_unknown_option_are_typer_usage_errors(initialized_kb, invoke_ingest) -> None:
    before = snapshot(initialized_kb)
    cases = [
        ("--class", "bogus", "--from", "stdin"),
        ("--class", "source", "--from", "bogus"),
        ("--class", "source", "--from", "stdin", "--bogus-flag"),
    ]
    for arguments in cases:
        result = invoke_ingest(initialized_kb, *arguments, input="x")
        assert result.exit_code == 2
        assert result.stderr
        assert snapshot(initialized_kb) == before


def test_ac40_missing_discovered_or_explicit_root_reports_shared_error(
    tmp_path, invoke_ingest
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    first = invoke_ingest(empty, "--class", "source", "--from", "stdin", input="x")
    second = invoke_ingest(
        empty, "--class", "source", "--from", "stdin", "--kb", str(empty), input="x"
    )
    for result in [first, second]:
        assert result.exit_code == 2
        assert result.stderr.strip() == (
            "E_NO_KB: not inside a knowledge base (no kb-config.json found); "
            "run 'kb init' or pass --kb"
        )


def test_ac41_invalid_config_is_environment_error(initialized_kb, invoke_ingest) -> None:
    (initialized_kb / "kb-config.json").write_text("not json", encoding="utf-8")
    before = snapshot(initialized_kb)
    result = invoke_ingest(initialized_kb, "--class", "source", "--from", "stdin", input="x")
    assert result.exit_code == 2 and "E_CONFIG_INVALID" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac42_newer_schema_is_environment_error(initialized_kb, invoke_ingest) -> None:
    (initialized_kb / "kb-config.json").write_text('{"schema": 999}', encoding="utf-8")
    before = snapshot(initialized_kb)
    result = invoke_ingest(initialized_kb, "--class", "source", "--from", "stdin", input="x")
    assert result.exit_code == 2 and "E_SCHEMA_UNSUPPORTED" in result.stderr
    assert snapshot(initialized_kb) == before


def test_final_config_access_failure_remains_config_invalid_for_ingest(
    tmp_path,
    initialized_kb,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    source = tmp_path / "evidence.md"
    source.write_text("evidence\n", encoding="utf-8")
    before = snapshot(initialized_kb)
    real_read = safeio._RootedReader.read_file

    def fail_config_read(reader, relative, **kwargs):
        if relative == Path("kb-config.json"):
            raise PermissionError(errno.EACCES, "config unreadable")
        return real_read(reader, relative, **kwargs)

    monkeypatch.setattr(safeio._RootedReader, "read_file", fail_config_read)

    result = ingest_file(invoke_ingest, initialized_kb, source)

    assert result.exit_code == 2
    assert "E_CONFIG_INVALID" in result.stderr
    assert "E_INGEST_IO" not in result.stderr
    assert snapshot(initialized_kb) == before


def test_index_losing_closing_delimiter_during_ingest_preflight_maps_to_io(
    tmp_path,
    initialized_kb,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.core.ingest as ingest_core

    source = tmp_path / "evidence.md"
    source.write_text("evidence\n", encoding="utf-8")
    index = initialized_kb / "raw/sources/index.md"
    real_prepare = ingest_core.prepare_write
    injected: dict[str, dict[str, bytes]] = {}

    def corrupt_index_then_prepare(context, intent):
        index.write_bytes(b"---\ntype: index\n")
        injected["snapshot"] = snapshot(initialized_kb)
        return real_prepare(context, intent)

    monkeypatch.setattr(ingest_core, "prepare_write", corrupt_index_then_prepare)

    result = ingest_file(invoke_ingest, initialized_kb, source)

    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert snapshot(initialized_kb) == injected["snapshot"]


def test_ac43_failed_preflight_is_byte_atomic(initialized_kb, invoke_ingest) -> None:
    before = snapshot(initialized_kb)
    result = invoke_ingest(
        initialized_kb, "--class", "feedback", "--from", "stdin", "--about", "KB-999999", input="x"
    )
    assert result.exit_code == 1
    assert snapshot(initialized_kb) == before


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="requires enforceable POSIX directory permissions",
)
def test_ac44_write_phase_os_error_is_typed(initialized_kb, tmp_path, invoke_ingest) -> None:
    target = initialized_kb / "raw/sources"
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    target.chmod(0o500)
    try:
        result = ingest_file(invoke_ingest, initialized_kb, source)
    finally:
        target.chmod(0o700)
    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert result.stderr.split(":", 1)[1].strip()


@pytest.mark.parametrize(
    ("source_name", "source_bytes", "occupied_name"),
    [
        ("late.txt", b"text", "late.md"),
        ("late.pdf", b"\xffbinary", "late.pdf"),
    ],
)
def test_append_only_file_creation_refuses_late_stub_and_original_occupants(
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
    source_name,
    source_bytes,
    occupied_name,
) -> None:
    from kb.core import write_pipeline

    source = tmp_path / source_name
    source.write_bytes(source_bytes)
    occupied_path = initialized_kb / "raw/sources" / occupied_name

    real_create = write_pipeline.create_rooted_file_bytes

    def create_with_late_occupant(
        root: Path,
        relative: Path,
        content: bytes,
        root_identity,
        *,
        parent_expected=None,
    ) -> None:
        if root / relative == occupied_path:
            real_create(
                root,
                relative,
                b"late occupant",
                root_identity,
                parent_expected=parent_expected,
            )
        real_create(
            root,
            relative,
            content,
            root_identity,
            parent_expected=parent_expected,
        )

    monkeypatch.setattr(
        write_pipeline,
        "create_rooted_file_bytes",
        create_with_late_occupant,
    )

    result = ingest_file(invoke_ingest, initialized_kb, source)

    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert occupied_path.read_bytes() == b"late occupant"
    assert "late.md" not in (
        initialized_kb / "raw/sources/index.md"
    ).read_text(encoding="utf-8")
    assert " | ingested | " not in (
        initialized_kb / "log.md"
    ).read_text(encoding="utf-8")


def test_ingest_stale_index_identity_is_typed_and_preserves_late_occupant(
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
) -> None:
    from kb.core import write_pipeline

    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    index = initialized_kb / "raw/sources/index.md"
    late = b"late replacement index\n"
    real_overwrite = write_pipeline.overwrite_rooted_bytes

    def replace_before_overwrite(
        root: Path,
        relative: Path,
        content: bytes,
        root_identity,
        expected,
    ) -> None:
        if relative == Path("raw/sources/index.md"):
            index.rename(index.with_name("old-index.md"))
            index.write_bytes(late)
        real_overwrite(root, relative, content, root_identity, expected)

    monkeypatch.setattr(
        write_pipeline,
        "overwrite_rooted_bytes",
        replace_before_overwrite,
    )

    result = ingest_file(invoke_ingest, initialized_kb, source)

    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert index.read_bytes() == late
    assert (initialized_kb / "raw/sources/doc.md").is_file()
    assert " | ingested | " not in (
        initialized_kb / "log.md"
    ).read_text(encoding="utf-8")


def test_ac45_actor_is_written_to_log(initialized_kb, tmp_path, invoke_ingest) -> None:
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, source, "--actor", "pm-skill").exit_code == 0
    assert " | ingested | pm-skill | RAW-000001 | " in (
        initialized_kb / "log.md"
    ).read_text(encoding="utf-8").splitlines()[-1]


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_surrogate_escaped_source_origin_is_stable_ingest_io_without_mutation(
    json_output,
    initialized_kb,
    tmp_path,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.cli.ingest_adapters as ingest_adapters
    from kb.core.ingest import AdapterPayload

    source = tmp_path / "adapter-source.md"
    source.write_bytes(b"evidence\n")
    source_before = source.read_bytes()
    before = snapshot(initialized_kb)
    escaped_name = "evidence-\udcff.md"
    escaped_origin = f"/external/{escaped_name}"

    def surrogate_payload(_value: str | None) -> AdapterPayload:
        return AdapterPayload(
            source_kind="file",
            data=source_before,
            default_origin=escaped_origin,
            source_filename=escaped_name,
        )

    monkeypatch.setitem(ingest_adapters._ADAPTERS, "file", surrogate_payload)
    arguments = ["--title", "Evidence"]
    if json_output:
        arguments.append("--json")

    result = ingest_file(
        invoke_ingest,
        initialized_kb,
        source,
        *arguments,
    )

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_INGEST_IO"
        assert "UTF-8" in error["message"]
        assert result.stderr == ""
    else:
        assert "E_INGEST_IO" in result.stderr
        assert "UTF-8" in result.stderr
        assert result.stdout == ""
    assert snapshot(initialized_kb) == before
    assert source.read_bytes() == source_before


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_unencodable_born_destination_is_stable_ingest_io_without_mutation(
    json_output,
    initialized_kb,
    tmp_path,
    invoke_ingest,
) -> None:
    source = tmp_path / "adapter-source.md"
    source.write_bytes(b"evidence\n")
    source_before = source.read_bytes()
    before = snapshot(initialized_kb)
    destination = os.fsdecode(b"bad-\xff")
    arguments = ["--dest", destination]
    if json_output:
        arguments.append("--json")

    result = ingest_file(
        invoke_ingest,
        initialized_kb,
        source,
        *arguments,
    )

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_INGEST_IO"
        assert "UTF-8" in error["message"]
        assert result.stderr == ""
    else:
        assert "E_INGEST_IO" in result.stderr
        assert "UTF-8" in result.stderr
        assert result.stdout == ""
    assert snapshot(initialized_kb) == before
    assert source.read_bytes() == source_before


def test_ac46_missing_log_is_recreated_without_initialized_entry(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    (initialized_kb / "log.md").unlink()
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")
    assert ingest_file(invoke_ingest, initialized_kb, source).exit_code == 0
    log = (initialized_kb / "log.md").read_text(encoding="utf-8")
    assert log.startswith(
        "---\ntype: log\n---\n<!-- KB history — append-only; written by `kb log`. "
    )
    assert "# Knowledge Base Log\n" in log
    assert " | initialized | " not in log
    assert log.count(" | ingested | ") == 1


def test_ac47_success_json_has_exact_fields_sorted_paths_and_original(
    initialized_kb, tmp_path, invoke_ingest
) -> None:
    binary = tmp_path / "Q3 Report.pdf"
    binary.write_bytes(b"\xffbinary")
    result = ingest_file(
        invoke_ingest,
        initialized_kb,
        binary,
        "--title",
        "Q3 Report",
        "--dest",
        "q3",
        "--json",
    )
    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert result.stderr == ""
    assert set(payload) == {"ok", "id", "path", "original", "created", "updated"}
    assert payload == {
        "ok": True,
        "id": "RAW-000001",
        "path": "raw/sources/q3/q3-report.md",
        "original": "raw/sources/q3/q3-report.pdf",
        "created": [
            "raw/sources/q3/index.md",
            "raw/sources/q3/q3-report.md",
            "raw/sources/q3/q3-report.pdf",
        ],
        "updated": ["raw/sources/index.md"],
    }
    text = tmp_path / "text.md"
    text.write_text("text", encoding="utf-8")
    text_result = ingest_file(invoke_ingest, initialized_kb, text, "--json")
    assert json.loads(text_result.stdout)["original"] is None


def test_ac48_error_json_is_exact_shared_envelope(initialized_kb, invoke_ingest) -> None:
    result = invoke_ingest(
        initialized_kb,
        "--class",
        "feedback",
        "--from",
        "stdin",
        "--about",
        "KB-999999",
        "--json",
        input="feedback",
    )
    payload = json.loads(result.stdout)
    assert result.exit_code == 1
    assert result.stderr == ""
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message"}
    assert payload["error"]["code"] == "E_INGEST_ABOUT_UNRESOLVED"
    assert isinstance(payload["error"]["message"], str)


def test_ac49_help_contains_every_normative_string(runner) -> None:
    result = runner.invoke(
        __import__("kb.cli.app", fromlist=["app"]).app,
        ["ingest", "--help"],
        terminal_width=1000,
    )
    expected = [
        "Ingest material into the knowledge base as immutable raw evidence.",
        "Reads from a file, stdin, or the clipboard and files one normalized Markdown document into raw/sources/, raw/chats/, or raw/feedback/, with the next sequential id and the reduced raw frontmatter.",
        "The body is copied verbatim — ingest normalizes and files, it never synthesizes.",
        "A non-text file is copied unchanged alongside a generated Markdown stub, which becomes the citable form.",
        "Feedback requires --about: the document the feedback concerns.",
        "Updates the affected index.md listings and appends an ingested entry to log.md.",
        "Does not touch Git.",
        "Path to the source file (required with --from file, forbidden otherwise).",
        "Raw subclass to file under: source, chat, or feedback.",
        "Where to read the material from: file, stdin, or clipboard.",
        "Subdirectory under the class directory (e.g. api → raw/sources/api/). Created with its index.md if missing.",
        "Document the feedback concerns (id or KB-relative path). Required for --class feedback.",
        "Document title; also drives the target filename. [default: derived from the source filename or the id]",
        'Provenance recorded in the frontmatter — a path, a URL, or a label. [default: the source path, "stdin", or "clipboard"]',
        "Actor recorded in the log entry. [default: kb-cli]",
        "KB root. [default: discovered upward from the current directory]",
        "Emit results as JSON.",
        "kb ingest --class source --from file notes.md                 File a document into raw/sources/",
        "kb ingest --class source --from file report.pdf --dest q3     Non-text original + citable stub into raw/sources/q3/",
        "kb ingest --class feedback --from stdin --about KB-000007     Pipe feedback about KB-000007",
        'kb ingest --class chat --from clipboard --title "Planning session"   Clipboard into raw/chats/',
        "kb ingest --class source --from file page.html --origin https://ex.com/post   Record the web page it came from",
    ]
    assert result.exit_code == 0
    assert all(value in result.stdout for value in expected)


def test_ac50_file_ingest_never_invokes_git_or_creates_git_directory(
    initialized_kb, tmp_path, invoke_ingest, monkeypatch
) -> None:
    source = tmp_path / "doc.md"
    source.write_text("doc", encoding="utf-8")

    def forbidden_subprocess(*args, **kwargs):
        raise AssertionError(f"unexpected subprocess invocation: {args!r}")

    monkeypatch.setattr("kb.cli.ingest_adapters.subprocess.run", forbidden_subprocess)
    result = ingest_file(invoke_ingest, initialized_kb, source)
    assert result.exit_code == 0
    assert not (initialized_kb / ".git").exists()


def test_replaced_root_before_preparation_maps_to_ingest_io_without_writes(
    tmp_path,
    initialized_kb,
    invoke_ingest,
    monkeypatch,
) -> None:
    import kb.core.ingest as ingest_core
    from kb.core.housekeeping import init_kb

    source = tmp_path / "evidence.md"
    source.write_text("evidence\n", encoding="utf-8")
    original = tmp_path / "original-kb"
    replacement_holder: dict[str, Path] = {}
    real_prepare = ingest_core.prepare_write

    def replace_root(context, intent):
        initialized_kb.rename(original)
        assert init_kb(initialized_kb).root == initialized_kb.resolve()
        replacement_holder["root"] = initialized_kb
        return real_prepare(context, intent)

    monkeypatch.setattr(ingest_core, "prepare_write", replace_root)

    result = ingest_file(invoke_ingest, initialized_kb, source)

    replacement = replacement_holder["root"]
    assert result.exit_code == 2
    assert "E_INGEST_IO" in result.stderr
    assert not (original / "raw/sources/evidence.md").exists()
    assert not (replacement / "raw/sources/evidence.md").exists()


def test_environment_failure_precedes_missing_external_source(
    tmp_path: Path,
    invoke_ingest,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    result = invoke_ingest(
        outside,
        "--class",
        "source",
        "--from",
        "file",
        str(tmp_path / "missing.md"),
    )
    assert result.exit_code == 2
    assert "E_NO_KB" in result.output
    assert "E_INGEST_SOURCE_NOT_FOUND" not in result.output
