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


def payload_for(result, path: str | None = None) -> list[dict[str, object]]:
    items = finding_payload(result)
    return items if path is None else [item for item in items if item["path"] == path]


def codes_for(result, path: str | None = None) -> list[str]:
    return [str(item["code"]) for item in payload_for(result, path)]


def valid_synthetic_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "id": "KB-000001",
        "type": "spec",
        "title": "Note",
        "description": "A concise note.",
        "status": "current",
        "derived_from": ["CHAT-000001"],
        "timestamp": "2026-07-16T10:00:00Z",
        "last_human_touch": "2026-07-16T10:00:00Z",
    }
    values.update(overrides)
    return values


def run_one(invoke_validate, root: Path, relative: str, values: dict[str, object]):
    make_doc(root, relative, values)
    return invoke_validate(root, "--json")


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


def test_ac11_raw_subtypes_must_match_their_class_directories(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/sources/chat.md", {
        "id": "CHAT-000001", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"
    })
    make_doc(root, "synthetic/source.md", {
        "id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file"
    })
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["LOC_TYPE_MISMATCH", "LOC_TYPE_MISMATCH"]


def test_ac12_root_synthetic_and_misplaced_governance_are_location_errors(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "note.md", valid_synthetic_values())
    make_doc(root, "synthetic/conventions.md", {
        "id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "Conventions", "description": "Rules."
    })
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["LOC_TYPE_MISMATCH", "LOC_TYPE_MISMATCH"]


def test_ac13_log_type_is_reserved_for_root_log(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "log.md", {"type": "log", "anything": [1]})
    make_doc(root, "raw/notes.md", {"type": "log", "id": 7})
    result = invoke_validate(root, "--json")
    assert codes_for(result, "log.md") == []
    assert codes_for(result, "raw/notes.md") == ["LOC_TYPE_MISMATCH"]


def test_ac14_index_location_rule_is_bidirectional(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "synthetic/listing.md", {"type": "index", "description": "Listing."})
    chat(root)
    make_doc(root, "synthetic/index.md", valid_synthetic_values())
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["LOC_TYPE_MISMATCH", "LOC_TYPE_MISMATCH"]


def test_ac15_matching_locations_are_valid_at_any_depth(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/sources/api/deep/x.md", {
        "id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file"
    })
    chat(root)
    make_doc(root, "synthetic/specs/x.md", valid_synthetic_values())
    result = invoke_validate(root, "--json")
    assert "LOC_TYPE_MISMATCH" not in codes_for(result)


def test_ac16_each_missing_synthetic_mandatory_field_is_reported(tmp_path, invoke_validate) -> None:
    for field in ["id", "title", "description", "status", "derived_from", "timestamp", "last_human_touch"]:
        root = make_kb(tmp_path / field)
        chat(root)
        values = valid_synthetic_values()
        del values[field]
        result = run_one(invoke_validate, root, "synthetic/note.md", values)
        matching = [item for item in payload_for(result, "synthetic/note.md") if item["code"] == "FM1_FIELD_MISSING"]
        assert len(matching) == 1
        assert f"'{field}'" in matching[0]["message"]


