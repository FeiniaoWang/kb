from __future__ import annotations

import json
from pathlib import Path

import yaml

from conftest import make_doc, make_kb


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def chat(
    root: Path,
    doc_id: str = "CHAT-000001",
    relative: str = "raw/chats/session.md",
) -> Path:
    return make_doc(
        root,
        relative,
        {
            "id": doc_id,
            "type": "chat",
            "ingested_at": "2026-07-16T09:00:00Z",
            "origin": "stdin",
            "title": "Session",
        },
    )


def source(
    root: Path,
    doc_id: str = "RAW-000001",
    relative: str = "raw/sources/source.md",
) -> Path:
    return make_doc(
        root,
        relative,
        {
            "id": doc_id,
            "type": "raw-source",
            "ingested_at": "2026-07-16T08:00:00Z",
            "origin": "file",
            "title": "Source",
        },
    )


def synthetic(
    root: Path,
    doc_id: str = "KB-000001",
    relative: str = "synthetic/note.md",
    **overrides: object,
) -> Path:
    chat(root)
    values: dict[str, object] = {
        "id": doc_id,
        "type": "spec",
        "title": "Note",
        "description": "A concise note.",
        "status": "current",
        "derived_from": ["CHAT-000001"],
        "timestamp": "2026-07-16T10:00:00Z",
        "last_human_touch": "2026-07-16T10:00:00Z",
    }
    values.update(overrides)
    return make_doc(root, relative, values)


def finding_payload(result) -> list[dict[str, object]]:
    return json.loads(result.stdout)["findings"]


def test_ac01_fresh_init_scaffold_is_born_valid(
    initialized_kb, invoke_validate
) -> None:
    result = invoke_validate(initialized_kb)
    assert result.exit_code == 0
    assert result.stdout == "no findings — checked 11 files\n"


def test_ac02_fully_conforming_populated_kb_has_no_findings(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb", types=["spec"], tags=["api"])
    source(root)
    chat(root)
    make_doc(
        root,
        "raw/feedback/feedback.md",
        {
            "id": "FEED-000001",
            "type": "feedback",
            "ingested_at": "2026-07-16T09:30:00Z",
            "origin": "stdin",
            "title": "Feedback",
            "about": "KB-000001",
        },
    )
    synthetic(root, tags=["api"], instructions="Keep examples runnable.")
    synthetic(root, "KB-000002", "synthetic/old.md", status="superseded")
    synthetic(root, "KB-000003", "synthetic/new.md", supersedes="KB-000002")
    result = invoke_validate(root)
    assert result.exit_code == 0
    assert "no findings" in result.stdout


def test_ac03_validation_is_byte_for_byte_read_only(
    initialized_kb, invoke_validate
) -> None:
    (initialized_kb / "README.md").write_text(
        "not frontmatter\n", encoding="utf-8"
    )
    before = snapshot(initialized_kb)
    result = invoke_validate(initialized_kb)
    assert result.exit_code == 1
    assert snapshot(initialized_kb) == before


def test_ac04_config_only_empty_kb_checks_zero_files(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "empty")
    result = invoke_validate(root)
    assert result.exit_code == 0
    assert result.stdout == "no findings — checked 0 files\n"


def test_ac05_malformed_guard_does_not_block_validate(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "broken.md").write_text("broken\n", encoding="utf-8")
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert "FM0_UNPARSEABLE" in result.stdout
    assert result.stdout.endswith(
        "1 finding (1 error, 0 warnings) — checked 1 files\n"
    )


def test_ac06_missing_unclosed_and_invalid_yaml_are_unparseable(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "a.md").write_text("body\n", encoding="utf-8")
    (root / "b.md").write_text("---\ntype: spec\n", encoding="utf-8")
    (root / "c.md").write_text("---\ntype: [\n---\n", encoding="utf-8")
    result = invoke_validate(root, "--json")
    assert result.exit_code == 1
    findings = finding_payload(result)
    assert [item["code"] for item in findings] == ["FM0_UNPARSEABLE"] * 3
    assert all("frontmatter cannot be parsed" in item["message"] for item in findings)


def test_ac07_non_mapping_and_non_utf8_are_unparseable(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "a.md").write_text("---\n- x\n---\n", encoding="utf-8")
    (root / "b.md").write_bytes(b"---\ntype: spec\n---\n\xff")
    result = invoke_validate(root, "--json")
    assert result.exit_code == 1
    assert [item["code"] for item in finding_payload(result)] == [
        "FM0_UNPARSEABLE",
        "FM0_UNPARSEABLE",
    ]


def test_ac08_bad_type_shapes_stop_classification(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "a.md", {"id": "KB-000001"})
    make_doc(root, "b.md", {"type": ""})
    make_doc(root, "c.md", {"type": ["x"]})
    result = invoke_validate(root, "--json")
    findings = finding_payload(result)
    assert result.exit_code == 1
    assert [item["code"] for item in findings] == ["FM0_MISSING_TYPE"] * 3


def test_ac09_log_without_type_gets_fm0(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "log.md", {"note": "operational"})
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert (
        "error  log.md  FM0_MISSING_TYPE  missing mandatory type frontmatter field"
        in result.stdout
    )


def test_ac10_stray_readme_is_in_the_check_universe(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    (root / "README.md").write_text("# Read me\n", encoding="utf-8")
    result = invoke_validate(root)
    assert result.exit_code == 1
    assert "error  README.md  FM0_UNPARSEABLE" in result.stdout
