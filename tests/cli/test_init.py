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
