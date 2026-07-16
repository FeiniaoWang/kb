from __future__ import annotations

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


@pytest.mark.parametrize("reserved", ["index", "chat", "health"])
def test_ac28_reserved_synthetic_types_are_rejected_verbatim(
    reserved, initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
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
    initialized_kb, invoke_create
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


def test_ac48_missing_log_is_recreated_without_initialized_entry(
    initialized_kb, invoke_create
) -> None:
    add_chat(initialized_kb)
    (initialized_kb / "log.md").unlink()
    result = invoke_valid(invoke_create, initialized_kb)
    text = (initialized_kb / "log.md").read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert text.startswith(
        "---\ntype: log\n---\n<!-- KB history — append-only; written by `kb log`."
    )
    assert "# Knowledge Base Log\n\n" in text
    assert "| initialized |" not in text
    assert text.count("| created |") == 1


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
    add_chat(initialized_kb)
    target = add_synthetic(initialized_kb)
    before = snapshot(initialized_kb)
    read_bytes = Path.read_bytes

    def fail_target(path: Path) -> bytes:
        if path == target:
            raise OSError("target became unreadable")
        return read_bytes(path)

    with monkeypatch.context() as context:
        context.setattr(Path, "read_bytes", fail_target)
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
