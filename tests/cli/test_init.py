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
    from kb.core.scan import resolve_ref, scan

    kb = scan(tmp_path)
    assert resolve_ref(kb, "GOVERNANCE-CONVENTIONS").path == Path(
        "governance/conventions.md"
    )
    assert resolve_ref(kb, "GOVERNANCE-KB-CONFIG").path == Path(
        "governance/kb-config.md"
    )


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


def test_ac18_relative_nested_root_is_created_and_reported_absolute(tmp_path, invoke_init) -> None:
    result = invoke_init(tmp_path, "--root", "x/y/z")
    root = (tmp_path / "x/y/z").resolve()
    assert result.exit_code == 0
    assert files_under(root) == set(expected_manifest(timestamp_from_log(root)))
    assert result.stdout.splitlines()[-1].startswith(f"KB ready at {root} —")


def test_ac19_default_root_is_resolved_cwd(tmp_path, invoke_init) -> None:
    result = invoke_init(tmp_path)
    assert result.exit_code == 0
    assert (tmp_path / "kb-config.json").is_file()
    assert result.stdout.splitlines()[-1].startswith(f"KB ready at {tmp_path.resolve()} —")


def test_ac20_file_target_reports_not_directory(tmp_path, invoke_init) -> None:
    target = tmp_path / "target"
    target.write_text("occupied", encoding="utf-8")
    result = invoke_init(tmp_path, "--root", str(target))
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip() == f"E_INIT_NOT_DIR: target exists and is not a directory: {target.resolve()}"
    assert files_under(tmp_path) == {"target"}


def test_ac21_nested_kb_root_is_allowed(tmp_path, invoke_init) -> None:
    outer = tmp_path / "a"
    outer.mkdir()
    assert invoke_init(outer).exit_code == 0
    inner = outer / "b"
    result = invoke_init(outer, "--root", str(inner))
    assert result.exit_code == 0
    assert (outer / "kb-config.json").is_file()
    assert (inner / "kb-config.json").is_file()
    assert files_under(inner) == set(expected_manifest(timestamp_from_log(inner)))


def test_ac22_wrong_kind_manifest_paths_report_io_error(tmp_path, invoke_init) -> None:
    directory_case = tmp_path / "directory-case"
    directory_case.mkdir()
    (directory_case / "kb-config.json").mkdir()
    first = invoke_init(directory_case)
    assert first.exit_code == 2
    assert "E_INIT_IO" in first.stderr
    assert str(directory_case / "kb-config.json") in first.stderr
    assert (directory_case / "kb-config.json").is_dir()

    file_case = tmp_path / "file-case"
    file_case.mkdir()
    (file_case / "raw").write_text("occupied", encoding="utf-8")
    second = invoke_init(file_case)
    assert second.exit_code == 2
    assert "E_INIT_IO" in second.stderr
    assert str(file_case / "raw") in second.stderr
    assert (file_case / "raw").read_text(encoding="utf-8") == "occupied"


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="requires enforceable POSIX directory permissions",
)
def test_ac23_unwritable_target_reports_io_error(tmp_path, invoke_init) -> None:
    target = tmp_path / "unwritable"
    target.mkdir()
    target.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        result = invoke_init(tmp_path, "--root", str(target))
        assert result.exit_code == 2
        assert "E_INIT_IO" in result.stderr
        assert str(target) in result.stderr
    finally:
        target.chmod(stat.S_IRWXU)


def test_ac24_unknown_option_is_usage_error_without_files(tmp_path, invoke_init) -> None:
    result = invoke_init(tmp_path, "--bogus-flag")
    assert result.exit_code == 2
    assert "No such option: --bogus-flag" in result.stderr
    assert result.stdout == ""
    assert files_under(tmp_path) == set()


