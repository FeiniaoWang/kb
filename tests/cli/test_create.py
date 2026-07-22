from __future__ import annotations

import errno
import json
import os
import re
import stat
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


def test_environment_failure_precedes_missing_external_body(
    tmp_path: Path,
    invoke_create,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    result = invoke_create(
        outside,
        "--type",
        "spec",
        "--title",
        "Ordering",
        "--description",
        "Environment errors win.",
        "--derived-from",
        "CHAT-000001",
        "--body-file",
        str(tmp_path / "missing.md"),
    )
    assert result.exit_code == 2
    assert "E_NO_KB" in result.output
    assert "E_CREATE_BODY_NOT_FOUND" not in result.output


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


def add_synthetic(
    root: Path,
    *,
    relative: str = "synthetic/old.md",
    doc_id: str = "KB-000001",
    status: str | None = "current",
    extra: str = "",
    body: str = "Old body\n",
) -> Path:
    status_line = "" if status is None else f"status: {status}\n"
    return write_doc(
        root,
        relative,
        f"id: {doc_id}\ntype: spec\ntitle: Old\ndescription: Old.\n"
        f"{status_line}derived_from:\n  - CHAT-000001\n"
        "timestamp: 2026-06-02T14:11:08Z\n"
        "last_human_touch: 2026-06-02T14:11:08Z\n"
        f"{extra}",
        body,
    )


def supersede(invoke_create, root: Path, *extra: str):
    return invoke_create(
        root,
        "--type", "spec", "--title", "Replacement", "--description", "Replacement.",
        "--supersedes", "KB-000001", *extra,
    )


def test_ac19_superseded_id_is_appended_after_explicit_parent(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb, "CHAT-000002")
    add_synthetic(initialized_kb)
    assert supersede(
        invoke_create, initialized_kb, "--derived-from", "CHAT-000002"
    ).exit_code == 0
    assert split_document(initialized_kb / "synthetic/replacement.md")[0]["derived_from"] == [
        "CHAT-000002", "KB-000001"
    ]


def test_ac20_supersedes_alone_satisfies_parent_rule(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    add_synthetic(initialized_kb)
    assert supersede(invoke_create, initialized_kb).exit_code == 0
    assert split_document(initialized_kb / "synthetic/replacement.md")[0]["derived_from"] == ["KB-000001"]


def test_ac21_explicit_superseded_parent_keeps_its_position_without_duplicate(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb, "CHAT-000002")
    add_synthetic(initialized_kb)
    result = supersede(
        invoke_create, initialized_kb,
        "--derived-from", "KB-000001", "--derived-from", "CHAT-000002",
    )
    assert result.exit_code == 0
    assert split_document(initialized_kb / "synthetic/replacement.md")[0]["derived_from"] == [
        "KB-000001", "CHAT-000002"
    ]


def test_ac22_supersession_changes_exactly_three_values_and_preserves_bytes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    target = write_doc(
        initialized_kb,
        "synthetic/old.md",
        "unknown: {style: flow}\ntitle: Old\nstatus: 'current' # lifecycle\n"
        "type: spec\nid: KB-000001\nlast_human_touch: '2026-06-02T14:11:08Z'\n"
        "description: Old.\ntimestamp: 2026-06-02T14:11:08Z\n"
        "derived_from: [CHAT-000001]\n",
        "Old body  \n",
        newline="\r\n",
    )
    before = target.read_bytes()
    result = supersede(invoke_create, initialized_kb)
    after = target.read_bytes()
    _, _, new_yaml = split_document(initialized_kb / "synthetic/replacement.md")
    timestamp = re.search(rf"(?m)^timestamp: ({TIMESTAMP})$", new_yaml)
    assert result.exit_code == 0
    assert timestamp is not None
    updated_frontmatter, _, updated_yaml = split_document(target)
    assert updated_frontmatter["status"] == "superseded"
    target_timestamp = re.search(
        rf"(?m)^timestamp: '?({TIMESTAMP})'?(?:\r)?$", updated_yaml
    )
    target_touched = re.search(
        rf"(?m)^last_human_touch: '?({TIMESTAMP})'?(?:\r)?$", updated_yaml
    )
    assert target_timestamp is not None and target_touched is not None
    assert target_timestamp.group(1) == timestamp.group(1)
    assert target_touched.group(1) == timestamp.group(1)
    assert b"status: 'superseded' # lifecycle" in after
    assert timestamp.group(1).encode() in after
    restored = after.replace(b"superseded", b"current")
    restored = restored.replace(timestamp.group(1).encode(), b"2026-06-02T14:11:08Z")
    assert restored == before


def test_ac23_new_document_and_log_record_supersession(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb, "CHAT-000040")
    write_doc(
        initialized_kb,
        "synthetic/webhook-retry-policy.md",
        "id: KB-000031\ntype: spec\ntitle: Webhook Retry Policy\n"
        "description: Defines retry and backoff behavior for outbound webhooks.\n"
        "status: current\nderived_from:\n  - CHAT-000040\n"
        "timestamp: 2026-06-02T14:11:08Z\n"
        "last_human_touch: 2026-06-02T14:11:08Z\n",
    )
    add_synthetic(
        initialized_kb,
        relative="synthetic/highest.md",
        doc_id="KB-000041",
    )
    draft = tmp_path / "draft.md"
    draft.write_text("Replacement body\n", encoding="utf-8")
    result = invoke_create(
        initialized_kb,
        "--type", "spec",
        "--title", "Webhook Retry Policy",
        "--description", "Defines retry and backoff behavior for outbound webhooks.",
        "--derived-from", "CHAT-000040",
        "--supersedes", "KB-000031",
        "--status", "current",
        "--tag", "api",
        "--tag", "reliability",
        "--instructions", "Keep the examples runnable.",
        "--body-file", str(draft),
    )
    replacement = initialized_kb / "synthetic/webhook-retry-policy-kb-000042.md"
    frontmatter = split_document(replacement)[0]
    assert result.exit_code == 0
    assert frontmatter["supersedes"] == "KB-000031"
    assert split_document(
        initialized_kb / "synthetic/webhook-retry-policy.md"
    )[0]["status"] == "superseded"
    assert (initialized_kb / "log.md").read_text(encoding="utf-8").splitlines()[-1].endswith(
        "| KB-000042,KB-000031 | synthetic/webhook-retry-policy-kb-000042.md supersedes KB-000031"
    )


def test_ac24_unknown_supersedes_ref_is_finding_without_writes(
    initialized_kb, invoke_create
) -> None:
    before = snapshot(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Replacement", "--description", "Replacement.",
        "--supersedes", "KB-999999",
    )
    assert result.exit_code == 1
    assert "E_CREATE_SUPERSEDES_UNRESOLVED" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac25_raw_supersedes_target_is_invalid(
    initialized_kb, invoke_create
) -> None:
    write_doc(initialized_kb, "raw/sources/source.md", "id: RAW-000001\ntype: raw-source\n")
    before = snapshot(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Replacement", "--description", "Replacement.",
        "--supersedes", "RAW-000001",
    )
    assert result.exit_code == 1
    assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac26_non_live_or_missing_supersedes_status_is_invalid(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    for index, status in enumerate(["superseded", "retired", None], start=1):
        target = add_synthetic(initialized_kb, status=status)
        before = snapshot(initialized_kb)
        result = supersede(invoke_create, initialized_kb)
        assert result.exit_code == 1
        assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
        assert snapshot(initialized_kb) == before
        target.unlink()


def test_ac27_superseded_directory_index_is_not_regenerated(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    archive = initialized_kb / "synthetic/archive"
    archive.mkdir()
    (archive / "index.md").write_text(
        "---\ntype: index\ndescription: Archive.\n---\n# Archive\n\ncustom body\n",
        encoding="utf-8",
    )
    target = add_synthetic(initialized_kb, relative="synthetic/archive/old.md")
    index_before = (archive / "index.md").read_bytes()
    result = supersede(invoke_create, initialized_kb)
    assert result.exit_code == 0
    assert "updated  synthetic/archive/old.md" in result.stdout
    assert target.read_text(encoding="utf-8").find("status: superseded") >= 0
    assert (archive / "index.md").read_bytes() == index_before


@pytest.mark.parametrize("reserved", ["index", "chat", "health", "charter"])
def test_ac28_reserved_synthetic_types_are_rejected_verbatim(
    reserved, initialized_kb, invoke_create
) -> None:
    before = snapshot(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", reserved, "--title", "Bad", "--description", "Bad.",
        "--derived-from", "CHAT-000001",
    )
    assert result.exit_code == 2
    assert "E_CREATE_TYPE_RESERVED" in result.stderr and reserved in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac29_unknown_type_warns_once_and_declared_type_does_not(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["types"] = ["spec"]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    unknown = invoke_create(
        initialized_kb,
        "--type", "retro", "--title", "Retro", "--description", "Retro.",
        "--derived-from", "CHAT-000001",
    )
    declared = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Spec", "--description", "Spec.",
        "--derived-from", "CHAT-000001",
    )
    assert unknown.exit_code == declared.exit_code == 0
    assert unknown.stderr.lower().count("retro") == 1
    assert "type" not in declared.stderr.lower()
    assert split_document(initialized_kb / "synthetic/retro.md")[0]["type"] == "retro"


def test_ac30_unknown_tags_warn_once_and_tags_keep_first_order(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["tags"] = ["api"]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = invoke_valid(
        invoke_create, initialized_kb,
        "--tag", "api", "--tag", "internal", "--tag", "internal",
    )
    assert result.exit_code == 0
    assert split_document(initialized_kb / "synthetic/webhook-retry-policy.md")[0]["tags"] == ["api", "internal"]
    assert result.stderr.lower().count("internal") == 1
    assert "api" not in result.stderr.lower()


def test_ac31_description_warns_only_above_two_sentences(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["types"] = ["spec"]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    long = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Long", "--description", "One. Two! Three?",
        "--derived-from", "CHAT-000001",
    )
    short = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Short", "--description", "One. Two!",
        "--derived-from", "CHAT-000001",
    )
    assert long.exit_code == short.exit_code == 0
    assert long.stderr.lower().count("description") == 1
    assert short.stderr == ""
    assert split_document(initialized_kb / "synthetic/long.md")[0]["description"] == "One. Two! Three?"


def test_ac32_unicode_title_ascii_folds_filename_but_stays_verbatim(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Résumé Über 2026!", "--description", "Title.",
        "--derived-from", "CHAT-000001",
    )
    path = initialized_kb / "synthetic/resume-uber-2026.md"
    assert result.exit_code == 0 and path.is_file()
    assert split_document(path)[0]["title"] == "Résumé Über 2026!"


def test_ac33_empty_slug_uses_lowercase_id_filename(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "!!!", "--description", "Title.",
        "--derived-from", "CHAT-000001",
    )
    assert result.exit_code == 0
    assert (initialized_kb / "synthetic/kb-000001.md").is_file()


def test_ac34_collision_suffixes_id_without_overwriting_existing_file(
    initialized_kb, tmp_path, invoke_create, monkeypatch
) -> None:
    add_chat(initialized_kb)
    existing = add_synthetic(initialized_kb, relative="synthetic/notes.md")
    before = existing.read_bytes()
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Notes", "--description", "New notes.",
        "--derived-from", "CHAT-000001",
    )
    assert result.exit_code == 0
    assert (initialized_kb / "synthetic/notes-kb-000002.md").is_file()
    assert existing.read_bytes() == before

    from typer.testing import CliRunner
    from kb.cli.app import app

    for json_output in (False, True):
        nested_root = tmp_path / f"nested-create-{'json' if json_output else 'text'}"
        assert (
            CliRunner().invoke(app, ["init", "--root", str(nested_root)]).exit_code
            == 0
        )
        add_chat(nested_root)
        arguments = [
            "--type", "spec",
            "--title", "Index",
            "--description", "Reserved filename.",
            "--derived-from", "CHAT-000001",
            "--dest", "a/b",
        ]
        if json_output:
            arguments.append("--json")
        nested = invoke_create(nested_root, *arguments)
        document_relative = "synthetic/a/b/index-kb-000001.md"
        nested_index = nested_root / "synthetic/a/b/index.md"
        created = [
            document_relative,
            "synthetic/a/b/index.md",
            "synthetic/a/index.md",
        ]
        assert nested.exit_code == 0
        assert (nested_root / document_relative).is_file()
        assert "[Index](index-kb-000001.md)" in nested_index.read_text(
            encoding="utf-8"
        )
        if json_output:
            assert json.loads(nested.stdout) == {
                "ok": True,
                "id": "KB-000001",
                "path": document_relative,
                "superseded": None,
                "created": created,
                "updated": ["synthetic/index.md"],
            }
        else:
            assert nested.stdout.splitlines() == [
                *(f"created  {path}" for path in created),
                "updated  synthetic/index.md",
                f"created KB-000001 as {document_relative}",
            ]

    import kb.core.create as create_core

    real_prepare = create_core.prepare_write
    prepared_births: list[Path] = []

    def record_birth(context, intent):
        prepared_births.append(intent.birth.path)
        return real_prepare(context, intent)

    monkeypatch.setattr(create_core, "prepare_write", record_birth)
    for json_output in (False, True):
        damaged_root = tmp_path / f"damaged-create-{'json' if json_output else 'text'}"
        assert (
            CliRunner().invoke(app, ["init", "--root", str(damaged_root)]).exit_code
            == 0
        )
        add_chat(damaged_root)
        damaged = damaged_root / "synthetic/damaged"
        damaged.mkdir()
        before_damaged = snapshot(damaged_root)
        arguments = [
            "--type", "spec",
            "--title", "Index",
            "--description", "Reserved filename.",
            "--derived-from", "CHAT-000001",
            "--dest", "damaged",
        ]
        if json_output:
            arguments.append("--json")

        result = invoke_create(damaged_root, *arguments)

        assert result.exit_code == 2
        assert isinstance(result.exception, SystemExit)
        if json_output:
            assert json.loads(result.stdout)["error"]["code"] == "E_CREATE_IO"
            assert result.stderr == ""
        else:
            assert "E_CREATE_IO" in result.stderr
            assert result.stdout == ""
        assert prepared_births[-1] == Path(
            "synthetic/damaged/index-kb-000001.md"
        )
        assert snapshot(damaged_root) == before_damaged


def test_ac35_new_dest_gets_exact_index_and_updates_synthetic_index_only(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    root_index = (initialized_kb / "index.md").read_bytes()
    result = invoke_valid(invoke_create, initialized_kb, "--dest", "specs")
    expected = """---
type: index
description: Documents under synthetic/specs/.
---
# specs

<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->

## Files
* [KB-000001][Webhook Retry Policy](webhook-retry-policy.md) - Defines retry and backoff behavior for outbound webhooks.
"""
    assert result.exit_code == 0
    assert (initialized_kb / "synthetic/specs/index.md").read_text(encoding="utf-8") == expected
    assert "* [specs](specs/index.md) - Documents under synthetic/specs/." in (
        initialized_kb / "synthetic/index.md"
    ).read_text(encoding="utf-8")
    assert (initialized_kb / "index.md").read_bytes() == root_index
    assert result.stdout.splitlines() == [
        "updated  synthetic/index.md",
        "created  synthetic/specs/index.md",
        "created  synthetic/specs/webhook-retry-policy.md",
        "created KB-000001 as synthetic/specs/webhook-retry-policy.md",
    ]


def test_ac36_nested_dest_indexes_are_born_current_bottom_up(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb, "--dest", "a/b")
    assert result.exit_code == 0
    assert "## Subdirectories\n* [b](b/index.md) - Documents under synthetic/a/b/." in (
        initialized_kb / "synthetic/a/index.md"
    ).read_text(encoding="utf-8")
    assert "## Files\n* [KB-000001][Webhook Retry Policy](webhook-retry-policy.md)" in (
        initialized_kb / "synthetic/a/b/index.md"
    ).read_text(encoding="utf-8")
    assert result.stdout.splitlines() == [
        "created  synthetic/a/b/index.md",
        "created  synthetic/a/b/webhook-retry-policy.md",
        "created  synthetic/a/index.md",
        "updated  synthetic/index.md",
        "created KB-000001 as synthetic/a/b/webhook-retry-policy.md",
    ]


@pytest.mark.parametrize("json_output", [False, True])
def test_new_nested_dest_reserves_born_index_filename_during_create_collision_naming(
    json_output, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    arguments = [
        "--type", "spec",
        "--title", "Index",
        "--description", "Reserved filename.",
        "--derived-from", "CHAT-000001",
        "--dest", "a/b",
    ]
    if json_output:
        arguments.append("--json")

    result = invoke_create(initialized_kb, *arguments)

    document = initialized_kb / "synthetic/a/b/index-kb-000001.md"
    index = initialized_kb / "synthetic/a/b/index.md"
    assert result.exit_code == 0
    assert result.exception is None
    assert document.is_file()
    assert index.read_text(encoding="utf-8") == (
        "---\ntype: index\n"
        "description: Documents under synthetic/a/b/.\n---\n"
        "# b\n\n"
        "<!-- Generated by kb — do not edit; run `kb index` to regenerate. -->\n\n"
        "## Files\n"
        "* [KB-000001][Index](index-kb-000001.md) - Reserved filename.\n"
    )
    if json_output:
        assert json.loads(result.stdout) == {
            "ok": True,
            "id": "KB-000001",
            "path": "synthetic/a/b/index-kb-000001.md",
            "superseded": None,
            "created": [
                "synthetic/a/b/index-kb-000001.md",
                "synthetic/a/b/index.md",
                "synthetic/a/index.md",
            ],
            "updated": ["synthetic/index.md"],
        }
    else:
        assert result.stdout.splitlines() == [
            "created  synthetic/a/b/index-kb-000001.md",
            "created  synthetic/a/b/index.md",
            "created  synthetic/a/index.md",
            "updated  synthetic/index.md",
            "created KB-000001 as synthetic/a/b/index-kb-000001.md",
        ]


def test_ac37_existing_dest_updates_only_its_own_index(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    specs = initialized_kb / "synthetic/specs"
    specs.mkdir()
    (specs / "index.md").write_text(
        "---\ntype: index\ndescription: Specs.\n---\n# specs\n\n",
        encoding="utf-8",
    )
    parent_before = (initialized_kb / "synthetic/index.md").read_bytes()
    result = invoke_valid(invoke_create, initialized_kb, "--dest", "specs")
    assert result.exit_code == 0
    assert "updated  synthetic/specs/index.md" in result.stdout
    assert (initialized_kb / "synthetic/index.md").read_bytes() == parent_before


@pytest.mark.parametrize("dest", ["/abs", "../escape"])
def test_ac38_absolute_or_parent_dest_is_rejected_without_writes(
    dest, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb, "--dest", dest)
    assert result.exit_code == 2
    assert "E_CREATE_DEST_INVALID" in result.stderr and dest in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac39_missing_or_directory_body_file_is_environment_error(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    missing = invoke_valid(
        invoke_create, initialized_kb, "--body-file", str(tmp_path / "missing.md")
    )
    directory = invoke_valid(
        invoke_create, initialized_kb, "--body-file", str(tmp_path)
    )
    assert missing.exit_code == directory.exit_code == 2
    assert "E_CREATE_BODY_NOT_FOUND" in missing.stderr
    assert "E_CREATE_BODY_NOT_FOUND" in directory.stderr
    assert snapshot(initialized_kb) == before


def test_ac40_non_utf8_file_or_stdin_is_finding_without_writes(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    body = tmp_path / "binary.md"
    body.write_bytes(b"\xff")
    before = snapshot(initialized_kb)
    file_result = invoke_valid(
        invoke_create, initialized_kb, "--body-file", str(body)
    )
    stdin_result = invoke_valid(
        invoke_create, initialized_kb, "--body-file", "-", input=b"\xff"
    )
    assert file_result.exit_code == stdin_result.exit_code == 1
    assert "E_CREATE_BODY_NOT_TEXT" in file_result.stderr
    assert "E_CREATE_BODY_NOT_TEXT" in stdin_result.stderr
    assert snapshot(initialized_kb) == before


def test_ac41_discovered_or_explicit_configless_root_reports_shared_error(
    tmp_path, initialized_kb, invoke_create
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    before = snapshot(outside)
    implicit = invoke_create(
        outside,
        "--type", "spec", "--title", "No root", "--description", "No root.",
        "--derived-from", "CHAT-000001",
    )
    explicit = invoke_create(
        outside,
        "--type", "spec", "--title", "No root", "--description", "No root.",
        "--derived-from", "CHAT-000001", "--kb", str(outside),
    )
    for result in [implicit, explicit]:
        assert result.exit_code == 2
        assert "E_NO_KB" in result.stderr
        assert "not inside a knowledge base" in result.stderr
    assert snapshot(outside) == before


def test_ac42_invalid_config_is_environment_error_without_writes(
    initialized_kb, invoke_create
) -> None:
    (initialized_kb / "kb-config.json").write_text("{", encoding="utf-8")
    before = snapshot(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb)
    assert result.exit_code == 2
    assert "E_CONFIG_INVALID" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac43_newer_schema_is_environment_error_without_writes(
    initialized_kb, invoke_create
) -> None:
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["schema"] = 999
    config_path.write_text(json.dumps(config), encoding="utf-8")
    before = snapshot(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb)
    assert result.exit_code == 2
    assert "E_SCHEMA_UNSUPPORTED" in result.stderr
    assert snapshot(initialized_kb) == before


def test_ac44_missing_type_bad_status_and_unknown_option_are_typer_usage_errors(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    missing = invoke_create(
        initialized_kb,
        "--title", "Missing", "--description", "Missing.",
        "--derived-from", "CHAT-000001",
    )
    bad_status = invoke_valid(invoke_create, initialized_kb, "--status", "bogus")
    unknown = invoke_valid(invoke_create, initialized_kb, "--bogus-flag")
    assert missing.exit_code == bad_status.exit_code == unknown.exit_code == 2
    assert "Missing option" in missing.stderr
    assert "bogus" in bad_status.stderr
    assert "--bogus-flag" in unknown.stderr
    assert snapshot(initialized_kb) == before


def test_ac45_failed_reference_preflight_is_byte_atomic(
    initialized_kb, invoke_create
) -> None:
    before = snapshot(initialized_kb)
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Bad", "--description", "Bad.",
        "--derived-from", "KB-999999",
    )
    assert result.exit_code == 1
    assert snapshot(initialized_kb) == before


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="requires POSIX permissions",
)
def test_ac46_write_phase_os_error_is_typed_and_may_leave_partial_state(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    target = initialized_kb / "synthetic"
    original_mode = stat.S_IMODE(target.stat().st_mode)
    target.chmod(0o555)
    try:
        result = invoke_valid(invoke_create, initialized_kb)
    finally:
        target.chmod(original_mode)
    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert result.stderr.strip() != "E_CREATE_IO:"


def test_ac47_actor_option_is_recorded_in_log(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    result = invoke_valid(invoke_create, initialized_kb, "--actor", "kb-author")
    assert result.exit_code == 0
    assert "| created | kb-author | KB-000001 |" in (
        initialized_kb / "log.md"
    ).read_text(encoding="utf-8").splitlines()[-1]


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_unencodable_actor_is_stable_create_io_without_any_mutation(
    json_output,
    initialized_kb,
    invoke_create,
) -> None:
    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    arguments = ["--actor", "kb-author-\udcff"]
    if json_output:
        arguments.append("--json")

    result = invoke_valid(invoke_create, initialized_kb, *arguments)

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_CREATE_IO"
        assert "UTF-8" in error["message"]
        assert result.stderr == ""
    else:
        assert "E_CREATE_IO" in result.stderr
        assert "UTF-8" in result.stderr
        assert result.stdout == ""
    assert snapshot(initialized_kb) == before


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_unencodable_born_destination_is_stable_create_io_without_mutation(
    json_output,
    initialized_kb,
    invoke_create,
) -> None:
    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    destination = os.fsdecode(b"bad-\xff")
    arguments = ["--dest", destination]
    if json_output:
        arguments.append("--json")

    result = invoke_valid(invoke_create, initialized_kb, *arguments)

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_CREATE_IO"
        assert "UTF-8" in error["message"]
        assert result.stderr == ""
    else:
        assert "E_CREATE_IO" in result.stderr
        assert "UTF-8" in result.stderr
        assert result.stdout == ""
    assert snapshot(initialized_kb) == before


def test_ac48_missing_log_is_recreated_without_initialized_entry(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    (initialized_kb / "log.md").unlink()
    result = invoke_valid(invoke_create, initialized_kb)
    content = (initialized_kb / "log.md").read_bytes()
    scaffold = (
        "---\ntype: log\n---\n"
        "<!-- KB history — append-only; written by `kb log`. Format: "
        "- <UTC ISO> | <action> | <actor> | <ids or -> | <note> -->\n"
        "# Knowledge Base Log\n\n"
    ).encode("utf-8")
    assert result.exit_code == 0
    assert content.startswith(scaffold)
    row = content[len(scaffold) :].decode("utf-8")
    match = re.fullmatch(
        rf"- ({TIMESTAMP}) \| created \| kb-cli \| KB-000001 \| "
        r"synthetic/webhook-retry-policy\.md\n",
        row,
    )
    assert match is not None
    datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    assert b"| initialized |" not in content


def test_ac49_success_json_has_exact_fields_and_sorted_paths(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    add_synthetic(initialized_kb)
    superseded = supersede(invoke_create, initialized_kb, "--json")
    payload = json.loads(superseded.stdout)
    assert superseded.exit_code == 0
    assert set(payload) == {"ok", "id", "path", "superseded", "created", "updated"}
    assert payload == {
        "ok": True,
        "id": "KB-000002",
        "path": "synthetic/replacement.md",
        "superseded": "KB-000001",
        "created": ["synthetic/replacement.md"],
        "updated": ["synthetic/index.md", "synthetic/old.md"],
    }
    plain_root = initialized_kb.parent / "plain-kb"
    from typer.testing import CliRunner
    from kb.cli.app import app
    assert CliRunner().invoke(app, ["init", "--root", str(plain_root)]).exit_code == 0
    add_chat(plain_root)
    plain = invoke_valid(invoke_create, plain_root, "--json")
    assert json.loads(plain.stdout)["superseded"] is None


def test_ac50_error_json_is_exact_shared_envelope(
    initialized_kb, invoke_create
) -> None:
    result = invoke_create(
        initialized_kb,
        "--type", "spec", "--title", "Bad", "--description", "Bad.",
        "--derived-from", "KB-999999", "--json",
    )
    payload = json.loads(result.stdout)
    assert result.exit_code == 1
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message"}
    assert payload["error"]["code"] == "E_CREATE_PARENT_UNRESOLVED"
    assert "KB-999999" in payload["error"]["message"]
    assert result.stderr == ""


def test_ac51_help_contains_all_normative_create_strings(runner) -> None:
    result = runner.invoke(__import__("kb.cli.app", fromlist=["app"]).app, ["create", "--help"])
    assert result.exit_code == 0
    required = [
        "Create a synthetic document in the knowledge base.",
        "The deterministic write path for synthetic/ — the counterpart to kb ingest for raw evidence.",
        "Allocates the next sequential id, emits the full synthetic frontmatter, and files one Markdown document under synthetic/.",
        "At least one parent is required: every synthetic document derives from prior evidence, named via --derived-from (--supersedes also counts as a parent).",
        "--supersedes marks the replaced document superseded in the same atomic write.",
        "Updates the affected index.md listings and appends a created entry to log.md.",
        "Agents never hand-write synthetic files — id allocation and frontmatter stay CLI-authoritative.",
        "Does not touch Git.",
        "Synthetic document type (open vocabulary; reserved types rejected).",
        "Document title; also drives the target filename.",
        "One-to-two-sentence summary, shown in index.md listings.",
        "Parent document (id or KB-relative path); repeatable. At least one parent is required.",
        "Document this one replaces; marked superseded in the same write and counted as a parent.",
        "Lifecycle status at birth: draft or current. [default: draft]",
        "Tag for the tags frontmatter list; repeatable (a tag missing from the vocabulary warns).",
        "Standing guidance for the document's consumers, stored in the instructions field.",
        "File to read the body from, or - for stdin. [default: empty body]",
        "Subdirectory under synthetic/ (e.g. specs → synthetic/specs/). Created with its index.md if missing.",
        "Actor recorded in the log entry. [default: kb-cli]",
        "KB root. [default: discovered upward from the current directory]",
        "Emit results as JSON.",
        "kb create --type spec --title \"Retry Policy\" --description \"Retry rules.\" --derived-from CHAT-000027 --body-file draft.md    Draft from a body file",
        "kb create --type outcome --title \"Q3 Outcomes\" --description \"Q3 results.\" --derived-from CHAT-000012 --derived-from RAW-000004 --status current    Accepted at creation",
        "kb create --type spec --title \"Retry Policy\" --description \"Retry rules.\" --supersedes KB-000031 --derived-from CHAT-000040 --body-file -    Replace KB-000031, body from stdin",
        "kb create --type note --title \"Cache Sizing\" --description \"Sizing note.\" --derived-from RAW-000004 --dest notes    File under synthetic/notes/",
    ]
    for text in required:
        assert text in result.stdout


def test_ac52_create_never_invokes_git_or_creates_git_directory(
    initialized_kb, invoke_create, monkeypatch
) -> None:
    add_chat(initialized_kb)

    def forbidden(*args, **kwargs):
        raise AssertionError(f"subprocess invoked: {args!r} {kwargs!r}")

    monkeypatch.setattr("subprocess.run", forbidden)
    result = invoke_valid(invoke_create, initialized_kb)
    assert result.exit_code == 0
    assert not (initialized_kb / ".git").exists()


def test_destination_with_yaml_sensitive_text_writes_parseable_indexes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)

    result = invoke_valid(invoke_create, initialized_kb, "--dest", "foo: bar")

    index = initialized_kb / "synthetic/foo: bar/index.md"
    assert result.exit_code == 0
    assert split_document(index)[0]["description"] == (
        "Documents under synthetic/foo: bar/."
    )
    assert "created  synthetic/foo: bar/index.md" in result.stdout
    assert "updated  synthetic/index.md" in result.stdout


def test_supersedes_preparation_oserror_is_structured_without_writes(
    monkeypatch, initialized_kb, invoke_create
) -> None:
    import kb.core.write_pipeline as pipeline

    add_chat(initialized_kb)
    target = add_synthetic(initialized_kb)
    before = snapshot(initialized_kb)
    real_read = pipeline.read_rooted_bytes

    def fail_target(root, relative, root_identity, expected):
        if root / relative == target:
            raise OSError("target became unreadable")
        return real_read(root, relative, root_identity, expected)

    with monkeypatch.context() as context:
        context.setattr(pipeline, "read_rooted_bytes", fail_target)
        result = supersede(invoke_create, initialized_kb)

    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert "target became unreadable" in result.stderr
    assert snapshot(initialized_kb) == before


def test_supersedes_alias_lifecycle_is_structured_invalid_without_writes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    write_doc(
        initialized_kb,
        "synthetic/old.md",
        "lifecycle: &lifecycle current\nid: KB-000001\ntype: spec\ntitle: Old\n"
        "description: Old.\nstatus: *lifecycle\nderived_from:\n  - CHAT-000001\n"
        "timestamp: 2026-06-02T14:11:08Z\n"
        "last_human_touch: 2026-06-02T14:11:08Z\n",
    )
    before = snapshot(initialized_kb)
    result = supersede(invoke_create, initialized_kb)
    assert result.exit_code == 1
    assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
    assert "not directly editable" in result.stderr
    assert snapshot(initialized_kb) == before


def test_supersedes_repeats_collision_suffix_without_overwriting_existing_files(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    target = add_synthetic(
        initialized_kb,
        relative="synthetic/replacement.md",
    )
    occupied = add_synthetic(
        initialized_kb,
        relative="synthetic/replacement-kb-000003.md",
        doc_id="KB-000002",
        body="Occupied body\n",
    )
    occupied_before = occupied.read_bytes()
    result = supersede(invoke_create, initialized_kb)
    created = initialized_kb / "synthetic/replacement-kb-000003-kb-000003.md"
    assert result.exit_code == 0
    assert split_document(created)[0]["id"] == "KB-000003"
    assert occupied.read_bytes() == occupied_before
    assert split_document(target)[0]["status"] == "superseded"


def test_supersedes_duplicate_lifecycle_key_is_invalid_without_writes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    duplicates = {
        "status": "current",
        "timestamp": "2026-06-02T14:11:08Z",
        "last_human_touch": "2026-06-02T14:11:08Z",
    }
    for key, value in duplicates.items():
        target = add_synthetic(initialized_kb, extra=f"{key}: {value}\n")
        before = snapshot(initialized_kb)
        result = supersede(invoke_create, initialized_kb)
        assert result.exit_code == 1
        assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
        assert "exactly once" in result.stderr
        assert snapshot(initialized_kb) == before
        target.unlink()


def test_supersedes_non_scalar_lifecycle_key_is_invalid_without_writes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    for key in ("timestamp", "last_human_touch"):
        timestamp = (
            "timestamp:\n  nested: value\n"
            if key == "timestamp"
            else "timestamp: 2026-06-02T14:11:08Z\n"
        )
        touched = (
            "last_human_touch:\n  nested: value\n"
            if key == "last_human_touch"
            else "last_human_touch: 2026-06-02T14:11:08Z\n"
        )
        target = write_doc(
            initialized_kb,
            "synthetic/old.md",
            "id: KB-000001\ntype: spec\ntitle: Old\ndescription: Old.\n"
            "status: current\nderived_from:\n  - CHAT-000001\n"
            f"{timestamp}{touched}",
        )
        before = snapshot(initialized_kb)
        result = supersede(invoke_create, initialized_kb)
        assert result.exit_code == 1
        assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
        assert "not directly editable" in result.stderr
        assert snapshot(initialized_kb) == before
        target.unlink()


def test_supersedes_merge_only_lifecycle_is_structured_invalid_without_writes(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    write_doc(
        initialized_kb,
        "synthetic/old.md",
        "defaults: &lifecycle\n"
        "  status: current\n"
        "  timestamp: 2026-06-02T14:11:08Z\n"
        "  last_human_touch: 2026-06-02T14:11:08Z\n"
        "id: KB-000001\ntype: spec\ntitle: Old\ndescription: Old.\n"
        "derived_from:\n  - CHAT-000001\n<<: *lifecycle\n",
    )
    before = snapshot(initialized_kb)
    result = supersede(invoke_create, initialized_kb)
    assert result.exit_code == 1
    assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
    assert "explicit key" in result.stderr
    assert snapshot(initialized_kb) == before


@pytest.mark.parametrize(
    ("source", "expected_template"),
    [
        (
            b"---\n{id: KB-000001, type: spec, status: current, timestamp: 2026-06-02T14:11:08Z, unknown: keep}\n---\nBody  \n",
            b"---\n{id: KB-000001, type: spec, status: superseded, timestamp: {timestamp}, unknown: keep, last_human_touch: {timestamp}}\n---\nBody  \n",
        ),
        (
            b"---\n{id: KB-000001, type: spec, status: current, unknown: keep, }\n---\nBody  \n",
            b"---\n{id: KB-000001, type: spec, status: superseded, unknown: keep, timestamp: {timestamp}, last_human_touch: {timestamp}}\n---\nBody  \n",
        ),
        (
            b"---\nid: KB-000001\ntype: spec\nstatus: current\nunknown: keep\n...\n---\nBody  \n",
            b"---\nid: KB-000001\ntype: spec\nstatus: superseded\nunknown: keep\ntimestamp: {timestamp}\nlast_human_touch: {timestamp}\n...\n---\nBody  \n",
        ),
        (
            b"---\n{id: KB-000001, type: spec, status: current, # trailing separator comment\n}\n---\nBody  \n",
            b"---\n{id: KB-000001, type: spec, status: superseded, # trailing separator comment\ntimestamp: {timestamp}, last_human_touch: {timestamp}}\n---\nBody  \n",
        ),
    ],
    ids=[
        "flow-missing-one",
        "flow-missing-both",
        "document-end-marker",
        "flow-commented-trailing-separator",
    ],
)
def test_supersedes_inserts_missing_lifecycle_into_valid_yaml_atomically(
    source, expected_template, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    target = initialized_kb / "synthetic/old.md"
    target.write_bytes(source)

    result = supersede(invoke_create, initialized_kb)

    assert result.exit_code == 0
    _, _, replacement_yaml = split_document(
        initialized_kb / "synthetic/replacement.md"
    )
    timestamp_match = re.search(rf"(?m)^timestamp: ({TIMESTAMP})$", replacement_yaml)
    assert timestamp_match is not None
    timestamp = timestamp_match.group(1)
    expected = expected_template.replace(b"{timestamp}", timestamp.encode("ascii"))
    assert target.read_bytes() == expected
    updated = split_document(target)[0]
    assert updated["status"] == "superseded"
    assert updated["timestamp"] == updated["last_human_touch"]
    assert updated["timestamp"].isoformat().replace("+00:00", "Z") == timestamp


def test_windows_form_parent_destination_is_rejected_without_writes(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"outside")
    kb_before = snapshot(initialized_kb)
    outside_before = snapshot(outside)

    result = invoke_valid(
        invoke_create, initialized_kb, "--dest", r"..\..\outside"
    )

    assert result.exit_code == 2
    assert "E_CREATE_DEST_INVALID" in result.stderr
    assert snapshot(initialized_kb) == kb_before
    assert snapshot(outside) == outside_before


def test_symlink_destination_outside_is_rejected_without_writes(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"outside")
    destination = initialized_kb / "synthetic/linked"
    try:
        destination.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    kb_before = snapshot(initialized_kb)
    outside_before = snapshot(outside)
    link_target = os.readlink(destination)

    result = invoke_valid(invoke_create, initialized_kb, "--dest", "linked")

    assert result.exit_code == 2
    assert "E_CREATE_DEST_INVALID" in result.stderr
    assert snapshot(initialized_kb) == kb_before
    assert snapshot(outside) == outside_before
    assert destination.is_symlink() and os.readlink(destination) == link_target


def test_document_race_uses_exclusive_create_and_preserves_raced_bytes(
    monkeypatch, initialized_kb, invoke_create
) -> None:
    import kb.core.write_pipeline as pipeline

    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    target = initialized_kb / "synthetic/webhook-retry-policy.md"
    raced_bytes = b"raced-in bytes\n"
    real_create = pipeline.create_rooted_file_bytes
    raced = False

    def racing_create(
        root,
        relative,
        content,
        root_identity,
        *,
        parent_expected=None,
    ):
        nonlocal raced
        if root / relative == target and not raced:
            raced = True
            target.write_bytes(raced_bytes)
        real_create(
            root,
            relative,
            content,
            root_identity,
            parent_expected=parent_expected,
        )

    monkeypatch.setattr(pipeline, "create_rooted_file_bytes", racing_create)
    result = invoke_valid(invoke_create, initialized_kb)

    assert raced
    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert target.read_bytes() == raced_bytes
    assert snapshot(initialized_kb) == before | {
        "synthetic/webhook-retry-policy.md": raced_bytes
    }


def test_birth_link_race_after_filename_selection_is_typed_io_without_writes(
    monkeypatch, tmp_path, initialized_kb, invoke_create
) -> None:
    import kb.core.create as create_core

    add_chat(initialized_kb)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "external.md"
    external.write_bytes(b"external bytes\n")
    probe = tmp_path / "symlink-probe"
    try:
        probe.symlink_to(external)
        probe.unlink()
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    target = initialized_kb / "synthetic/webhook-retry-policy.md"
    real_prepare = create_core.prepare_write
    at_preflight: dict[str, dict[str, bytes] | str] = {}

    def insert_link_after_filename_selection(context, intent):
        assert intent.birth.path == Path("synthetic/webhook-retry-policy.md")
        target.symlink_to(external)
        at_preflight["kb"] = snapshot(initialized_kb)
        at_preflight["outside"] = snapshot(outside)
        at_preflight["link"] = os.readlink(target)
        return real_prepare(context, intent)

    monkeypatch.setattr(
        create_core,
        "prepare_write",
        insert_link_after_filename_selection,
    )

    result = invoke_valid(invoke_create, initialized_kb)

    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert snapshot(initialized_kb) == at_preflight["kb"]
    assert snapshot(outside) == at_preflight["outside"]
    assert target.is_symlink() and os.readlink(target) == at_preflight["link"]
    assert external.read_bytes() == b"external bytes\n"


@pytest.mark.parametrize(
    ("dest", "expected_created", "expected_index_fragment"),
    [
        (
            None,
            [
                "synthetic/index.md",
                "synthetic/webhook-retry-policy.md",
            ],
            "## Files\n* [KB-000001][Webhook Retry Policy](webhook-retry-policy.md)",
        ),
        (
            "a/b",
            [
                "synthetic/a/b/index.md",
                "synthetic/a/b/webhook-retry-policy.md",
                "synthetic/a/index.md",
                "synthetic/index.md",
            ],
            "## Subdirectories\n* [a](a/index.md) - Documents under synthetic/a/.",
        ),
    ],
    ids=["default", "nested"],
)
def test_missing_synthetic_base_is_created_with_current_indexes(
    dest, expected_created, expected_index_fragment, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    synthetic = initialized_kb / "synthetic"
    (synthetic / "index.md").unlink()
    synthetic.rmdir()
    before = snapshot(initialized_kb)
    arguments = ("--json",) if dest is None else ("--dest", dest, "--json")

    result = invoke_valid(invoke_create, initialized_kb, *arguments)

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["created"] == expected_created
    assert payload["updated"] == ["index.md"]
    assert expected_index_fragment in (synthetic / "index.md").read_text(
        encoding="utf-8"
    )
    expected_changes = set(expected_created) | {"index.md", "log.md"}
    assert changed(before, snapshot(initialized_kb)) == expected_changes
    for relative in expected_created:
        if relative.endswith("index.md"):
            assert split_document(initialized_kb / relative)[0]["type"] == "index"


def test_partial_prefix_config_uses_default_synthetic_prefix(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["id_prefixes"] = {"source": "SRC"}
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = invoke_valid(invoke_create, initialized_kb)

    assert result.exit_code == 0
    assert split_document(
        initialized_kb / "synthetic/webhook-retry-policy.md"
    )[0]["id"] == "KB-000001"


@pytest.mark.parametrize("prefix", ["lower", "BAD-PREFIX", 7, "GOVERNANCE"])
@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_invalid_synthetic_prefix_is_structured_config_error_without_writes(
    prefix, json_output, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    config_path = initialized_kb / "kb-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["id_prefixes"]["synthetic"] = prefix
    config_path.write_text(json.dumps(config), encoding="utf-8")
    before = snapshot(initialized_kb)
    arguments = ("--json",) if json_output else ()

    result = invoke_valid(invoke_create, initialized_kb, *arguments)

    assert result.exit_code == 2
    if json_output:
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "E_CONFIG_INVALID"
        assert result.stderr == ""
    else:
        assert "E_CONFIG_INVALID" in result.stderr
        assert result.stdout == ""
    assert snapshot(initialized_kb) == before


def test_symlinked_supersession_target_outside_is_invalid_without_writes(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = add_synthetic(outside, relative="old.md")
    target = initialized_kb / "synthetic/old.md"
    try:
        target.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    kb_before = snapshot(initialized_kb)
    outside_before = snapshot(outside)
    link_target = os.readlink(target)

    result = invoke_create(
        initialized_kb,
        "--type", "spec",
        "--title", "Replacement",
        "--description", "Replacement.",
        "--supersedes", "synthetic/old.md",
    )

    assert result.exit_code == 1
    assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
    assert snapshot(initialized_kb) == kb_before
    assert snapshot(outside) == outside_before
    assert target.is_symlink() and os.readlink(target) == link_target


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_supersession_path_race_keeps_exact_invalid_envelope_and_no_cli_writes(
    json_output,
    tmp_path,
    initialized_kb,
    invoke_create,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    add_chat(initialized_kb)
    target = add_synthetic(initialized_kb)
    target_before = target.read_bytes()
    outside = tmp_path / "outside-target.md"
    outside.write_bytes(b"outside")
    log_before = (initialized_kb / "log.md").read_bytes()
    index_before = (initialized_kb / "synthetic/index.md").read_bytes()
    real_open = safeio.os.open
    injected = False

    def replace_listed_target(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected
        if path == "old.md" and dir_fd is not None and not injected:
            injected = True
            os.rename(
                "old.md",
                "old-original.md",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.symlink(outside, "old.md", dir_fd=dir_fd)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", replace_listed_target)
    arguments = [
        "--type", "spec",
        "--title", "Replacement",
        "--description", "Replacement.",
        "--supersedes", "synthetic/old.md",
    ]
    if json_output:
        arguments.append("--json")

    result = invoke_create(initialized_kb, *arguments)

    assert injected
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_CREATE_SUPERSEDES_INVALID"
        assert result.stderr == ""
    else:
        assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
        assert result.stdout == ""
    assert (initialized_kb / "synthetic/old-original.md").read_bytes() == target_before
    assert target.is_symlink() and os.readlink(target) == str(outside)
    assert outside.read_bytes() == b"outside"
    assert not (initialized_kb / "synthetic/replacement.md").exists()
    assert (initialized_kb / "synthetic/index.md").read_bytes() == index_before
    assert (initialized_kb / "log.md").read_bytes() == log_before


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_supersession_target_lstat_failure_keeps_exact_invalid_envelope(
    json_output,
    initialized_kb,
    invoke_create,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    add_chat(initialized_kb)
    add_synthetic(initialized_kb)
    before = snapshot(initialized_kb)
    real_stat = safeio.os.stat
    injected = False

    def fail_listed_target(path, *, dir_fd=None, follow_symlinks=True):
        nonlocal injected
        if path == "old.md" and dir_fd is not None and not injected:
            injected = True
            raise FileNotFoundError(errno.ENOENT, "listed entry vanished", path)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(safeio.os, "stat", fail_listed_target)
    arguments = [
        "--type", "spec",
        "--title", "Replacement",
        "--description", "Replacement.",
        "--supersedes", "synthetic/old.md",
    ]
    if json_output:
        arguments.append("--json")

    result = invoke_create(initialized_kb, *arguments)

    assert injected
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_CREATE_SUPERSEDES_INVALID"
        assert result.stderr == ""
    else:
        assert "E_CREATE_SUPERSEDES_INVALID" in result.stderr
        assert result.stdout == ""
    assert snapshot(initialized_kb) == before


@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_unknown_supersedes_id_with_unrelated_unsafe_markdown_is_generic_io(
    json_output, tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    outside = tmp_path / "outside-unknown-supersedes"
    external = add_synthetic(
        outside,
        relative="external.md",
        doc_id="KB-900001",
    )
    unrelated = initialized_kb / "synthetic/unrelated.md"
    try:
        unrelated.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    kb_before = snapshot(initialized_kb)
    outside_before = snapshot(outside)
    arguments = [
        "--type", "spec",
        "--title", "Replacement",
        "--description", "Replacement.",
        "--supersedes", "KB-999999",
    ]
    if json_output:
        arguments.append("--json")

    result = invoke_create(initialized_kb, *arguments)

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)
    if json_output:
        error = json.loads(result.stdout)["error"]
        assert error["code"] == "E_CREATE_IO"
        assert "supersedes target" not in error["message"]
        assert result.stderr == ""
    else:
        assert "E_CREATE_IO" in result.stderr
        assert "E_CREATE_SUPERSEDES_INVALID" not in result.stderr
        assert "supersedes target" not in result.stderr
        assert result.stdout == ""
    assert snapshot(initialized_kb) == kb_before
    assert snapshot(outside) == outside_before


def test_regular_supersession_with_unrelated_markdown_symlink_maps_to_create_io(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    add_synthetic(initialized_kb)
    outside = tmp_path / "outside-unrelated"
    external = add_synthetic(
        outside,
        relative="external.md",
        doc_id="KB-900001",
    )
    unrelated = initialized_kb / "synthetic/unrelated.md"
    try:
        unrelated.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    kb_before = snapshot(initialized_kb)
    outside_before = snapshot(outside)

    result = supersede(invoke_create, initialized_kb)

    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert "E_CREATE_SUPERSEDES_INVALID" not in result.stderr
    assert snapshot(initialized_kb) == kb_before
    assert snapshot(outside) == outside_before


def test_final_config_access_failure_remains_config_invalid_for_create(
    initialized_kb,
    invoke_create,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    add_chat(initialized_kb)
    before = snapshot(initialized_kb)
    real_read = safeio._RootedReader.read_file

    def fail_config_read(reader, relative, **kwargs):
        if relative == Path("kb-config.json"):
            raise PermissionError(errno.EACCES, "config unreadable")
        return real_read(reader, relative, **kwargs)

    monkeypatch.setattr(safeio._RootedReader, "read_file", fail_config_read)

    result = invoke_valid(invoke_create, initialized_kb)

    assert result.exit_code == 2
    assert "E_CONFIG_INVALID" in result.stderr
    assert "E_CREATE_IO" not in result.stderr
    assert snapshot(initialized_kb) == before


def test_index_losing_closing_delimiter_during_create_preflight_maps_to_io(
    initialized_kb,
    invoke_create,
    monkeypatch,
) -> None:
    import kb.core.create as create_core

    add_chat(initialized_kb)
    index = initialized_kb / "synthetic/index.md"
    real_prepare = create_core.prepare_write
    injected: dict[str, dict[str, bytes]] = {}

    def corrupt_index_then_prepare(context, intent):
        index.write_bytes(b"---\ntype: index\n")
        injected["snapshot"] = snapshot(initialized_kb)
        return real_prepare(context, intent)

    monkeypatch.setattr(create_core, "prepare_write", corrupt_index_then_prepare)

    result = invoke_valid(invoke_create, initialized_kb)

    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert snapshot(initialized_kb) == injected["snapshot"]


def test_symlinked_existing_index_outside_fails_before_any_writes(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = write_doc(
        outside,
        "index.md",
        "type: index\ndescription: External index.\n",
        "# External\n",
    )
    index = initialized_kb / "synthetic/index.md"
    index.unlink()
    try:
        index.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    kb_before = snapshot(initialized_kb)
    outside_before = snapshot(outside)
    link_target = os.readlink(index)

    result = invoke_valid(invoke_create, initialized_kb)

    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert snapshot(initialized_kb) == kb_before
    assert snapshot(outside) == outside_before
    assert index.is_symlink() and os.readlink(index) == link_target


def test_symlinked_existing_log_outside_fails_before_any_writes(
    tmp_path, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = write_doc(
        outside,
        "log.md",
        "type: log\n",
        "# External log\n",
    )
    log = initialized_kb / "log.md"
    log.unlink()
    try:
        log.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")
    kb_before = snapshot(initialized_kb)
    outside_before = snapshot(outside)
    link_target = os.readlink(log)

    result = invoke_valid(invoke_create, initialized_kb)

    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert snapshot(initialized_kb) == kb_before
    assert snapshot(outside) == outside_before
    assert log.is_symlink() and os.readlink(log) == link_target


def test_replaced_root_before_preparation_maps_to_create_io_without_writes(
    tmp_path,
    initialized_kb,
    invoke_create,
    monkeypatch,
) -> None:
    import kb.core.create as create_core
    from kb.core.housekeeping import init_kb

    add_chat(initialized_kb)
    original = tmp_path / "original-kb"
    replacement_holder: dict[str, Path] = {}
    real_prepare = create_core.prepare_write

    def replace_root(context, intent):
        initialized_kb.rename(original)
        assert init_kb(initialized_kb).root == initialized_kb.resolve()
        replacement_holder["root"] = initialized_kb
        return real_prepare(context, intent)

    monkeypatch.setattr(create_core, "prepare_write", replace_root)

    result = invoke_valid(invoke_create, initialized_kb)

    replacement = replacement_holder["root"]
    assert result.exit_code == 2
    assert "E_CREATE_IO" in result.stderr
    assert not (original / "synthetic/webhook-retry-policy.md").exists()
    assert not (replacement / "synthetic/webhook-retry-policy.md").exists()
