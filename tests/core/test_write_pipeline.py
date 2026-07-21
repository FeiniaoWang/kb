from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from kb.core.housekeeping import LogEntry, init_kb
from kb.core.model import ConfigLoadError
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


def test_prepare_does_not_follow_root_replacement_link(tmp_path) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    moved = tmp_path / "kb-moved"
    root.rename(moved)
    try:
        root.symlink_to(moved, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "directory"
    assert raised.value.path == Path(".")
    assert not (moved / "synthetic/planned.md").exists()


def test_prepare_rejects_real_root_replacement_bound_to_loaded_context(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    original = tmp_path / "kb-original"
    root.rename(original)
    replacement = initialized(tmp_path)

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "directory"
    assert raised.value.path == Path(".")
    assert not (original / "synthetic/planned.md").exists()
    assert not (replacement / "synthetic/planned.md").exists()


def test_load_context_anchors_config_and_scan_during_swap_away_and_back(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    (root / "kb-config.json").write_text(
        '{"schema": 1, "types": ["original-type"]}',
        encoding="utf-8",
    )
    (root / "synthetic/original.md").write_bytes(
        document_bytes("KB-000007", "Original", "Original metadata.")
    )
    replacement = tmp_path / "replacement"
    assert init_kb(replacement).root == replacement.resolve()
    (replacement / "kb-config.json").write_text(
        '{"schema": 1, "types": ["replacement-type"]}',
        encoding="utf-8",
    )
    (replacement / "synthetic/replacement.md").write_bytes(
        document_bytes("KB-999999", "Replacement", "Outside metadata.")
    )
    moved = tmp_path / "root-during-snapshot"
    real_open = safeio.os.open
    swapped = False

    def swap_for_config_read(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "kb-config.json" and dir_fd is not None and not swapped:
            swapped = True
            root.rename(moved)
            replacement.rename(root)
            try:
                return real_open(path, flags, mode, dir_fd=dir_fd)
            finally:
                root.rename(replacement)
                moved.rename(root)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", swap_for_config_read)

    context = load_write_context(root)

    assert swapped
    assert context.config.types == ["original-type"]
    assert "KB-000007" in context.kb.by_id
    assert context.kb.by_id["KB-000007"].frontmatter.root["title"] == "Original"
    assert "KB-999999" not in context.kb.by_id


def test_load_context_closes_root_descriptor_when_snapshot_read_fails(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    real_open = safeio.os.open
    root_descriptor: int | None = None

    def fail_config_read(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal root_descriptor
        if path == "kb-config.json" and dir_fd is not None:
            root_descriptor = dir_fd
            raise OSError(errno.EIO, "snapshot read failure")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", fail_config_read)

    with pytest.raises(ConfigLoadError) as raised:
        load_write_context(root)

    assert raised.value.code == "E_CONFIG_INVALID"
    assert root_descriptor is not None
    with pytest.raises(OSError):
        os.fstat(root_descriptor)


def test_load_context_fails_safely_when_rooted_reads_are_unsupported(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    monkeypatch.setattr(safeio, "_ROOTED_SUPPORTED", False)

    with pytest.raises(WriteFailure) as raised:
        load_write_context(root)

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "directory"
    assert raised.value.cause.errno == errno.ENOTSUP
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(errno.ENOENT, "config disappeared"),
        PermissionError(errno.EACCES, "config unreadable"),
    ],
)
def test_load_context_preserves_config_error_for_final_config_access_failure(
    tmp_path,
    monkeypatch,
    error,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    real_read = safeio._RootedReader.read_file

    def fail_config_read(reader, relative, **kwargs):
        if relative == Path("kb-config.json"):
            raise error
        return real_read(reader, relative, **kwargs)

    monkeypatch.setattr(safeio._RootedReader, "read_file", fail_config_read)

    with pytest.raises(ConfigLoadError) as raised:
        load_write_context(root)

    assert raised.value.code == "E_CONFIG_INVALID"
    assert raised.value.message.startswith("invalid kb-config.json:")


def test_load_context_snapshot_does_not_resolve_root_after_acquisition(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    (root / "synthetic/original.md").write_bytes(
        document_bytes("KB-000007", "Original", "Original metadata.")
    )
    replacement = tmp_path / "replacement-during-scan"
    assert init_kb(replacement).root == replacement.resolve()
    moved = tmp_path / "root-during-scan-build"
    real_scan_snapshot = pipeline.scan_snapshot
    swapped = False

    def build_while_root_path_is_a_symlink(captured_root, files):
        nonlocal swapped
        swapped = True
        root.rename(moved)
        try:
            root.symlink_to(replacement, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            moved.rename(root)
            pytest.skip(f"symlinks unsupported: {error}")
        try:
            return real_scan_snapshot(captured_root, files)
        finally:
            root.unlink()
            moved.rename(root)

    monkeypatch.setattr(pipeline, "scan_snapshot", build_while_root_path_is_a_symlink)

    context = load_write_context(root)

    assert swapped
    assert context.kb.root == context.root
    assert all(
        document._source_path == context.root / document.path
        for document in context.kb.documents
    )


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


def test_prepare_classifies_final_mutation_symlink_as_inspect_failure(tmp_path) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    outside = tmp_path / "outside.md"
    outside.write_bytes(document_bytes("KB-000002", "Old", "Old."))
    target = root / "synthetic/old.md"
    try:
        target.symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"),
                    content=document_bytes(),
                ),
                mutations=[
                    MutationTarget(
                        key="superseded",
                        path=Path("synthetic/old.md"),
                    )
                ],
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "mutation"
    assert raised.value.path == Path("synthetic/old.md")
    assert raised.value.key == "superseded"
    assert outside.read_bytes() == document_bytes("KB-000002", "Old", "Old.")
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


def test_prepare_classifies_directory_at_birth_path_as_inspect_failure(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    target = root / "synthetic/planned.md"
    target.mkdir()
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"), content=document_bytes()
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "document"
    assert raised.value.path == Path("synthetic/planned.md")
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_prepare_rejects_birth_at_would_be_born_index_before_writes(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(ValueError, match="implicit pipeline path"):
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/a/index.md"),
                    content=document_bytes(),
                ),
                log_entry=log_entry(),
            ),
        )

    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize(
    "reserved",
    [Path("synthetic/index.md"), Path("log.md")],
)
def test_prepare_rejects_mutation_at_implicit_pipeline_path_before_writes(
    tmp_path,
    reserved,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(ValueError, match="implicit pipeline path"):
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"),
                    content=document_bytes(),
                ),
                mutations=[MutationTarget(key="reserved", path=reserved)],
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
    real_create = pipeline.create_rooted_file_bytes

    def record(
        rooted_at: Path,
        relative: Path,
        content: bytes,
        root_identity,
    ) -> None:
        seen.append(relative.as_posix())
        real_create(rooted_at, relative, content, root_identity)

    monkeypatch.setattr(pipeline, "create_rooted_file_bytes", record)
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


def test_prepare_classifies_symlink_birth_as_inspect_failure_without_touching_target(
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

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"), content=document_bytes()
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "document"
    assert raised.value.path == Path("synthetic/planned.md")
    assert outside.read_bytes() == b"outside"


def test_prepare_classifies_symlink_birth_parent_as_directory_inspect_failure(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    external = outside / "planned.md"
    external.write_bytes(b"outside")
    parent = root / "synthetic/nested"
    try:
        parent.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/nested/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "directory"
    assert raised.value.path == Path("synthetic/nested")
    assert external.read_bytes() == b"outside"


@pytest.mark.parametrize(
    ("with_companion", "expected_role", "expected_path"),
    [
        (True, "companion", Path("raw/sources/evidence.pdf")),
        (False, "document", Path("raw/sources/evidence.md")),
    ],
)
def test_late_birth_parent_link_is_role_specific_write_failure(
    tmp_path,
    with_companion,
    expected_role,
    expected_path,
) -> None:
    root = initialized(tmp_path)
    companions = (
        [
            CompanionBirth(
                path=Path("raw/sources/evidence.pdf"),
                content=b"%PDF",
            )
        ]
        if with_companion
        else []
    )
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("raw/sources/evidence.md"),
                content=(
                    b"---\nid: RAW-000001\ntype: raw-source\n"
                    b"title: Evidence\n---\nStub\n"
                ),
                companions_before=companions,
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
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evidence.md").write_bytes(b"external document")
    (outside / "evidence.pdf").write_bytes(b"external companion")
    moved = root / "raw/sources-moved"
    (root / "raw/sources").rename(moved)
    try:
        (root / "raw/sources").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlinks unsupported: {error}")

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.operation == "create"
    assert raised.value.role == expected_role
    assert raised.value.path == expected_path
    assert (outside / "evidence.md").read_bytes() == b"external document"
    assert (outside / "evidence.pdf").read_bytes() == b"external companion"


def test_document_failure_leaves_companion_but_not_index_or_log(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    index_before = (root / "raw/sources/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
    real_create = pipeline.create_rooted_file_bytes
    document = Path("raw/sources/evidence.md")

    def fail_document(
        rooted_at: Path,
        relative: Path,
        content: bytes,
        root_identity,
    ) -> None:
        if relative == document:
            raise OSError("document failure")
        real_create(rooted_at, relative, content, root_identity)

    monkeypatch.setattr(pipeline, "create_rooted_file_bytes", fail_document)
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
    assert not (root / document).exists()
    assert (root / "raw/sources/index.md").read_bytes() == index_before
    assert (root / "log.md").read_bytes() == log_before


def test_late_born_index_occupant_is_preserved(tmp_path, monkeypatch) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    born_index = root / "synthetic/a/index.md"
    real_create = pipeline.create_rooted_file_bytes

    def occupy_index(
        rooted_at: Path,
        relative: Path,
        content: bytes,
        root_identity,
    ) -> None:
        if rooted_at / relative == born_index:
            real_create(rooted_at, relative, b"late index", root_identity)
        real_create(rooted_at, relative, content, root_identity)

    monkeypatch.setattr(pipeline, "create_rooted_file_bytes", occupy_index)
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


def test_prepare_rejects_temporary_index_directory_swap_during_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    context = load_write_context(root)
    synthetic = root / "synthetic"
    moved = root / "synthetic-during-snapshot"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_index = outside / "index.md"
    outside_document = outside / "outside.md"
    outside_index.write_text(
        "---\ntype: index\ndescription: Outside.\n---\n# Outside\n",
        encoding="utf-8",
    )
    outside_document.write_bytes(
        document_bytes("KB-888888", "Outside Secret", "Outside metadata.")
    )
    kb_before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    outside_before = {
        path: path.read_bytes() for path in outside.rglob("*") if path.is_file()
    }
    synthetic_identity = os.stat(synthetic)
    real_listdir = safeio.os.listdir
    swapped = False

    def swap_during_listing(path="."):
        nonlocal swapped
        if (
            isinstance(path, int)
            and os.fstat(path).st_dev == synthetic_identity.st_dev
            and os.fstat(path).st_ino == synthetic_identity.st_ino
            and not swapped
        ):
            swapped = True
            synthetic.rename(moved)
            synthetic.symlink_to(outside, target_is_directory=True)
        return real_listdir(path)

    monkeypatch.setattr(safeio.os, "listdir", swap_during_listing)
    try:
        with pytest.raises(WriteFailure) as raised:
            prepare_write(
                context,
                WriteIntent(
                    birth=DocumentBirth(
                        path=Path("synthetic/planned.md"),
                        content=document_bytes(),
                    ),
                    log_entry=log_entry(),
                ),
            )
    finally:
        if synthetic.is_symlink():
            synthetic.unlink()
            moved.rename(synthetic)

    assert swapped
    assert raised.value.phase == "preflight"
    assert raised.value.role in {"directory", "index"}
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == kb_before
    assert {
        path: path.read_bytes() for path in outside.rglob("*") if path.is_file()
    } == outside_before
    assert b"Outside Secret" not in (root / "synthetic/index.md").read_bytes()


def test_prepare_rejects_external_tree_swap_before_index_listing_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    context = load_write_context(root)
    synthetic = root / "synthetic"
    moved = root / "synthetic-before-listing"
    outside = tmp_path / "outside-tree"
    outside.mkdir()
    (outside / "index.md").write_text(
        "---\ntype: index\ndescription: Outside.\n---\n# Outside\n",
        encoding="utf-8",
    )
    (outside / "outside.md").write_bytes(
        document_bytes("KB-777777", "Outside Secret", "Outside metadata.")
    )
    kb_before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    outside_before = {
        path.name: path.read_bytes() for path in outside.iterdir() if path.is_file()
    }
    real_read = safeio._RootedReader.read_file
    swapped = False

    def swap_after_index_read(reader, relative, **kwargs):
        nonlocal swapped
        content = real_read(reader, relative, **kwargs)
        if relative == Path("synthetic/index.md") and not swapped:
            swapped = True
            synthetic.rename(moved)
            outside.rename(synthetic)
        return content

    monkeypatch.setattr(safeio._RootedReader, "read_file", swap_after_index_read)
    try:
        with pytest.raises(WriteFailure) as raised:
            prepare_write(
                context,
                WriteIntent(
                    birth=DocumentBirth(
                        path=Path("synthetic/planned.md"),
                        content=document_bytes(),
                    ),
                    log_entry=log_entry(),
                ),
            )
    finally:
        if synthetic.exists() and moved.exists():
            synthetic.rename(outside)
            moved.rename(synthetic)

    assert swapped
    assert raised.value.phase == "preflight"
    assert raised.value.role in {"directory", "index"}
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == kb_before
    assert {
        path.name: path.read_bytes() for path in outside.iterdir() if path.is_file()
    } == outside_before
    assert b"Outside Secret" not in (root / "synthetic/index.md").read_bytes()


def test_prepare_rejects_directory_b_installed_during_bound_index_read(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    context = load_write_context(root)
    synthetic = root / "synthetic"
    moved = root / "synthetic-during-index-read"
    replacement = tmp_path / "replacement-synthetic"
    replacement.mkdir()
    (replacement / "index.md").write_text(
        "---\ntype: index\ndescription: Replacement.\n---\n# Replacement\n",
        encoding="utf-8",
    )
    (replacement / "outside.md").write_bytes(
        document_bytes("KB-666666", "Outside Secret", "Outside metadata.")
    )
    kb_before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    replacement_before = {
        path.name: path.read_bytes() for path in replacement.iterdir() if path.is_file()
    }
    real_read = safeio._RootedReader.read_file
    swapped = False

    def swap_before_bound_index_read(reader, relative, **kwargs):
        nonlocal swapped
        if relative == Path("synthetic/index.md") and not swapped:
            swapped = True
            synthetic.rename(moved)
            replacement.rename(synthetic)
            try:
                return real_read(reader, relative, **kwargs)
            finally:
                synthetic.rename(replacement)
                moved.rename(synthetic)
        return real_read(reader, relative, **kwargs)

    monkeypatch.setattr(
        safeio._RootedReader,
        "read_file",
        swap_before_bound_index_read,
    )
    try:
        with pytest.raises(WriteFailure) as raised:
            prepare_write(
                context,
                WriteIntent(
                    birth=DocumentBirth(
                        path=Path("synthetic/planned.md"),
                        content=document_bytes(),
                    ),
                    log_entry=log_entry(),
                ),
            )
    finally:
        if synthetic.exists() and moved.exists():
            synthetic.rename(replacement)
            moved.rename(synthetic)

    assert swapped
    assert raised.value.phase == "preflight"
    assert raised.value.role in {"directory", "index"}
    assert not (root / "synthetic/planned.md").exists()
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == kb_before
    assert {
        path.name: path.read_bytes() for path in replacement.iterdir() if path.is_file()
    } == replacement_before


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires FIFO support")
def test_prepare_rejects_non_regular_non_markdown_listing_child(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)
    fifo = root / "synthetic/pipe"
    os.mkfifo(fifo)

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            context,
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.role == "index"
    assert not (root / "synthetic/planned.md").exists()


def test_prepare_index_rendering_performs_no_path_based_listing_reads(
    tmp_path,
    monkeypatch,
) -> None:
    root = initialized(tmp_path)
    (root / "synthetic/existing.md").write_bytes(
        document_bytes("KB-000009", "Existing", "Existing metadata.")
    )
    context = load_write_context(root)

    def forbidden(*args, **kwargs):
        raise AssertionError("pipeline index rendering used a path-based read")

    monkeypatch.setattr(Path, "iterdir", forbidden)
    monkeypatch.setattr(Path, "glob", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)

    prepared = prepare_write(
        context,
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )

    assert prepared.sources == {}