def test_ac17_multiple_missing_fields_emit_one_finding_each(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    values = valid_synthetic_values()
    for field in ["title", "status", "timestamp"]:
        del values[field]
    result = run_one(invoke_validate, root, "synthetic/note.md", values)
    assert codes_for(result, "synthetic/note.md").count("FM1_FIELD_MISSING") == 3


def test_ac18_raw_mandatory_set_excludes_title(tmp_path, invoke_validate) -> None:
    for field, expected in [("ingested_at", True), ("origin", True), ("title", False)]:
        root = make_kb(tmp_path / field)
        values = {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "title": "Source"}
        del values[field]
        result = run_one(invoke_validate, root, "raw/sources/source.md", values)
        assert ("FM1_FIELD_MISSING" in codes_for(result, "raw/sources/source.md")) is expected


def test_ac19_about_is_mandatory_only_for_feedback(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/feedback/f.md", {"id": "FEED-000001", "type": "feedback", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"})
    make_doc(root, "raw/chats/c.md", {"id": "CHAT-000001", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"})
    result = invoke_validate(root, "--json")
    assert codes_for(result, "raw/feedback/f.md") == ["FM1_FIELD_MISSING"]
    assert codes_for(result, "raw/chats/c.md") == []


def test_ac20_governance_and_index_require_description(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "governance/conventions.md", {"id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "Rules"})
    make_doc(root, "index.md", {"type": "index"})
    result = invoke_validate(root, "--json")
    assert codes_for(result) == ["FM1_FIELD_MISSING", "FM1_FIELD_MISSING"]


def test_ac21_status_vocabulary_is_literal_and_case_sensitive(tmp_path, invoke_validate) -> None:
    for value in ["accepted", "Current"]:
        root = make_kb(tmp_path / value)
        chat(root)
        result = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(status=value))
        assert "FM1_FIELD_INVALID" in codes_for(result, "synthetic/note.md")


def test_status_non_string_shape_is_invalid_without_crashing(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "list")
    chat(root)
    result = run_one(
        invoke_validate,
        root,
        "synthetic/note.md",
        valid_synthetic_values(status=["current"]),
    )
    assert codes_for(result, "synthetic/note.md") == ["FM1_FIELD_INVALID"]


def test_ac22_bad_derived_from_shape_preempts_graph_checks(tmp_path, invoke_validate) -> None:
    for offset, value in enumerate(["CHAT-000001", ["CHAT-000001", 42]]):
        root = make_kb(tmp_path / str(offset))
        chat(root)
        result = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(derived_from=value))
        anchored = codes_for(result, "synthetic/note.md")
        assert anchored == ["FM1_FIELD_INVALID"]


def test_ac23_timestamp_fields_accept_iso_offsets_and_reject_bad_dates(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "synthetic")
    chat(root)
    bad = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(timestamp="not-a-date"))
    assert "FM1_FIELD_INVALID" in codes_for(bad, "synthetic/note.md")
    root = make_kb(tmp_path / "raw")
    raw_bad = run_one(invoke_validate, root, "raw/sources/source.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-13-40", "origin": "file"})
    assert "FM1_FIELD_INVALID" in codes_for(raw_bad, "raw/sources/source.md")
    root = make_kb(tmp_path / "offset")
    chat(root)
    valid = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(timestamp="2026-07-16T10:00:00+02:00", last_human_touch="2026-07-16T10:00:00+02:00"))
    assert "FM1_FIELD_INVALID" not in codes_for(valid, "synthetic/note.md")


def test_ac24_required_strings_must_be_non_whitespace(tmp_path, invoke_validate) -> None:
    for offset, values in enumerate([valid_synthetic_values(title=""), valid_synthetic_values(description="   ")]):
        root = make_kb(tmp_path / str(offset))
        chat(root)
        result = run_one(invoke_validate, root, "synthetic/note.md", values)
        assert "FM1_FIELD_INVALID" in codes_for(result, "synthetic/note.md")


def test_ac25_tags_must_be_a_string_list_but_may_be_empty(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "bad")
    chat(root)
    bad = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(tags="api"))
    assert "FM1_FIELD_INVALID" in codes_for(bad, "synthetic/note.md")
    root = make_kb(tmp_path / "empty")
    chat(root)
    clean = run_one(invoke_validate, root, "synthetic/note.md", valid_synthetic_values(tags=[]))
    assert "FM1_FIELD_INVALID" not in codes_for(clean, "synthetic/note.md")


