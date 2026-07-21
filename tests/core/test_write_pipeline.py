from __future__ import annotations

from pathlib import Path

import pytest

from kb.core.housekeeping import LogEntry, init_kb
from kb.core.write_pipeline import (
    AllocationBlocked,
    CompanionBirth,
    DocumentBirth,
    MutationTarget,
    WriteFailure,
    WriteIntent,
    apply_write,
    load_write_context,
    prepare_write,
)


def document_bytes(
    doc_id: str = "KB-000001",
    title: str = "Planned",
    description: str | None = "Planned document.",
) -> bytes:
    description_line = "" if description is None else f"description: {description}\n"
    return (
        "---\n"
        f"id: {doc_id}\n"
        "type: spec\n"
        f"title: {title}\n"
        f"{description_line}"
        "---\n"
        "Body\n"
    ).encode("utf-8")


def log_entry(doc_id: str = "KB-000001") -> LogEntry:
    return LogEntry(
        at="2026-07-20T12:00:00Z",
        action="created",
        actor="test",
        doc_ids=[doc_id],
        note="synthetic/planned.md",
    )


def initialized(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    assert init_kb(root).root == root.resolve()
    return root


def test_load_context_blocks_malformed_documents_without_writes(tmp_path) -> None:
    root = initialized(tmp_path)
    malformed = root / "synthetic/bad.md"
    malformed.write_text("not frontmatter\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(AllocationBlocked) as raised:
        load_write_context(root)

    assert raised.value.paths == (Path("synthetic/bad.md"),)
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize(
    "relative",
    [Path("/absolute.md"), Path("../escape.md"), Path(r"synthetic\escape.md")],
)
def test_prepare_rejects_non_relative_posix_birth_paths_before_writes(
    tmp_path,
    relative,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    intent = WriteIntent(
        birth=DocumentBirth(path=relative, content=document_bytes()),
        log_entry=log_entry(),
    )

    with pytest.raises(ValueError):
        prepare_write(context, intent)

    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_prepare_exposes_identity_checked_mutation_source_without_writes(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    old.write_bytes(document_bytes("KB-000002", "Old", "Old."))
    context = load_write_context(root)
    intent = WriteIntent(
        birth=DocumentBirth(
            path=Path("synthetic/planned.md"),
            content=document_bytes(),
        ),
        mutations=[MutationTarget(key="superseded", path=Path("synthetic/old.md"))],
        log_entry=log_entry(),
    )

    prepared = prepare_write(context, intent)

    assert prepared.sources["superseded"].content == old.read_bytes()
    assert not (root / "synthetic/planned.md").exists()


def test_prepare_rejects_markdown_companion_before_writes(tmp_path) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    intent = WriteIntent(
        birth=DocumentBirth(
            path=Path("raw/sources/evidence.md"),
            content=(
                b"---\nid: RAW-000001\ntype: raw-source\n"
                b"title: Evidence\n---\nStub\n"
            ),
            companions_before=[
                CompanionBirth(path=Path("raw/sources/original.md"), content=b"binary")
            ],
        ),
        log_entry=LogEntry(
            at="2026-07-20T12:00:00Z",
            action="ingested",
            actor="test",
            doc_ids=["RAW-000001"],
            note="raw/sources/evidence.md",
        ),
    )

    with pytest.raises(ValueError, match="must not be Markdown"):
        prepare_write(context, intent)


def test_prepare_rejects_directory_at_birth_path_before_writes(tmp_path) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    target = root / "synthetic/planned.md"
    target.mkdir()
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(ValueError, match="must be a file path"):
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"), content=document_bytes()
                ),
                log_entry=log_entry(),
            ),
        )

    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_apply_creates_nested_indexes_document_updates_ancestor_and_logs(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/b/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )

    receipt = apply_write(prepared)

    assert receipt.created == [
        "synthetic/a/b/index.md",
        "synthetic/a/b/planned.md",
        "synthetic/a/index.md",
    ]
    assert receipt.updated == ["synthetic/index.md"]
    assert "(planned.md)" in (root / "synthetic/a/b/index.md").read_text(
        encoding="utf-8"
    )
    assert "(a/index.md)" in (root / "synthetic/index.md").read_text(
        encoding="utf-8"
    )
    assert " | created | test | KB-000001 | " in (root / "log.md").read_text(
        encoding="utf-8"
    )


def test_companion_is_created_before_document_and_excluded_from_index(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    seen: list[str] = []
    real_create = pipeline.create_file_bytes

    def record(path: Path, content: bytes) -> None:
        seen.append(path.relative_to(root).as_posix())
        real_create(path, content)

    monkeypatch.setattr(pipeline, "create_file_bytes", record)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("raw/sources/evidence.md"),
                content=(
                    b"---\nid: RAW-000001\ntype: raw-source\n"
                    b"title: Evidence\n---\nStub\n"
                ),
                companions_before=[
                    CompanionBirth(
                        path=Path("raw/sources/evidence.pdf"),
                        content=b"%PDF",
                    )
                ],
            ),
            log_entry=LogEntry(
                at="2026-07-20T12:00:00Z",
                action="ingested",
                actor="test",
                doc_ids=["RAW-000001"],
                note="raw/sources/evidence.md",
            ),
        ),
    )

    receipt = apply_write(prepared)

    assert seen.index("raw/sources/evidence.pdf") < seen.index(
        "raw/sources/evidence.md"
    )
    assert receipt.created == [
        "raw/sources/evidence.md",
        "raw/sources/evidence.pdf",
    ]
    assert "evidence.pdf" not in (root / "raw/sources/index.md").read_text(
        encoding="utf-8"
    )


