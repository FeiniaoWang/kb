from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from kb.cli.app import app
from kb.cli import revise_input


TIMESTAMP = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, yaml_text, _ = text.split("---", 2)
    values = yaml.safe_load(yaml_text)
    assert isinstance(values, dict)
    return values


def body_bytes(path: Path) -> bytes:
    content = path.read_bytes()
    closing = content.find(b"\n---", len(b"---\n"))
    assert closing >= 0
    remainder = content[closing + len(b"\n---") :]
    return remainder.removeprefix(b"\n")


def frontmatter_block(content: bytes) -> bytes:
    closing = content.find(b"\n---", len(b"---\n"))
    assert closing >= 0
    return content[: closing + len(b"\n---")]


def without_frontmatter_keys(content: bytes, keys: set[str]) -> bytes:
    block = frontmatter_block(content)
    for key in keys:
        if key == "derived_from":
            block = re.sub(
                rb"(?ms)^derived_from:.*?(?=^---$|^[A-Za-z_][^:\n]*:)",
                b"",
                block,
            )
        else:
            block = re.sub(
                rf"(?m)^{re.escape(key)}:[^\n]*(?:\n|$)".encode(),
                b"",
                block,
            )
    return block


def revised_rows(root: Path) -> list[str]:
    return [
        line
        for line in (root / "log.md").read_text(encoding="utf-8").splitlines()
        if " | revised | " in line
    ]


def invoke(runner: CliRunner, root: Path, *args: str, input=None):
    return runner.invoke(app, ["revise", *args, "--kb", str(root)], input=input)


def ingest(
    runner: CliRunner,
    root: Path,
    raw_class: str,
    title: str,
    body: str,
) -> tuple[str, Path]:
    result = runner.invoke(
        app,
        [
            "ingest",
            "--class",
            raw_class,
            "--from",
            "stdin",
            "--title",
            title,
            "--kb",
            str(root),
            "--json",
        ],
        input=body,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    return payload["id"], root / payload["path"]


def create(
    runner: CliRunner,
    root: Path,
    title: str,
    *parents: str,
    status: str = "draft",
) -> tuple[str, Path]:
    args = [
        "create",
        "--type",
        "spec",
        "--title",
        title,
        "--description",
        f"Description for {title}.",
        "--status",
        status,
    ]
    for parent in parents:
        args.extend(["--derived-from", parent])
    args.extend(["--kb", str(root), "--json"])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    return payload["id"], root / payload["path"]


def build_kb(runner: CliRunner, root: Path) -> tuple[Path, Path]:
    result = runner.invoke(app, ["init", "--root", str(root)])
    assert result.exit_code == 0, result.output
    chat_id, _ = ingest(runner, root, "chat", "Planning Session", "chat\n")
    _, target = create(runner, root, "Retry Policy", chat_id)
    source_id, _ = ingest(runner, root, "source", "New Evidence", "evidence\n")
    assert source_id == "RAW-000001"
    content = target.read_text(encoding="utf-8")
    content = re.sub(
        r"(?m)^timestamp: .*?$",
        "timestamp: 2020-01-01T00:00:00Z",
        content,
    )
    content = re.sub(
        r"(?m)^last_human_touch: .*?$",
        "last_human_touch: 2020-01-01T00:00:00Z",
        content,
    )
    target.write_text(content, encoding="utf-8")
    return root, target


@pytest.fixture
def kb_with_spec(tmp_path: Path, runner: CliRunner) -> tuple[Path, Path]:
    return build_kb(runner, tmp_path / "kb")


def test_ac01_append_parent_preserves_other_frontmatter_and_touch(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "title: Retry Policy\n",
            'title: "Retry Policy" # keep title\ncustom_key: "kept"\n# preserve this comment\n',
        ),
        encoding="utf-8",
    )
    before = target.read_bytes()
    before_values = frontmatter(target)
    result = invoke(runner, root, "KB-000001", "--add-parent", "RAW-000001")
    values = frontmatter(target)
    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "updated  synthetic/retry-policy.md",
        "revised KB-000001 as synthetic/retry-policy.md",
    ]
    assert values["derived_from"] == ["CHAT-000001", "RAW-000001"]
    assert values["timestamp"] != before_values["timestamp"]
    assert values["last_human_touch"] == before_values["last_human_touch"]
    assert without_frontmatter_keys(
        before, {"derived_from", "timestamp"}
    ) == without_frontmatter_keys(
        target.read_bytes(), {"derived_from", "timestamp"}
    )