def test_ac26_reserved_keys_are_forbidden_outside_their_schema(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "raw/sources/s.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "about": "KB-000001"})
    make_doc(root, "raw/chats/c.md", {"id": "CHAT-000001", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin", "status": "current"})
    make_doc(root, "governance/conventions.md", {"id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "Rules", "description": "Rules.", "derived_from": ["RAW-000001"]})
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("FM1_KEY_FORBIDDEN") == 3
    assert "LINK_UNRESOLVED" not in codes_for(result)


def test_illegal_description_is_not_evaluated_for_length(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    result = run_one(
        invoke_validate,
        root,
        "raw/sources/source.md",
        {
            "id": "RAW-000001",
            "type": "raw-source",
            "ingested_at": "2026-07-16T09:00:00Z",
            "origin": "file",
            "description": "One. Two! Three?",
        },
    )
    assert codes_for(result, "raw/sources/source.md") == ["FM1_KEY_FORBIDDEN"]


def test_ac27_index_id_is_forbidden_without_id_checks(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    result = run_one(invoke_validate, root, "index.md", {"type": "index", "description": "Root.", "id": "KB-000009"})
    assert codes_for(result, "index.md") == ["FM1_KEY_FORBIDDEN"]


def test_ac28_unknown_extension_keys_are_never_flagged(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(custom_field="x"))
    make_doc(root, "raw/sources/s.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "custom_field": "x"})
    result = invoke_validate(root, "--json")
    assert result.exit_code == 0
    assert finding_payload(result) == []


def test_ac29_description_warning_uses_the_sentence_heuristic(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/note.md", valid_synthetic_values(description="One. Two! Three?"))
    make_doc(root, "index.md", {"type": "index", "description": "One. Two. Three."})
    make_doc(root, "raw/sources/two.md", {"id": "RAW-000001", "type": "raw-source", "ingested_at": "2026-07-16T09:00:00Z", "origin": "file", "description": "One. Two."})
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("FM1_DESCRIPTION_LONG") == 2


def test_ac30_declared_synthetic_type_is_clean_and_undeclared_warns(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", types=["spec"])
    chat(root)
    make_doc(root, "synthetic/retro.md", valid_synthetic_values(type="retro"))
    make_doc(root, "synthetic/spec.md", valid_synthetic_values(id="KB-000002"))
    result = invoke_validate(root, "--json")
    warnings = [item for item in finding_payload(result) if item["code"] == "TYPE_UNDECLARED"]
    assert len(warnings) == 1 and "retro" in warnings[0]["message"]


def test_ac31_empty_type_vocabulary_is_unconstrained(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", types=[])
    synthetic(root, type="retro")
    result = invoke_validate(root, "--json")
    assert "TYPE_UNDECLARED" not in codes_for(result)


def test_ac32_each_undeclared_tag_warns_in_list_order(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", tags=["api"])
    synthetic(root, tags=["api", "internal", "wip"])
    result = invoke_validate(root, "--json")
    warnings = [item for item in finding_payload(result) if item["code"] == "TAG_UNDECLARED"]
    assert [item["message"].split("'")[1] for item in warnings] == ["internal", "wip"]


def test_ac33_empty_tag_vocabulary_declares_no_tags(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", tags=[])
    synthetic(root, tags=["api"])
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("TAG_UNDECLARED") == 1


def test_ac34_noncanonical_synthetic_ids_are_invalid(tmp_path, invoke_validate) -> None:
    for offset, doc_id in enumerate(["KB-42", "kb-000042", "KB-FOO"]):
        root = make_kb(tmp_path / str(offset))
        synthetic(root, doc_id)
        result = invoke_validate(root, "--json")
        assert "ID_INVALID" in codes_for(result, "synthetic/note.md")


def test_ac35_seven_digit_id_with_leading_zero_is_invalid(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, "KB-0000042")
    result = invoke_validate(root, "--json")
    assert "ID_INVALID" in codes_for(result, "synthetic/note.md")


def test_ac36_governance_slug_and_numeric_growth_forms_are_class_specific(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(root, "governance/a.md", {"id": "GOVERNANCE-000001", "type": "conventions", "title": "A", "description": "A."})
    make_doc(root, "governance/b.md", {"id": "CONV-CONVENTIONS", "type": "conventions", "title": "B", "description": "B."})
    make_doc(root, "governance/c.md", {"id": "GOVERNANCE-CONVENTIONS", "type": "conventions", "title": "C", "description": "C."})
    chat(root)
    make_doc(root, "synthetic/large.md", valid_synthetic_values(id="KB-1000001"))
    result = invoke_validate(root, "--json")
    assert codes_for(result, "governance/a.md") == ["ID_INVALID"]
    assert codes_for(result, "governance/b.md") == ["ID_INVALID"]
    assert "ID_INVALID" not in codes_for(result, "governance/c.md")
    assert "ID_INVALID" not in codes_for(result, "synthetic/large.md")


def test_ac37_cross_class_numeric_prefixes_are_mismatches(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, "RAW-000009")
    make_doc(root, "raw/chats/other.md", {"id": "FEED-000002", "type": "chat", "ingested_at": "2026-07-16T09:00:00Z", "origin": "stdin"})
    result = invoke_validate(root, "--json")
    assert codes_for(result).count("ID_PREFIX_MISMATCH") == 2


def test_ac38_configured_prefix_wins(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb", id_prefixes={"synthetic": "SYN"})
    chat(root)
    make_doc(root, "synthetic/bad.md", valid_synthetic_values(id="KB-000001"))
    make_doc(root, "synthetic/good.md", valid_synthetic_values(id="SYN-000001"))
    result = invoke_validate(root, "--json")
    assert "ID_PREFIX_MISMATCH" in codes_for(result, "synthetic/bad.md")
    assert "ID_PREFIX_MISMATCH" not in codes_for(result, "synthetic/good.md")


def test_ac39_duplicate_literal_id_emits_one_finding_per_participant(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(root, "synthetic/a.md", valid_synthetic_values(id="KB-000007"))
    make_doc(root, "synthetic/b.md", valid_synthetic_values(id="KB-000007"))
    result = invoke_validate(root, "--json")
    duplicates = [item for item in finding_payload(result) if item["code"] == "ID_DUPLICATE"]
    assert [item["path"] for item in duplicates] == ["synthetic/a.md", "synthetic/b.md"]
    assert "synthetic/b.md" in duplicates[0]["message"]
    assert "synthetic/a.md" in duplicates[1]["message"]


def test_ac40_each_unresolved_parent_is_reported_in_list_order(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(
            derived_from=["CHAT-000001", "KB-999999", "RAW-999999"]
        ),
    )
    result = invoke_validate(root, "--json")
    links = [
        item
        for item in payload_for(result, "synthetic/note.md")
        if item["code"] == "LINK_UNRESOLVED"
    ]
    assert [item["message"].split("'")[1] for item in links] == [
        "KB-999999",
        "RAW-999999",
    ]


def test_ac41_supersedes_and_feedback_about_must_resolve(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    synthetic(root, supersedes="KB-999999")
    make_doc(
        root,
        "raw/feedback/f.md",
        {
            "id": "FEED-000001",
            "type": "feedback",
            "ingested_at": "2026-07-16T09:00:00Z",
            "origin": "stdin",
            "about": "KB-999999",
        },
    )
    result = invoke_validate(root, "--json")
    links = [
        item
        for item in finding_payload(result)
        if item["code"] == "LINK_UNRESOLVED"
    ]
    assert {item["message"].split()[0] for item in links} == {
        "about",
        "supersedes",
    }


def test_ac42_link_values_never_resolve_as_paths(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(derived_from=["raw/chats/session.md"]),
    )
    result = invoke_validate(root, "--json")
    assert "LINK_UNRESOLVED" in codes_for(result, "synthetic/note.md")


def test_ac43_reserved_governance_slug_resolves_as_a_parent(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(
        root,
        "governance/conventions.md",
        {
            "id": "GOVERNANCE-CONVENTIONS",
            "type": "conventions",
            "title": "Rules",
            "description": "Rules.",
        },
    )
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(
            derived_from=["GOVERNANCE-CONVENTIONS", "CHAT-000001"]
        ),
    )
    result = invoke_validate(root, "--json")
    assert "LINK_UNRESOLVED" not in codes_for(result, "synthetic/note.md")


def test_ac44_empty_parent_list_is_only_dg1(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(derived_from=[]),
    )
    result = invoke_validate(root, "--json")
    anchored = codes_for(result, "synthetic/note.md")
    assert anchored.count("DG1_NO_PARENTS") == 1
    assert "FM1_FIELD_MISSING" not in anchored
    assert "DG5_NO_SESSION_PARENT" not in anchored


def test_ac45_two_document_cycle_anchors_once_to_each_participant(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(
        root,
        "synthetic/a.md",
        valid_synthetic_values(
            id="KB-000001", derived_from=["KB-000002", "CHAT-000001"]
        ),
    )
    make_doc(
        root,
        "synthetic/b.md",
        valid_synthetic_values(
            id="KB-000002", derived_from=["KB-000001", "CHAT-000001"]
        ),
    )
    result = invoke_validate(root, "--json")
    cycles = [
        item for item in finding_payload(result) if item["code"] == "DG2_CYCLE"
    ]
    assert [item["path"] for item in cycles] == [
        "synthetic/a.md",
        "synthetic/b.md",
    ]
    assert (
        cycles[0]["message"]
        == "derivation cycle: KB-000001 -> KB-000002 -> KB-000001"
    )
    assert (
        cycles[1]["message"]
        == "derivation cycle: KB-000002 -> KB-000001 -> KB-000002"
    )


def test_ac46_self_parent_is_a_one_node_cycle(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(
        root,
        "synthetic/a.md",
        valid_synthetic_values(
            derived_from=["KB-000001", "CHAT-000001"]
        ),
    )
    result = invoke_validate(root, "--json")
    cycle = [
        item
        for item in payload_for(result, "synthetic/a.md")
        if item["code"] == "DG2_CYCLE"
    ]
    assert len(cycle) == 1
    assert cycle[0]["message"] == "derivation cycle: KB-000001 -> KB-000001"


def test_ac47_diamond_derivation_is_acyclic(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(
        root,
        "synthetic/one.md",
        valid_synthetic_values(id="KB-000001"),
    )
    make_doc(
        root,
        "synthetic/two.md",
        valid_synthetic_values(
            id="KB-000002", derived_from=["KB-000001", "CHAT-000001"]
        ),
    )
    make_doc(
        root,
        "synthetic/three.md",
        valid_synthetic_values(
            id="KB-000003", derived_from=["KB-000001", "CHAT-000001"]
        ),
    )
    make_doc(
        root,
        "synthetic/four.md",
        valid_synthetic_values(
            id="KB-000004",
            derived_from=[
                "KB-000002",
                "KB-000002",
                "KB-000003",
                "CHAT-000001",
            ],
        ),
    )
    result = invoke_validate(root, "--json")
    assert "DG2_CYCLE" not in codes_for(result)


def test_ac48_a_resolvable_chat_parent_is_required(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "without-chat")
    source(root)
    chat(root)
    make_doc(
        root,
        "synthetic/parent.md",
        valid_synthetic_values(
            id="KB-000002", derived_from=["CHAT-000001"]
        ),
    )
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(derived_from=["RAW-000001", "KB-000002"]),
    )
    result = invoke_validate(root, "--json")
    assert "DG5_NO_SESSION_PARENT" in codes_for(result, "synthetic/note.md")
    root = make_kb(tmp_path / "with-chat")
    source(root)
    chat(root)
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(derived_from=["RAW-000001", "CHAT-000001"]),
    )
    result = invoke_validate(root, "--json")
    assert "DG5_NO_SESSION_PARENT" not in codes_for(
        result, "synthetic/note.md"
    )


def test_ac49_dg5_uses_only_resolvable_parents(tmp_path, invoke_validate) -> None:
    root = make_kb(tmp_path / "none")
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(derived_from=["CHAT-999999"]),
    )
    result = invoke_validate(root, "--json")
    assert {"LINK_UNRESOLVED", "DG5_NO_SESSION_PARENT"}.issubset(
        codes_for(result, "synthetic/note.md")
    )
    root = make_kb(tmp_path / "one")
    chat(root)
    make_doc(
        root,
        "synthetic/note.md",
        valid_synthetic_values(derived_from=["KB-999999", "CHAT-000001"]),
    )
    result = invoke_validate(root, "--json")
    assert "LINK_UNRESOLVED" in codes_for(result, "synthetic/note.md")
    assert "DG5_NO_SESSION_PARENT" not in codes_for(result, "synthetic/note.md")


def test_derivation_cycles_use_the_first_document_for_duplicate_ids(
    tmp_path, invoke_validate
) -> None:
    root = make_kb(tmp_path / "kb")
    chat(root)
    make_doc(
        root,
        "synthetic/a-first.md",
        valid_synthetic_values(
            id="KB-000001", derived_from=["KB-000002", "CHAT-000001"]
        ),
    )
    make_doc(
        root,
        "synthetic/b-second.md",
        valid_synthetic_values(
            id="KB-000002", derived_from=["KB-000001", "CHAT-000001"]
        ),
    )
    make_doc(
        root,
        "synthetic/z-duplicate.md",
        valid_synthetic_values(
            id="KB-000001", derived_from=["CHAT-000001"]
        ),
    )

    result = invoke_validate(root, "--json")

    cycles = [
        item for item in finding_payload(result) if item["code"] == "DG2_CYCLE"
    ]
    assert [item["path"] for item in cycles] == [
        "synthetic/a-first.md",
        "synthetic/b-second.md",
    ]