def test_late_document_occupant_is_preserved_and_preparation_is_consumed(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    target = root / "synthetic/planned.md"
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    target.write_bytes(b"late occupant")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.role == "document"
    assert target.read_bytes() == b"late occupant"
    with pytest.raises(ValueError, match="already consumed"):
        apply_write(prepared)


def test_stale_mutation_identity_preserves_late_replacement(tmp_path) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    old.write_bytes(document_bytes("KB-000002", "Old", "Old."))
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            mutations=[
                MutationTarget(key="superseded", path=Path("synthetic/old.md"))
            ],
            log_entry=log_entry(),
        ),
    )
    old.rename(root / "synthetic/original-old.md")
    old.write_bytes(b"late replacement")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared, {"superseded": b"superseded"})

    assert raised.value.operation == "overwrite"
    assert raised.value.role == "mutation"
    assert old.read_bytes() == b"late replacement"


def test_late_mutation_parent_symlink_is_not_followed(tmp_path) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    original = document_bytes("KB-000002", "Old", "Old.")
    old.write_bytes(original)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("raw/sources/evidence.md"),
                content=(
                    b"---\nid: RAW-000001\ntype: raw-source\n"
                    b"title: Evidence\n---\nStub\n"
                ),
            ),
            mutations=[
                MutationTarget(key="superseded", path=Path("synthetic/old.md"))
            ],
            log_entry=log_entry(),
        ),
    )
    moved = root / "synthetic-moved"
    (root / "synthetic").rename(moved)
    try:
        (root / "synthetic").symlink_to(moved, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared, {"superseded": b"superseded"})

    assert raised.value.operation == "overwrite"
    assert raised.value.role == "mutation"
    assert (moved / "old.md").read_bytes() == original


def test_stale_index_identity_is_not_overwritten_or_logged(tmp_path) -> None:
    root = initialized(tmp_path)
    index = root / "synthetic/index.md"
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    log_before = (root / "log.md").read_bytes()
    index.rename(root / "synthetic/original-index.md")
    index.write_bytes(b"late index")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.operation == "overwrite"
    assert raised.value.role == "index"
    assert index.read_bytes() == b"late index"
    assert (root / "log.md").read_bytes() == log_before


def test_stale_log_identity_is_not_appended(tmp_path) -> None:
    root = initialized(tmp_path)
    log = root / "log.md"
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    log.rename(root / "original-log.md")
    log.write_bytes(b"late log")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.operation == "append"
    assert raised.value.role == "log"
    assert log.read_bytes() == b"late log"


def test_missing_log_is_recreated_with_only_the_new_entry(tmp_path) -> None:
    root = initialized(tmp_path)
    (root / "log.md").unlink()
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )

    apply_write(prepared)

    log = (root / "log.md").read_text(encoding="utf-8")
    assert "| initialized |" not in log
    assert log.count("| created | test | KB-000001 |") == 1


def test_replacement_keys_are_exact_and_checked_before_consumption(tmp_path) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    old.write_bytes(document_bytes("KB-000002", "Old", "Old."))
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            mutations=[
                MutationTarget(key="superseded", path=Path("synthetic/old.md"))
            ],
            log_entry=log_entry(),
        ),
    )

    with pytest.raises(ValueError, match="exactly match"):
        apply_write(prepared)
    receipt = apply_write(prepared, {"superseded": b"superseded"})

    assert receipt.updated == ["synthetic/index.md", "synthetic/old.md"]


def test_prepare_rejects_symlink_birth_without_touching_target(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"outside")
    target = root / "synthetic/planned.md"
    try:
        target.symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    with pytest.raises(ValueError, match="symlink or junction"):
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"), content=document_bytes()
                ),
                log_entry=log_entry(),
            ),
        )

    assert outside.read_bytes() == b"outside"


def test_document_failure_leaves_companion_but_not_index_or_log(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    index_before = (root / "raw/sources/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
    real_create = pipeline.create_file_bytes
    document = root / "raw/sources/evidence.md"

    def fail_document(path: Path, content: bytes) -> None:
        if path == document:
            raise OSError("document failure")
        real_create(path, content)

    monkeypatch.setattr(pipeline, "create_file_bytes", fail_document)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("raw/sources/evidence.md"),
                content=(
                    b"---\nid: RAW-000001\ntype: raw-source\n"
                    b"title: Evidence\n---\nStub\n"
                ),
                companions_before=[
                    CompanionBirth(
                        path=Path("raw/sources/evidence.pdf"), content=b"%PDF"
                    )
                ],
            ),
            log_entry=LogEntry(
                at="2026-07-20T12:00:00Z",
                action="ingested",
                actor="test",
                doc_ids=["RAW-000001"],
                note="raw/sources/evidence.md",
            ),
        ),
    )

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.role == "document"
    assert (root / "raw/sources/evidence.pdf").read_bytes() == b"%PDF"
    assert not document.exists()
    assert (root / "raw/sources/index.md").read_bytes() == index_before
    assert (root / "log.md").read_bytes() == log_before


def test_late_born_index_occupant_is_preserved(tmp_path, monkeypatch) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    born_index = root / "synthetic/a/index.md"
    real_create = pipeline.create_file_bytes

    def occupy_index(path: Path, content: bytes) -> None:
        if path == born_index:
            real_create(path, b"late index")
        real_create(path, content)

    monkeypatch.setattr(pipeline, "create_file_bytes", occupy_index)
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.operation == "create"
    assert raised.value.role == "index"
    assert born_index.read_bytes() == b"late index"