def test_ac02_human_advances_touch_to_revision_timestamp(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    result = invoke(
        runner, root, "KB-000001", "--status", "current", "--human"
    )
    values = frontmatter(target)
    assert result.exit_code == 0
    assert values["last_human_touch"] == values["timestamp"]


def test_ac03_path_and_id_refs_resolve_same_target(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    first = invoke(runner, root, "KB-000001", "--status", "current")
    second = invoke(
        runner, root, "synthetic/retry-policy", "--status", "draft"
    )
    assert first.exit_code == second.exit_code == 0
    assert "revised KB-000001 as synthetic/retry-policy.md" in first.stdout
    assert "revised KB-000001 as synthetic/retry-policy.md" in second.stdout
    assert frontmatter(target)["status"] == "draft"


def test_ac04_parent_path_is_stored_as_canonical_id(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--add-parent",
        "raw/sources/new-evidence",
    )
    assert result.exit_code == 0
    assert frontmatter(target)["derived_from"][-1] == "RAW-000001"


def test_ac05_repeated_add_parent_fails_without_writes(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--add-parent",
        "RAW-000001",
        "--add-parent",
        "RAW-000001",
    )
    assert result.exit_code == 1
    assert "E_REVISE_PARENT_DUPLICATE" in result.stderr
    assert snapshot(root) == before


def test_ac06_existing_parent_fails_without_writes(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    result = invoke(
        runner, root, "KB-000001", "--add-parent", "CHAT-000001"
    )
    assert result.exit_code == 1
    assert "E_REVISE_PARENT_DUPLICATE" in result.stderr
    assert snapshot(root) == before


def test_ac07_unresolvable_parent_is_exit_one(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    result = invoke(
        runner, root, "KB-000001", "--add-parent", "RAW-999999"
    )
    assert result.exit_code == 1
    assert "E_REVISE_PARENT_UNRESOLVED" in result.stderr
    assert snapshot(root) == before


def test_ac08_direct_cycle_names_cycle_path(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    child_id, _ = create(runner, root, "Child", "CHAT-000001", "KB-000001")
    before = snapshot(root)
    result = invoke(runner, root, "KB-000001", "--add-parent", child_id)
    assert result.exit_code == 1
    assert "E_REVISE_CYCLE" in result.stderr
    assert "KB-000001 -> KB-000002 -> KB-000001" in result.stderr
    assert snapshot(root) == before


def test_ac09_transitive_cycle_is_rejected(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    middle, _ = create(runner, root, "Middle", "CHAT-000001", "KB-000001")
    leaf, _ = create(runner, root, "Leaf", "CHAT-000001", middle)
    before = snapshot(root)
    result = invoke(runner, root, "KB-000001", "--add-parent", leaf)
    assert result.exit_code == 1
    assert "E_REVISE_CYCLE" in result.stderr
    assert "KB-000001 -> KB-000003 -> KB-000002 -> KB-000001" in result.stderr
    assert snapshot(root) == before


def test_ac10_raw_and_governance_parents_append(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--add-parent",
        "RAW-000001",
        "--add-parent",
        "GOVERNANCE-CHARTER",
    )
    assert result.exit_code == 0
    assert frontmatter(target)["derived_from"][-2:] == [
        "RAW-000001",
        "GOVERNANCE-CHARTER",
    ]


def test_ac11_link_creates_links_mapping(runner: CliRunner, kb_with_spec) -> None:
    root, target = kb_with_spec
    result = invoke(
        runner, root, "KB-000001", "--link", "references=RAW-000001"
    )
    assert result.exit_code == 0
    assert frontmatter(target)["links"] == {"references": ["RAW-000001"]}


def test_ac12_link_appends_to_existing_type_in_order(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    assert invoke(
        runner, root, "KB-000001", "--link", "references=CHAT-000001"
    ).exit_code == 0
    assert invoke(
        runner, root, "KB-000001", "--link", "references=RAW-000001"
    ).exit_code == 0
    assert frontmatter(target)["links"]["references"] == [
        "CHAT-000001",
        "RAW-000001",
    ]


def test_ac13_distinct_link_types_keep_argument_order(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    existing = invoke(
        runner, root, "KB-000001", "--link", "references=CHAT-000001"
    )
    assert existing.exit_code == 0
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--link",
        "contradicts=CHAT-000001",
        "--link",
        "constrains=RAW-000001",
    )
    assert result.exit_code == 0
    assert list(frontmatter(target)["links"]) == [
        "references",
        "contradicts",
        "constrains",
    ]


def test_ac14_duplicate_link_target_is_rejected(
    runner: CliRunner, kb_with_spec, tmp_path: Path
) -> None:
    root, _ = kb_with_spec
    assert invoke(
        runner, root, "KB-000001", "--link", "references=RAW-000001"
    ).exit_code == 0
    before = snapshot(root)
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--link",
        "references=RAW-000001",
    )
    assert result.exit_code == 1
    assert "E_REVISE_LINK_DUPLICATE" in result.stderr
    assert snapshot(root) == before
    repeated_root, _ = build_kb(runner, tmp_path / "repeated")
    repeated_before = snapshot(repeated_root)
    repeated = invoke(
        runner,
        repeated_root,
        "KB-000001",
        "--link",
        "references=RAW-000001",
        "--link",
        "references=RAW-000001",
    )
    assert repeated.exit_code == 1
    assert "E_REVISE_LINK_DUPLICATE" in repeated.stderr
    assert snapshot(repeated_root) == repeated_before


def test_ac15_malformed_link_tokens_are_usage_errors(
    runner: CliRunner, tmp_path: Path
) -> None:
    for offset, token in enumerate(["references", "=KB-000001", "references="]):
        root, _ = build_kb(runner, tmp_path / str(offset))
        before = snapshot(root)
        result = invoke(runner, root, "KB-000001", "--link", token)
        assert result.exit_code == 2
        assert "E_REVISE_LINK_INVALID" in result.stderr
        assert snapshot(root) == before


def test_ac16_unresolvable_link_target_is_exit_one(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    result = invoke(
        runner, root, "KB-000001", "--link", "references=KB-999999"
    )
    assert result.exit_code == 1
    assert "E_REVISE_LINK_UNRESOLVED" in result.stderr
    assert snapshot(root) == before


def test_ac17_undeclared_type_warns_once_and_declared_type_does_not(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    declared = invoke(
        runner, root, "KB-000001", "--link", "references=CHAT-000001"
    )
    undeclared = invoke(
        runner,
        root,
        "KB-000001",
        "--link",
        "blocks=CHAT-000001",
        "--link",
        "blocks=RAW-000001",
    )
    assert declared.exit_code == undeclared.exit_code == 0
    assert declared.stderr == ""
    assert undeclared.stderr.count("blocks") == 1
    assert "not declared" in undeclared.stderr


def test_ac18_empty_link_vocabulary_warns_for_every_type(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    config_path = root / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["link_types"] = []
    config_path.write_text(json.dumps(config) + "\n", encoding="utf-8")
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--link",
        "references=CHAT-000001",
        "--link",
        "blocks=RAW-000001",
    )
    assert result.exit_code == 0
    assert "references" in result.stderr
    assert "blocks" in result.stderr


def test_ac19_status_values_rewrite_only_status_and_timestamp(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    baseline = frontmatter(target)
    for status in ["current", "draft", "retired"]:
        result = invoke(runner, root, "KB-000001", "--status", status)
        assert result.exit_code == 0
        values = frontmatter(target)
        assert values["status"] == status
        assert {
            key: value
            for key, value in values.items()
            if key not in {"status", "timestamp"}
        } == {
            key: value
            for key, value in baseline.items()
            if key not in {"status", "timestamp"}
        }
    invalid = invoke(runner, root, "KB-000001", "--status", "superseded")
    assert invalid.exit_code == 2
    assert "Invalid value" in invalid.stderr


def test_ac20_superseded_target_is_frozen(runner: CliRunner, kb_with_spec) -> None:
    root, target = kb_with_spec
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "status: draft", "status: superseded"
        ),
        encoding="utf-8",
    )
    before = snapshot(root)
    result = invoke(runner, root, "KB-000001", "--status", "retired")
    assert result.exit_code == 1
    assert "E_REVISE_TARGET_INVALID" in result.stderr
    assert snapshot(root) == before


def test_ac21_same_status_is_a_successful_revision(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    old_timestamp = frontmatter(target)["timestamp"]
    result = invoke(runner, root, "KB-000001", "--status", "draft")
    assert result.exit_code == 0
    assert frontmatter(target)["status"] == "draft"
    assert frontmatter(target)["timestamp"] != old_timestamp


def test_ac22_pending_parent_creates_marker(runner: CliRunner, kb_with_spec) -> None:
    root, target = kb_with_spec
    result = invoke(
        runner, root, "KB-000001", "--pending", "CHAT-000001"
    )
    assert result.exit_code == 0
    assert frontmatter(target)["pending_upstream"] == ["CHAT-000001"]


def test_ac23_pending_requires_final_parent_but_same_run_add_succeeds(
    runner: CliRunner, tmp_path: Path
) -> None:
    root, _ = build_kb(runner, tmp_path / "invalid")
    before = snapshot(root)
    invalid = invoke(runner, root, "KB-000001", "--pending", "RAW-000001")
    assert invalid.exit_code == 1
    assert "E_REVISE_PENDING_INVALID" in invalid.stderr
    assert snapshot(root) == before
    root, target = build_kb(runner, tmp_path / "valid")
    valid = invoke(
        runner,
        root,
        "KB-000001",
        "--add-parent",
        "RAW-000001",
        "--pending",
        "RAW-000001",
    )
    assert valid.exit_code == 0
    assert frontmatter(target)["pending_upstream"] == ["RAW-000001"]


def test_ac24_duplicate_marked_and_unresolvable_pending_fail(
    runner: CliRunner, tmp_path: Path
) -> None:
    root, _ = build_kb(runner, tmp_path / "marked")
    assert invoke(
        runner, root, "KB-000001", "--pending", "CHAT-000001"
    ).exit_code == 0
    before = snapshot(root)
    marked = invoke(runner, root, "KB-000001", "--pending", "CHAT-000001")
    assert marked.exit_code == 1
    assert "E_REVISE_PENDING_INVALID" in marked.stderr
    assert snapshot(root) == before
    root, _ = build_kb(runner, tmp_path / "repeated")
    repeated = invoke(
        runner,
        root,
        "KB-000001",
        "--pending",
        "CHAT-000001",
        "--pending",
        "CHAT-000001",
    )
    assert repeated.exit_code == 1
    assert "E_REVISE_PENDING_INVALID" in repeated.stderr
    root, _ = build_kb(runner, tmp_path / "unresolved")
    unresolved = invoke(
        runner, root, "KB-000001", "--pending", "CHAT-999999"
    )
    assert unresolved.exit_code == 1
    assert "E_REVISE_PENDING_UNRESOLVED" in unresolved.stderr


def test_ac25_clear_pending_removes_last_marker_and_key(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    assert invoke(
        runner, root, "KB-000001", "--pending", "CHAT-000001"
    ).exit_code == 0
    result = invoke(
        runner, root, "KB-000001", "--clear-pending", "CHAT-000001"
    )
    assert result.exit_code == 0
    assert "pending_upstream" not in frontmatter(target)


def test_ac26_invalid_clear_and_add_clear_conflict_fail(
    runner: CliRunner, tmp_path: Path
) -> None:
    root, _ = build_kb(runner, tmp_path / "absent")
    before = snapshot(root)
    absent = invoke(
        runner, root, "KB-000001", "--clear-pending", "CHAT-000001"
    )
    assert absent.exit_code == 1
    assert "E_REVISE_PENDING_INVALID" in absent.stderr
    assert snapshot(root) == before
    root, _ = build_kb(runner, tmp_path / "conflict")
    conflict = invoke(
        runner,
        root,
        "KB-000001",
        "--pending",
        "CHAT-000001",
        "--clear-pending",
        "CHAT-000001",
    )
    assert conflict.exit_code == 1
    assert "E_REVISE_PENDING_INVALID" in conflict.stderr


def test_ac27_body_file_replaces_only_body_and_revised_keys(
    runner: CliRunner, kb_with_spec, tmp_path: Path
) -> None:
    root, target = kb_with_spec
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "title: Retry Policy\n",
            'title: "Retry Policy" # keep title\ncustom_key: "kept"\n# preserve this comment\n',
        ),
        encoding="utf-8",
    )
    body_file = tmp_path / "body.md"
    body_file.write_text("new body\n", encoding="utf-8")
    before = target.read_bytes()
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--body-file",
        str(body_file),
    )
    assert result.exit_code == 0
    assert body_bytes(target) == b"new body\n"
    assert without_frontmatter_keys(
        before, {"timestamp"}
    ) == without_frontmatter_keys(target.read_bytes(), {"timestamp"})


def test_ac28_stdin_body_normalizes_line_endings_and_trailing_newline(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--body-file",
        "-",
        input="first\r\nsecond\r\n\r\n",
    )
    assert result.exit_code == 0
    assert body_bytes(target) == b"first\nsecond\n"


def test_ac29_whitespace_body_input_yields_empty_body(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    result = invoke(
        runner, root, "KB-000001", "--body-file", "-", input=" \t\r\n"
    )
    assert result.exit_code == 0
    assert target.read_bytes().rstrip().endswith(b"---")


def test_ac30_omitted_body_file_preserves_body_bytes(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    before = body_bytes(target)
    result = invoke(runner, root, "KB-000001", "--status", "current")
    assert result.exit_code == 0
    assert body_bytes(target) == before


def test_ac31_body_input_failures_have_typed_exit_codes_and_no_writes(
    runner: CliRunner, tmp_path: Path
) -> None:
    root, _ = build_kb(runner, tmp_path / "bytes")
    before = snapshot(root)
    non_text = invoke(
        runner,
        root,
        "KB-000001",
        "--body-file",
        "-",
        input=b"\xff\xfe",
    )
    assert non_text.exit_code == 1
    assert "E_REVISE_BODY_NOT_TEXT" in non_text.stderr
    assert snapshot(root) == before
    root, _ = build_kb(runner, tmp_path / "missing")
    before = snapshot(root)
    missing = invoke(
        runner,
        root,
        "KB-000001",
        "--body-file",
        str(tmp_path / "does-not-exist.md"),
    )
    assert missing.exit_code == 2
    assert "E_REVISE_BODY_NOT_FOUND" in missing.stderr
    assert snapshot(root) == before
    directory = invoke(
        runner,
        root,
        "KB-000001",
        "--body-file",
        str(tmp_path),
    )
    assert directory.exit_code == 2
    assert "E_REVISE_BODY_NOT_FOUND" in directory.stderr
    assert snapshot(root) == before


def test_ac32_no_change_option_is_usage_error(runner: CliRunner, kb_with_spec) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    result = invoke(runner, root, "KB-000001")
    assert result.exit_code == 2
    assert "E_REVISE_NO_CHANGES" in result.stderr
    assert snapshot(root) == before


def test_ac33_unknown_keys_comments_and_quotes_survive_byte_for_byte(
    runner: CliRunner, kb_with_spec
) -> None:
    root, target = kb_with_spec
    content = target.read_text(encoding="utf-8").replace(
        "title: Retry Policy\n",
        'title: "Retry Policy" # preserved comment\ncustom_extension: "yes"\n',
    )
    target.write_text(content, encoding="utf-8")
    result = invoke(runner, root, "KB-000001", "--status", "current")
    after = target.read_bytes()
    assert result.exit_code == 0
    assert b'title: "Retry Policy" # preserved comment\n' in after
    assert b'custom_extension: "yes"\n' in after


def test_ac34_duplicate_keys_and_nonlist_parents_are_not_editable(
    runner: CliRunner, tmp_path: Path
) -> None:
    for offset, mutate in enumerate(["duplicate", "shape"]):
        root, target = build_kb(runner, tmp_path / str(offset))
        content = target.read_text(encoding="utf-8")
        if mutate == "duplicate":
            content = content.replace(
                "description: Description for Retry Policy.\n",
                "description: first\ndescription: second\n",
            )
        else:
            content = re.sub(
                r"derived_from:\n  - CHAT-000001\n",
                "derived_from: CHAT-000001\n",
                content,
            )
        target.write_text(content, encoding="utf-8")
        before = snapshot(root)
        result = invoke(runner, root, "KB-000001", "--status", "current")
        assert result.exit_code == 1
        assert "E_REVISE_NOT_EDITABLE" in result.stderr
        assert snapshot(root) == before


def test_ac35_target_resolution_and_class_failures_are_typed(
    runner: CliRunner, tmp_path: Path
) -> None:
    cases = [
        ("KB-999999", "E_REVISE_TARGET_UNRESOLVED"),
        ("synthetic/index.md", "E_REVISE_TARGET_INVALID"),
        ("RAW-000001", "E_REVISE_TARGET_INVALID"),
        ("GOVERNANCE-CHARTER", "E_REVISE_TARGET_INVALID"),
    ]
    for offset, (ref, code) in enumerate(cases):
        root, _ = build_kb(runner, tmp_path / str(offset))
        before = snapshot(root)
        result = invoke(runner, root, ref, "--status", "current")
        assert result.exit_code == 1
        assert code in result.stderr
        assert snapshot(root) == before

    root, _ = build_kb(runner, tmp_path / "index-parent")
    index = root / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "type: index\n", "type: index\nid: KB-000099\n"
        ),
        encoding="utf-8",
    )
    before = snapshot(root)
    result = invoke(runner, root, "KB-000001", "--add-parent", "index.md")
    assert result.exit_code == 1
    assert "E_REVISE_PARENT_UNRESOLVED" in result.stderr
    assert snapshot(root) == before

    root, _ = build_kb(runner, tmp_path / "invalid-path-ref")
    invalid = root / "raw/sources/invalid.md"
    invalid.write_text(
        "---\nid: RAW-0000001\ntype: raw-source\ningested_at: 2026-07-20T09:00:00Z\norigin: file\ntitle: Invalid\n---\nbody\n",
        encoding="utf-8",
    )
    for flag, code in [
        ("--add-parent", "E_REVISE_PARENT_UNRESOLVED"),
        ("--link", "E_REVISE_LINK_UNRESOLVED"),
        ("--pending", "E_REVISE_PENDING_UNRESOLVED"),
    ]:
        value = "references=raw/sources/invalid.md" if flag == "--link" else "raw/sources/invalid.md"
        before = snapshot(root)
        result = invoke(runner, root, "KB-000001", flag, value)
        assert result.exit_code == 1
        assert code in result.stderr
        assert snapshot(root) == before


def test_ac36_malformed_scan_blocks_and_names_paths(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    bad = root / "synthetic" / "bad.md"
    bad.write_text("---\nid: KB-000099\n---\nbad\n", encoding="utf-8")
    before = snapshot(root)
    result = invoke(runner, root, "KB-000001", "--status", "current")
    assert result.exit_code == 2
    assert "E_REVISE_MALFORMED" in result.stderr
    assert "synthetic/bad.md" in result.stderr
    assert snapshot(root) == before


def test_ac37_log_gains_one_well_formed_revised_row(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    before = len(revised_rows(root))
    result = invoke(runner, root, "KB-000001", "--status", "current")
    rows = revised_rows(root)
    assert result.exit_code == 0
    assert len(rows) == before + 1
    match = re.fullmatch(
        rf"- ({TIMESTAMP}) \| revised \| kb-cli \| KB-000001 \| synthetic/retry-policy.md \(status current\)",
        rows[-1],
    )
    assert match is not None
    datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))


def test_ac38_revise_never_changes_indexes(runner: CliRunner, kb_with_spec) -> None:
    root, _ = kb_with_spec
    indexes = {path: path.read_bytes() for path in root.rglob("index.md")}
    result = invoke(runner, root, "KB-000001", "--status", "current")
    assert result.exit_code == 0
    assert {path: path.read_bytes() for path in root.rglob("index.md")} == indexes


def test_ac39_representative_preflight_errors_leave_kb_byte_identical(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    cases = [
        ("malformed-scan", ["--status", "current"], None, "E_REVISE_MALFORMED", 2),
        ("no-changes", [], None, "E_REVISE_NO_CHANGES", 2),
        ("link-token", ["--link", "references"], None, "E_REVISE_LINK_INVALID", 2),
        ("target-unresolved", ["--status", "current"], None, "E_REVISE_TARGET_UNRESOLVED", 1),
        ("target-invalid", ["--status", "current"], None, "E_REVISE_TARGET_INVALID", 1),
        ("not-editable", ["--status", "current"], None, "E_REVISE_NOT_EDITABLE", 1),
        ("parent-unresolved", ["--add-parent", "RAW-999999"], None, "E_REVISE_PARENT_UNRESOLVED", 1),
        ("parent-duplicate", ["--add-parent", "CHAT-000001"], None, "E_REVISE_PARENT_DUPLICATE", 1),
        ("cycle", ["--add-parent", "KB-000002"], None, "E_REVISE_CYCLE", 1),
        ("link-unresolved", ["--link", "references=KB-999999"], None, "E_REVISE_LINK_UNRESOLVED", 1),
        ("link-duplicate-existing", ["--link", "references=RAW-000001"], None, "E_REVISE_LINK_DUPLICATE", 1),
        ("link-duplicate-repeated", ["--link", "references=RAW-000001", "--link", "references=RAW-000001"], None, "E_REVISE_LINK_DUPLICATE", 1),
        ("pending-unresolved", ["--pending", "RAW-999999"], None, "E_REVISE_PENDING_UNRESOLVED", 1),
        ("pending-not-parent", ["--pending", "RAW-000001"], None, "E_REVISE_PENDING_INVALID", 1),
        ("pending-clear-absent", ["--clear-pending", "CHAT-000001"], None, "E_REVISE_PENDING_INVALID", 1),
        ("pending-add-clear-conflict", ["--pending", "CHAT-000001", "--clear-pending", "CHAT-000001"], None, "E_REVISE_PENDING_INVALID", 1),
        ("body-missing", ["--body-file", str(tmp_path / "missing-body.md")], None, "E_REVISE_BODY_NOT_FOUND", 2),
        ("body-not-regular", ["--body-file", str(tmp_path)], None, "E_REVISE_BODY_NOT_FOUND", 2),
        ("body-not-text", ["--body-file", "-"], b"\xff", "E_REVISE_BODY_NOT_TEXT", 1),
        ("body-stdin-io", ["--body-file", "-"], None, "E_REVISE_IO", 2),
        ("validation", ["--status", "current"], None, "E_REVISE_VALIDATION", 1),
    ]
    for offset, (case, args, input_data, code, exit_code) in enumerate(cases):
        root, target = build_kb(runner, tmp_path / f"case-{offset}")
        target_ref = "KB-000001"
        if case == "malformed-scan":
            (root / "synthetic" / "bad.md").write_text(
                "---\nid: KB-000099\n---\nbad\n", encoding="utf-8"
            )
        elif case == "target-unresolved":
            target_ref = "KB-999999"
        elif case == "target-invalid":
            target_ref = "RAW-000001"
        elif case == "not-editable":
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    "derived_from:\n  - CHAT-000001\n",
                    "derived_from: CHAT-000001\n",
                ),
                encoding="utf-8",
            )
        elif case == "cycle":
            create(runner, root, "Cycle Child", "CHAT-000001", "KB-000001")
        elif case == "link-duplicate-existing":
            assert invoke(
                runner, root, "KB-000001", "--link", "references=RAW-000001"
            ).exit_code == 0
        elif case == "pending-add-clear-conflict":
            args = ["--pending", "CHAT-000001", "--clear-pending", "CHAT-000001"]
        elif case == "validation":
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    "description: Description for Retry Policy.\n", ""
                ),
                encoding="utf-8",
            )
        elif case == "body-stdin-io":
            monkeypatch.setattr(
                revise_input, "sys", SimpleNamespace(stdin=_FailingStdin())
            )
        before = snapshot(root)
        result = invoke(runner, root, target_ref, *(args or []), input=input_data)
        assert result.exit_code == exit_code, result.output
        assert code in result.stderr
        assert snapshot(root) == before


def test_ac40_json_success_and_error_envelopes_are_exact(
    runner: CliRunner, tmp_path: Path
) -> None:
    root, _ = build_kb(runner, tmp_path / "success")
    success = invoke(
        runner,
        root,
        "KB-000001",
        "--status",
        "current",
        "--human",
        "--json",
    )
    assert success.exit_code == 0
    assert json.loads(success.stdout) == {
        "ok": True,
        "id": "KB-000001",
        "path": "synthetic/retry-policy.md",
        "updated": ["synthetic/retry-policy.md"],
        "warnings": [],
    }
    root, _ = build_kb(runner, tmp_path / "error")
    failure = invoke(
        runner,
        root,
        "KB-000001",
        "--add-parent",
        "CHAT-000001",
        "--json",
    )
    payload = json.loads(failure.stdout)
    assert failure.exit_code == 1
    assert failure.stderr == ""
    assert payload == {
        "error": {
            "code": "E_REVISE_PARENT_DUPLICATE",
            "message": payload["error"]["message"],
        }
    }
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]


def test_ac41_combined_run_applies_all_changes_once(
    runner: CliRunner, kb_with_spec, tmp_path: Path
) -> None:
    root, target = kb_with_spec
    body_file = tmp_path / "combined.md"
    body_file.write_text("combined\n", encoding="utf-8")
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--add-parent",
        "RAW-000001",
        "--link",
        "references=RAW-000001",
        "--status",
        "current",
        "--body-file",
        str(body_file),
        "--pending",
        "RAW-000001",
    )
    values = frontmatter(target)
    assert result.exit_code == 0
    assert values["derived_from"][-1] == "RAW-000001"
    assert values["links"] == {"references": ["RAW-000001"]}
    assert values["status"] == "current"
    assert values["pending_upstream"] == ["RAW-000001"]
    assert body_bytes(target) == b"combined\n"
    assert len(revised_rows(root)) == 1


def test_ac42_custom_and_default_actor_appear_in_log(
    runner: CliRunner, tmp_path: Path
) -> None:
    root, _ = build_kb(runner, tmp_path / "default")
    assert invoke(
        runner, root, "KB-000001", "--status", "current"
    ).exit_code == 0
    assert " | revised | kb-cli | " in revised_rows(root)[-1]
    root, _ = build_kb(runner, tmp_path / "custom")
    assert invoke(
        runner,
        root,
        "KB-000001",
        "--status",
        "current",
        "--actor",
        "agent-7",
    ).exit_code == 0
    assert " | revised | agent-7 | " in revised_rows(root)[-1]


def test_ac43_target_validation_errors_block_but_unrelated_errors_do_not(
    runner: CliRunner, tmp_path: Path
) -> None:
    root, target = build_kb(runner, tmp_path / "target-error")
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "description: Description for Retry Policy.\n", ""
        ),
        encoding="utf-8",
    )
    before = snapshot(root)
    failure = invoke(runner, root, "KB-000001", "--status", "current")
    assert failure.exit_code == 1
    assert "E_REVISE_VALIDATION" in failure.stderr
    assert "FM1_FIELD_MISSING" in failure.stderr
    assert snapshot(root) == before

    root, target = build_kb(runner, tmp_path / "target-cycle")
    child_id, _ = create(runner, root, "Cycle Child", "CHAT-000001", "KB-000001")
    target.write_text(
        target.read_text(encoding="utf-8").replace(
            "derived_from:\n  - CHAT-000001\n",
            f"derived_from:\n  - CHAT-000001\n  - {child_id}\n",
        ),
        encoding="utf-8",
    )
    before = snapshot(root)
    cycle = invoke(runner, root, "KB-000001", "--status", "current")
    assert cycle.exit_code == 1
    assert "E_REVISE_VALIDATION" in cycle.stderr
    assert "DG2_CYCLE" in cycle.stderr
    assert snapshot(root) == before

    root, _ = build_kb(runner, tmp_path / "unrelated-error")
    create(runner, root, "Unrelated", "CHAT-000001")
    unrelated = root / "synthetic" / "unrelated.md"
    unrelated.write_text(
        unrelated.read_text(encoding="utf-8").replace(
            "derived_from:\n  - CHAT-000001\n", "derived_from: []\n"
        ),
        encoding="utf-8",
    )
    success = invoke(runner, root, "KB-000001", "--status", "current")
    assert success.exit_code == 0, success.output


