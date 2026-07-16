from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from kb.cli.app import app
from conftest import expected_manifest


LOG_PATTERN = re.compile(
    r"^- (?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) "
    r"\| initialized \| kb-cli \| - \| KB scaffolded by kb init$",
    re.MULTILINE,
)


def files_under(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def read_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    opening, yaml_text, body = text.split("---", 2)
    assert opening == ""
    assert body.startswith("\n")
    parsed = yaml.safe_load(yaml_text)
    assert isinstance(parsed, dict)
    return parsed


def timestamp_from_log(root: Path) -> str:
    match = LOG_PATTERN.search((root / "log.md").read_text(encoding="utf-8"))
    assert match is not None
    return match.group("timestamp")


def test_ac01_fresh_scaffold_has_exact_manifest_and_bytes(tmp_path, invoke_init) -> None:
    result = invoke_init(tmp_path)
    assert result.exit_code == 0
    timestamp = timestamp_from_log(tmp_path)
    expected = expected_manifest(timestamp)
    assert files_under(tmp_path) == set(expected)
    assert {
        path: (tmp_path / path).read_text(encoding="utf-8") for path in expected
    } == expected


def test_ac02_text_output_is_sorted_and_summarized(tmp_path, invoke_init) -> None:
    result = invoke_init(tmp_path)
    expected_paths = sorted(expected_manifest("unused"))
    expected_lines = [f"created  {path}" for path in expected_paths]
    expected_lines.append(
        f"KB ready at {tmp_path.resolve()} — 12 created, 0 overwritten, 0 skipped"
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == expected_lines


def test_ac03_config_is_strict_json_with_exact_fields(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    config = json.loads((tmp_path / "kb-config.json").read_text(encoding="utf-8"))
    assert config == {
        "schema": 1,
        "types": [],
        "tags": [],
        "id_prefixes": {
            "synthetic": "KB",
            "source": "RAW",
            "chat": "CHAT",
            "feedback": "FEED",
        },
        "propagation_auto_safe": [],
    }


def test_ac04_governance_documents_have_reserved_ids(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    conventions = read_frontmatter(tmp_path / "governance/conventions.md")
    config_reference = read_frontmatter(tmp_path / "governance/kb-config.md")
    assert conventions["id"] == "GOVERNANCE-CONVENTIONS"
    assert config_reference["id"] == "GOVERNANCE-KB-CONFIG"
    pytest.xfail("scan and id resolution are introduced by kb ingest")


def test_ac05_indexes_have_exact_frontmatter_and_bodies(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    timestamp = timestamp_from_log(tmp_path)
    expected = expected_manifest(timestamp)
    indexes = sorted(path for path in expected if path.endswith("index.md"))
    assert len(indexes) == 8
    for relative_path in indexes:
        actual = (tmp_path / relative_path).read_text(encoding="utf-8")
        assert actual == expected[relative_path]
        frontmatter = read_frontmatter(tmp_path / relative_path)
        assert frontmatter["type"] == "index"
        assert "description" in frontmatter
        assert "id" not in frontmatter


def test_ac06_every_markdown_file_has_type(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    markdown_files = sorted(tmp_path.rglob("*.md"))
    assert len(markdown_files) == 11
    assert all("type" in read_frontmatter(path) for path in markdown_files)


def test_ac07_scaffold_contains_no_gitkeep(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    assert list(tmp_path.rglob(".gitkeep")) == []


def test_ac08_log_has_one_valid_utc_initialized_entry(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    text = (tmp_path / "log.md").read_text(encoding="utf-8")
    matches = list(LOG_PATTERN.finditer(text))
    assert len(matches) == 1
    parsed = datetime.fromisoformat(matches[0].group("timestamp").replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc


def test_ac09_rerun_skips_without_writes(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    for path in before:
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    expected_before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}
    result = invoke_init(tmp_path)
    expected_paths = sorted(expected_manifest("unused"))
    expected_lines = [f"skipped  {path} (exists)" for path in expected_paths]
    expected_lines.append(
        f"KB ready at {tmp_path.resolve()} — 0 created, 0 overwritten, 12 skipped"
    )
    after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}
    assert result.exit_code == 0
    assert result.stdout.splitlines() == expected_lines
    assert after == expected_before


def test_ac10_three_runs_keep_one_initialized_entry(tmp_path, invoke_init) -> None:
    for _ in range(3):
        assert invoke_init(tmp_path).exit_code == 0
    assert len(LOG_PATTERN.findall((tmp_path / "log.md").read_text(encoding="utf-8"))) == 1


def test_log_repair_ignores_initialized_marker_in_other_action_note(
    tmp_path, invoke_init
) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    log_path = tmp_path / "log.md"
    misleading_entry = (
        "- 2026-07-15T12:00:00Z | ingested | kb-cli | - | "
        "note includes | initialized | marker"
    )
    log_path.write_text(
        LOG_PATTERN.sub(misleading_entry, log_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    result = invoke_init(tmp_path)

    repaired = log_path.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert misleading_entry in repaired
    assert len(LOG_PATTERN.findall(repaired)) == 1


def test_ac11_partial_scaffold_recreates_only_missing_entries(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    (tmp_path / "log.md").unlink()
    (tmp_path / "raw/index.md").unlink()
    result = invoke_init(tmp_path)
    lines = result.stdout.splitlines()
    assert result.exit_code == 0
    assert "created  log.md" in lines
    assert "created  raw/index.md" in lines
    assert sum(line.startswith("created  ") for line in lines) == 2
    assert sum(line.startswith("skipped  ") for line in lines) == 10
    assert lines[-1].endswith("— 2 created, 0 overwritten, 10 skipped")
    assert (tmp_path / "raw/index.md").read_text(encoding="utf-8") == expected_manifest(
        timestamp_from_log(tmp_path)
    )["raw/index.md"]
    assert len(LOG_PATTERN.findall((tmp_path / "log.md").read_text(encoding="utf-8"))) == 1


def test_ac12_foreign_content_is_untouched(tmp_path, invoke_init) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_bytes(b"private notes\x00")
    misc = tmp_path / "misc"
    misc.mkdir()
    foreign = misc / "data.bin"
    foreign.write_bytes(b"foreign\xff")
    result = invoke_init(tmp_path)
    assert result.exit_code == 0
    assert notes.read_bytes() == b"private notes\x00"
    assert foreign.read_bytes() == b"foreign\xff"
    assert not (misc / "index.md").exists()


def test_ac13_force_on_empty_root_creates_without_overwrites(tmp_path, invoke_init, monkeypatch) -> None:
    from kb.core import housekeeping

    monkeypatch.setattr(housekeeping, "_utc_now", lambda: "2026-07-15T12:00:00Z")
    plain = tmp_path / "plain"
    forced = tmp_path / "forced"
    plain.mkdir()
    forced.mkdir()
    assert invoke_init(plain).exit_code == 0
    result = invoke_init(forced, "--force")
    assert result.exit_code == 0
    assert files_under(plain) == files_under(forced)
    assert all(
        (plain / path).read_bytes() == (forced / path).read_bytes()
        for path in files_under(plain)
    )
    assert result.stdout.splitlines()[-1].endswith("— 12 created, 0 overwritten, 0 skipped")


def test_ac14_force_restores_config(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    (tmp_path / "kb-config.json").write_text('{"schema": 1, "types": ["adr"]}\n', encoding="utf-8")
    result = invoke_init(tmp_path, "--force")
    assert result.exit_code == 0
    assert "overwritten  kb-config.json" in result.stdout.splitlines()
    assert (tmp_path / "kb-config.json").read_text(encoding="utf-8") == expected_manifest(
        timestamp_from_log(tmp_path)
    )["kb-config.json"]


def test_ac15_force_restores_index(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    (tmp_path / "raw/index.md").write_text("human edit\n", encoding="utf-8")
    result = invoke_init(tmp_path, "--force")
    assert result.exit_code == 0
    assert "overwritten  raw/index.md" in result.stdout.splitlines()
    assert (tmp_path / "raw/index.md").read_text(encoding="utf-8") == expected_manifest(
        timestamp_from_log(tmp_path)
    )["raw/index.md"]


def test_ac16_force_preserves_protected_entries(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    protected = [
        tmp_path / "governance/conventions.md",
        tmp_path / "governance/kb-config.md",
        tmp_path / "log.md",
    ]
    protected[0].write_text(protected[0].read_text(encoding="utf-8") + "human\n", encoding="utf-8")
    protected[1].write_text(protected[1].read_text(encoding="utf-8") + "human\n", encoding="utf-8")
    protected[2].write_text(protected[2].read_text(encoding="utf-8") + "extra one\nextra two\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in protected}
    result = invoke_init(tmp_path, "--force")
    assert result.exit_code == 0
    assert {path: path.read_bytes() for path in protected} == before
    for relative in ["governance/conventions.md", "governance/kb-config.md", "log.md"]:
        assert f"skipped  {relative} (exists)" in result.stdout.splitlines()
    assert result.stdout.splitlines()[-1].endswith("— 0 created, 9 overwritten, 3 skipped")


def test_ac17_force_never_writes_non_manifest_document(tmp_path, invoke_init) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    document = tmp_path / "raw/sources/x.md"
    document.write_bytes(b"---\ntype: raw-source\n---\nimmutable\xff")
    before = document.read_bytes()
    result = invoke_init(tmp_path, "--force")
    assert result.exit_code == 0
    assert document.read_bytes() == before