def test_init_default_cwd_failure_reports_typed_io_error(
    tmp_path, runner, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def raise_cwd_failure(cls) -> Path:
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(Path, "cwd", classmethod(raise_cwd_failure))
    result = runner.invoke(app, ["init"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip() == "E_INIT_IO: No such file or directory"
    assert files_under(tmp_path) == set()


def test_init_reports_first_non_directory_manifest_parent(tmp_path, invoke_init) -> None:
    blocker = tmp_path / "raw"
    blocker.write_text("occupied", encoding="utf-8")

    result = invoke_init(tmp_path)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip() == (
        f"E_INIT_IO: manifest path parent is not a directory: {blocker}"
    )
    assert blocker.read_text(encoding="utf-8") == "occupied"


def test_init_refuses_symlinked_manifest_parent_without_writing_outside_root(
    tmp_path, invoke_init
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "raw"
    link.symlink_to(outside, target_is_directory=True)

    result = invoke_init(root)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.startswith("E_INIT_IO: ")
    assert str(link) in result.stderr
    assert list(outside.iterdir()) == []
    assert (root / "governance/conventions.md").is_file()
    assert (root / "log.md").is_file()
    assert not (root / "synthetic").exists()


def test_init_force_refuses_cli_owned_file_symlink_without_changing_target(
    tmp_path, invoke_init
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    assert invoke_init(root).exit_code == 0
    external = tmp_path / "external-config.json"
    external.write_bytes(b"external config\xff")
    link = root / "kb-config.json"
    link.unlink()
    link.symlink_to(external)

    result = invoke_init(root, "--force")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.startswith("E_INIT_IO: ")
    assert str(link) in result.stderr
    assert link.is_symlink()
    assert external.read_bytes() == b"external config\xff"


def test_init_json_refuses_log_symlink_without_reading_or_appending_target(
    tmp_path, invoke_init
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    assert invoke_init(root).exit_code == 0
    external = tmp_path / "external-log.md"
    external.write_bytes(b"outside log without initialized entry\xff")
    link = root / "log.md"
    link.unlink()
    link.symlink_to(external)

    result = invoke_init(root, "--json")
    expected = {
        "error": {
            "code": "E_INIT_IO",
            "message": f"manifest path must not be a symlink or junction: {link}",
        }
    }

    assert result.exit_code == 2
    assert result.stdout == json.dumps(expected, ensure_ascii=False) + "\n"
    assert result.stderr == ""
    assert external.read_bytes() == b"outside log without initialized entry\xff"


def test_init_refuses_broken_manifest_symlink_without_creating_target(
    tmp_path, invoke_init
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    external = tmp_path / "missing-external-index.md"
    link = root / "index.md"
    link.symlink_to(external)

    result = invoke_init(root)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.startswith("E_INIT_IO: ")
    assert str(link) in result.stderr
    assert link.is_symlink()
    assert not external.exists()


def test_init_refuses_manifest_junction_before_file_operations(
    tmp_path, invoke_init, monkeypatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    junction = root / "governance"
    original_is_junction = Path.is_junction

    def report_manifest_junction(self) -> bool:
        return self == junction or original_is_junction(self)

    monkeypatch.setattr(Path, "is_junction", report_manifest_junction)

    result = invoke_init(root)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip() == (
        f"E_INIT_IO: manifest path must not be a symlink or junction: {junction}"
    )
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("json_output", [False, True])
def test_init_invalid_utf8_log_is_typed_io_error_on_the_correct_channel(
    tmp_path, invoke_init, json_output
) -> None:
    root = tmp_path / ("json-root" if json_output else "text-root")
    root.mkdir()
    assert invoke_init(root).exit_code == 0
    log_path = root / "log.md"
    log_path.write_bytes(b"\xff")

    arguments = ("--json",) if json_output else ()
    result = invoke_init(root, *arguments)
    message = (
        f"{log_path}: 'utf-8' codec can't decode byte 0xff in position 0: "
        "invalid start byte"
    )

    assert result.exit_code == 2
    if json_output:
        expected = {"error": {"code": "E_INIT_IO", "message": message}}
        assert result.stdout == json.dumps(expected, ensure_ascii=False) + "\n"
        assert result.stderr == ""
    else:
        assert result.stdout == ""
        assert result.stderr == f"E_INIT_IO: {message}\n"


def test_init_root_expanduser_runtime_error_is_exact_json_io_error(
    tmp_path, runner, monkeypatch
) -> None:
    requested = tmp_path / "requested"

    def fail_expanduser(self) -> Path:
        raise RuntimeError("home directory is unavailable")

    monkeypatch.setattr(Path, "expanduser", fail_expanduser)
    result = runner.invoke(app, ["init", "--json", "--root", str(requested)])
    expected = {
        "error": {
            "code": "E_INIT_IO",
            "message": f"{requested}: home directory is unavailable",
        }
    }

    assert result.exit_code == 2
    assert result.stdout == json.dumps(expected, ensure_ascii=False) + "\n"
    assert result.stderr == ""
    assert not requested.exists()


def test_ac25_json_success_has_exact_sorted_schema(tmp_path, invoke_init) -> None:
    result = invoke_init(tmp_path, "--json")
    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert result.stdout == json.dumps(payload, ensure_ascii=False) + "\n"
    assert set(payload) == {"ok", "root", "created", "overwritten", "skipped"}
    assert payload["ok"] is True
    assert payload["root"] == str(tmp_path.resolve())
    assert payload["created"] == sorted(expected_manifest("unused"))
    assert payload["overwritten"] == []
    assert payload["skipped"] == []
    assert set(payload["created"] + payload["overwritten"] + payload["skipped"]) == set(
        expected_manifest("unused")
    )


def test_ac26_json_not_directory_error_is_exact_envelope(tmp_path, invoke_init) -> None:
    target = tmp_path / "target"
    target.write_text("occupied", encoding="utf-8")
    result = invoke_init(tmp_path, "--json", "--root", str(target))
    expected = {
        "error": {
            "code": "E_INIT_NOT_DIR",
            "message": f"target exists and is not a directory: {target.resolve()}",
        }
    }
    assert result.exit_code == 2
    assert json.loads(result.stdout) == expected
    assert result.stdout == json.dumps(expected, ensure_ascii=False) + "\n"
    assert result.stderr == ""


def test_ac27_text_error_uses_stderr_only(tmp_path, invoke_init) -> None:
    target = tmp_path / "target"
    target.write_text("occupied", encoding="utf-8")
    result = invoke_init(tmp_path, "--root", str(target))
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "E_INIT_NOT_DIR" in result.stderr


def test_ac28_help_contains_normative_copy_and_examples(runner) -> None:
    result = runner.invoke(app, ["init", "--help"])
    normalized = " ".join(result.stdout.split())
    required = [
        "Scaffold a new knowledge base, or repair an existing one.",
        "Run this from the folder you want to become the KB root; it scaffolds the current directory by default (pass --root to target a different folder). Creates the standard KB layout (raw/, synthetic/, governance/), the root index.md and log.md, and kb-config.json — the file at the KB root that holds project configuration and marks the root for every other command. Safe to re-run: existing files are never touched; --force restores pristine kb-config.json and index.md files, but documents and log.md are never overwritten. Does not touch Git — putting the KB under version control is up to you.",
        "Folder to become the KB root. Resolved to an absolute path and created if it does not exist. [default: current directory]",
        "Restore pristine kb-config.json and index.md files. Documents and log.md are never touched.",
        "Emit results as JSON.",
        "Examples:",
        "kb init Scaffold a KB in the current directory (the KB root)",
        "kb init --root ~/team-kb Scaffold a KB at the given path",
        "kb init --force Restore pristine kb-config.json and index.md files",
        "kb init --json Machine-readable scaffold output",
    ]
    assert result.exit_code == 0
    for text in required:
        assert " ".join(text.split()) in normalized
    lowered = normalized.lower()
    assert "git init" not in lowered
    assert "git status" not in lowered
    assert "git add" not in lowered
    assert "git commit" not in lowered


def test_ac29_init_is_git_agnostic(tmp_path, invoke_init, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError(f"subprocess invocation is forbidden: {args!r} {kwargs!r}")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "check_call", forbidden)
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    result = invoke_init(tmp_path, "--json")
    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert not (tmp_path / ".git").exists()
    assert "git" not in payload


def test_ac30_fresh_scaffold_is_born_valid(tmp_path, invoke_init, runner) -> None:
    assert invoke_init(tmp_path).exit_code == 0
    result = runner.invoke(app, ["validate", "--kb", str(tmp_path)])
    assert result.exit_code == 0