def test_revise_help_and_root_registration_order(runner: CliRunner) -> None:
    help_result = runner.invoke(app, ["revise", "--help"])
    assert help_result.exit_code == 0
    for text in [
        "Usage: root revise [OPTIONS] REF",
        "Revise a synthetic document in place, preserving its id.",
        "--add-parent TEXT",
        "Append a parent to derived_from; repeatable.",
        "--link TYPE=REF",
        "Append an associative link target; repeatable.",
        "--body-file TEXT",
        "body unchanged",
        "--status [draft|current|retired]",
        "human-directed status transition",
        "--pending TEXT",
        "--clear-pending TEXT",
        "--human",
        "--actor TEXT",
        "--kb PATH",
        "--json",
        "Examples:",
        "kb revise KB-000042 --status current --human",
    ]:
        assert text in help_result.stdout
    root_help = runner.invoke(app, ["--help"])
    positions = [root_help.stdout.index(name) for name in [
        "init", "ingest", "create", "revise", "validate"
    ]]
    assert positions == sorted(positions)


def test_environment_failure_precedes_external_body_acquisition(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "revise",
            "KB-000001",
            "--body-file",
            str(tmp_path / "missing.md"),
            "--kb",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "E_NO_KB" in result.stderr
    assert "E_REVISE_BODY_NOT_FOUND" not in result.stderr


def test_domain_preflight_precedes_external_body_acquisition(
    runner: CliRunner, tmp_path: Path
) -> None:
    missing_body = tmp_path / "missing.md"
    cases = [
        ("target", "KB-999999", [], "E_REVISE_TARGET_UNRESOLVED"),
        ("parent", "KB-000001", ["--add-parent", "RAW-999999"], "E_REVISE_PARENT_UNRESOLVED"),
        ("validation", "KB-000001", ["--status", "current"], "E_REVISE_VALIDATION"),
    ]
    for name, ref, options, expected in cases:
        root, target = build_kb(runner, tmp_path / name)
        if name == "validation":
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    "description: Description for Retry Policy.\n", ""
                ),
                encoding="utf-8",
            )
        result = invoke(
            runner,
            root,
            ref,
            *options,
            "--body-file",
            str(missing_body),
        )
        assert result.exit_code == 1
        assert expected in result.stderr
        assert "E_REVISE_BODY_NOT_FOUND" not in result.stderr


class _FailingStdin:
    @property
    def buffer(self):
        return self

    def read(self):
        raise OSError("stdin read failed")


class _UndecodableTextStdin:
    def read(self):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


class _ReplacingStdin:
    def __init__(self, referenced: Path) -> None:
        self.referenced = referenced

    def read(self):
        self.referenced.write_text(
            self.referenced.read_text(encoding="utf-8").replace(
                "evidence", "replaced evidence"
            ),
            encoding="utf-8",
        )
        return "new body"


def test_revise_failing_stdin_stream_maps_to_io_error_without_writes(
    runner: CliRunner, kb_with_spec, monkeypatch
) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    monkeypatch.setattr(
        revise_input, "sys", SimpleNamespace(stdin=_FailingStdin())
    )
    result = invoke(runner, root, "KB-000001", "--body-file", "-")
    assert result.exit_code == 2
    assert "E_REVISE_IO" in result.stderr
    assert "stdin read failed" in result.stderr
    assert snapshot(root) == before


def test_revise_text_stdin_decode_failure_maps_to_body_not_text(
    runner: CliRunner, kb_with_spec, monkeypatch
) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    monkeypatch.setattr(
        revise_input, "sys", SimpleNamespace(stdin=_UndecodableTextStdin())
    )
    result = invoke(runner, root, "KB-000001", "--body-file", "-")
    assert result.exit_code == 1
    assert "E_REVISE_BODY_NOT_TEXT" in result.stderr
    assert snapshot(root) == before


def test_revise_referenced_document_replaced_during_stdin_acquisition_is_atomic(
    runner: CliRunner, kb_with_spec, monkeypatch
) -> None:
    root, target = kb_with_spec
    referenced = root / "raw/sources/source.md"
    before_target = target.read_bytes()
    before_log = (root / "log.md").read_bytes()
    monkeypatch.setattr(
        revise_input, "sys", SimpleNamespace(stdin=_ReplacingStdin(referenced))
    )
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--add-parent",
        "RAW-000001",
        "--body-file",
        "-",
    )
    assert result.exit_code == 2
    assert "E_REVISE_IO" in result.stderr
    assert target.read_bytes() == before_target
    assert (root / "log.md").read_bytes() == before_log


def test_revise_invalid_tilde_user_path_maps_to_body_not_found_without_writes(
    runner: CliRunner, kb_with_spec
) -> None:
    root, _ = kb_with_spec
    before = snapshot(root)
    result = invoke(
        runner,
        root,
        "KB-000001",
        "--body-file",
        "~kb_task14_user_that_does_not_exist/body.md",
    )
    assert result.exit_code == 2
    assert "E_REVISE_BODY_NOT_FOUND" in result.stderr
    assert snapshot(root) == before
