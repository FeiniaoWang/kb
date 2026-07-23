from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from kb.core.housekeeping import LogEntry, empty_log_content, init_kb
from kb.core.model import ConfigLoadError
from kb.core.write_pipeline import (
    AllocationBlocked,
    CompanionBirth,
    DocumentBirth,
    MutationIntent,
    MutationTarget,
    WriteFailure,
    WriteIntent,
    apply_mutation_write,
    apply_write,
    load_write_context,
    prepare_mutation_write,
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


SYNTHETIC_DOC = document_bytes()
LOG_ENTRY = LogEntry(
    at="2026-07-22T00:00:00Z",
    action="revised",
    actor="kb-cli",
    doc_ids=["KB-000001"],
    note="synthetic/doc.md",
)


def _create_descriptor_relative_deep_tree(root: Path, depth: int) -> Path:
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root / "synthetic", directory_flags)
    parts = ["synthetic"]
    try:
        for _ in range(depth):
            os.mkdir("d", dir_fd=descriptor)
            child = os.open("d", directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            parts.append("d")
            index = os.open(
                "index.md",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o644,
                dir_fd=descriptor,
            )
            try:
                os.write(index, b"---\ntype: index\n---\n# Deep\n")
            finally:
                os.close(index)
        document = os.open(
            "deep.md",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
            dir_fd=descriptor,
        )
        try:
            os.write(
                document,
                document_bytes("KB-999999", "Deep", "Deep tree document."),
            )
        finally:
            os.close(document)
    finally:
        os.close(descriptor)
    return Path(*parts, "deep.md")


def test_load_context_blocks_malformed_documents_without_writes(tmp_path) -> None:
    root = initialized(tmp_path)
    malformed = root / "synthetic/bad.md"
    malformed.write_text("not frontmatter\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(AllocationBlocked) as raised:
        load_write_context(root)

    assert raised.value.paths == (Path("synthetic/bad.md"),)
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_load_context_traverses_beyond_recursion_limit_without_root_reopen_growth(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    deep_document = _create_descriptor_relative_deep_tree(root, 1_025)
    root_to_relative_reopens = 0
    real_open_directory = safeio._RootedReader._open_directory

    def count_root_to_relative_reopen(reader, relative, expected=None):
        nonlocal root_to_relative_reopens
        root_to_relative_reopens += 1
        return real_open_directory(reader, relative, expected)

    monkeypatch.setattr(
        safeio._RootedReader,
        "_open_directory",
        count_root_to_relative_reopen,
    )

    context = load_write_context(root)

    assert context.kb.by_id["KB-999999"].path == deep_document
    assert root_to_relative_reopens <= 4


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


def test_load_context_reads_only_rooted_frontmatter_prefixes(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    path = root / "synthetic/large.md"
    prefix = b"---\nid: KB-000007\ntype: spec\ntitle: Large\n---\n"
    body = b"rooted body bytes that allocation must not read\n" * 100_000
    path.write_bytes(prefix + body)
    bytes_read: list[int] = []

    def observed_prefix(stream) -> bytes:
        assert stream.tell() == 0
        content = bytearray()
        first = stream.readline()
        content.extend(first)
        if first.rstrip(b"\r\n") == b"---":
            while True:
                line = stream.readline()
                if not line:
                    break
                content.extend(line)
                if line.rstrip(b"\r\n") == b"---":
                    break
        bytes_read.append(len(content))
        return bytes(content)

    monkeypatch.setattr(
        pipeline,
        "read_frontmatter_prefix",
        observed_prefix,
        raising=False,
    )

    context = load_write_context(root)

    assert len(prefix) in bytes_read
    assert len(prefix + body) not in bytes_read
    document = context.kb.by_id["KB-000007"]
    assert not hasattr(document, "_source_bytes")


def test_load_context_documents_keep_body_access_lazy(tmp_path) -> None:
    root = initialized(tmp_path)
    path = root / "synthetic/lazy.md"
    path.write_bytes(document_bytes("KB-000007", "Lazy", "Lazy.") + b"one\n")

    context = load_write_context(root)
    path.write_bytes(document_bytes("KB-000007", "Lazy", "Lazy.") + b"two\n")

    assert context.kb.by_id["KB-000007"].body == "Body\ntwo\n"


def test_load_context_failure_keeps_exact_path_and_partial_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    target = root / "synthetic/a-target.md"
    target.write_bytes(document_bytes("KB-000007", "Target", "Target."))
    failing = root / "synthetic/z-failing.md"
    failing.write_bytes(document_bytes("KB-000008", "Failing", "Failing."))
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"outside")
    real_open = safeio.os.open
    injected = False

    def replace_later_file(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected
        if path == "z-failing.md" and dir_fd is not None and not injected:
            injected = True
            os.rename(
                "z-failing.md",
                "z-original.md",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.symlink(outside, "z-failing.md", dir_fd=dir_fd)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safeio.os, "open", replace_later_file)

    with pytest.raises(WriteFailure) as raised:
        load_write_context(root)

    assert injected
    assert raised.value.path == Path("synthetic/z-failing.md")
    assert raised.value.snapshot_kb is not None
    assert raised.value.snapshot_kb.by_id["KB-000007"].path == Path(
        "synthetic/a-target.md"
    )


def test_load_context_unclosed_frontmatter_reads_to_eof_deterministically(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    content = b"---\nid: KB-000007\ntype: spec\n" + (b"not closed\n" * 500)
    (root / "synthetic/unclosed.md").write_bytes(content)
    bytes_read: list[int] = []

    def observed_prefix(stream) -> bytes:
        acquired = stream.read()
        bytes_read.append(len(acquired))
        return acquired

    monkeypatch.setattr(
        pipeline,
        "read_frontmatter_prefix",
        observed_prefix,
        raising=False,
    )

    with pytest.raises(AllocationBlocked) as raised:
        load_write_context(root)

    assert raised.value.paths == (Path("synthetic/unclosed.md"),)
    assert len(content) in bytes_read


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


def test_prepare_acquires_full_supersession_bytes_after_lazy_context(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    old = root / "synthetic/old.md"
    original = (
        b"---\r\nid: KB-000002\r\ntype: spec\r\ntitle: Old\r\n"
        b"description: Old.\r\ncustom: preserved\r\n---\r\n"
        + (b"lossless body\x00bytes\r\n" * 20_000)
    )
    old.write_bytes(original)
    context = load_write_context(root)

    prepared = prepare_write(
        context,
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"),
                content=document_bytes(),
            ),
            mutations=[
                MutationTarget(key="superseded", path=Path("synthetic/old.md"))
            ],
            log_entry=log_entry(),
        ),
    )

    assert prepared.sources["superseded"].content == original


def test_prepare_projected_index_decodes_only_large_child_frontmatter_prefix(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    prefix = (
        b"---\nid: KB-000007\ntype: spec\ntitle: Prefix Only\n"
        b"description: Metadata stays small.\n---\n"
    )
    (root / "synthetic/large.md").write_bytes(
        prefix + b"\xff" * (4 * 1024 * 1024)
    )

    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )

    assert b"[KB-000007][Prefix Only](large.md)" in prepared._refresh_content


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


def test_prepare_owns_exact_log_bytes_and_apply_does_not_render_again(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    log = root / "log.md"
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    expected = (
        b"- 2026-07-20T12:00:00Z | created | test | KB-000001 | "
        b"synthetic/planned.md\n"
    )

    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )

    assert prepared._log_row == expected
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before

    def forbidden_render(_entry: LogEntry) -> str:
        raise AssertionError("apply_write must consume prepared log bytes")

    monkeypatch.setattr(pipeline, "format_log_entry", forbidden_render)
    apply_write(prepared)

    assert log.read_bytes() == before[log] + expected


def test_prepare_wraps_unencodable_log_row_as_typed_preflight_failure(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    entry = log_entry()
    entry.actor = "actor-\udcff"

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            load_write_context(root),
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=entry,
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "render"
    assert raised.value.role == "log"
    assert raised.value.path == Path("log.md")
    assert type(raised.value.cause) is OSError
    assert raised.value.cause.errno == errno.EILSEQ
    assert "UTF-8" in str(raised.value.cause)
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_prepare_wraps_log_formatting_failure_as_typed_preflight_failure(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    entry = log_entry()
    entry.doc_ids = [None]  # type: ignore[list-item]

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            load_write_context(root),
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=entry,
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "render"
    assert raised.value.role == "log"
    assert raised.value.path == Path("log.md")
    assert type(raised.value.cause) is OSError
    assert raised.value.cause.errno == errno.EINVAL
    assert "formatted" in str(raised.value.cause)
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_prepare_wraps_unencodable_born_index_as_typed_preflight_failure(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    born_index = Path("synthetic/bad-\udcff/index.md")

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            load_write_context(root),
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/bad-\udcff/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "render"
    assert raised.value.role == "index"
    assert raised.value.path == born_index
    assert type(raised.value.cause) is OSError
    assert raised.value.cause.errno == errno.EILSEQ
    assert "UTF-8" in str(raised.value.cause)
    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_prepare_wraps_born_index_formatting_failure_as_typed_preflight_failure(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def fail_born_index(*_args, **_kwargs):
        raise ValueError("born index formatting failed")

    monkeypatch.setattr(pipeline, "render_index", fail_born_index)

    with pytest.raises(WriteFailure) as raised:
        prepare_write(
            load_write_context(root),
            WriteIntent(
                birth=DocumentBirth(
                    path=Path("synthetic/new/planned.md"),
                    content=document_bytes(),
                ),
                log_entry=log_entry(),
            ),
        )

    assert raised.value.phase == "preflight"
    assert raised.value.operation == "render"
    assert raised.value.role == "index"
    assert raised.value.path == Path("synthetic/new/index.md")
    assert type(raised.value.cause) is OSError
    assert raised.value.cause.errno == errno.EINVAL
    assert "formatted" in str(raised.value.cause)
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
        *,
        parent_expected=None,
    ) -> None:
        seen.append(relative.as_posix())
        real_create(
            rooted_at,
            relative,
            content,
            root_identity,
            parent_expected=parent_expected,
        )

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


@pytest.mark.parametrize(
    ("log_exists", "cleanup_target"),
    [
        (False, "file"),
        (True, "file"),
        (False, "parent"),
        (True, "parent"),
    ],
)
def test_completed_final_log_write_ignores_descriptor_cleanup_failure(
    tmp_path,
    monkeypatch,
    log_exists,
    cleanup_target,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    log = root / "log.md"
    if not log_exists:
        log.unlink()
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    log_before = log.read_bytes() if log_exists else empty_log_content().encode("utf-8")
    expected_log = log_before + prepared._log_row
    real_open = safeio.os.open
    real_write = safeio.os.write
    real_close = safeio.os.close
    parent_descriptor = None
    log_descriptor = None
    log_write_completed = False
    cleanup_failed = False

    def track_log_descriptors(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal parent_descriptor, log_descriptor
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == root and dir_fd is None:
            parent_descriptor = descriptor
        is_log_create = path == "log.md" and bool(flags & os.O_CREAT)
        is_log_append = path == "log.md" and bool(flags & os.O_APPEND)
        if is_log_create or is_log_append:
            log_descriptor = descriptor
        return descriptor

    def track_completed_log_write(descriptor, content):
        nonlocal log_write_completed
        written = real_write(descriptor, content)
        if descriptor == log_descriptor:
            log_write_completed = True
        return written

    def fail_selected_cleanup(descriptor):
        nonlocal cleanup_failed
        fail_file = cleanup_target == "file" and descriptor == log_descriptor
        fail_parent = (
            cleanup_target == "parent"
            and log_write_completed
            and descriptor == parent_descriptor
        )
        real_close(descriptor)
        if not cleanup_failed and (fail_file or fail_parent):
            cleanup_failed = True
            raise OSError(errno.EIO, "injected post-log cleanup failure")

    monkeypatch.setattr(safeio.os, "open", track_log_descriptors)
    monkeypatch.setattr(safeio.os, "write", track_completed_log_write)
    monkeypatch.setattr(safeio.os, "close", fail_selected_cleanup)

    receipt = apply_write(prepared)

    assert cleanup_failed
    assert receipt.created == ["synthetic/planned.md"]
    assert receipt.updated == ["synthetic/index.md"]
    assert log.read_bytes() == expected_log


def test_pre_log_open_failure_is_not_hidden_by_parent_cleanup(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    log = root / "log.md"
    log_before = log.read_bytes()
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    real_open = safeio.os.open
    real_close = safeio.os.close
    parent_descriptor = None
    log_open_attempted = False

    def fail_log_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal parent_descriptor, log_open_attempted
        if path == "log.md" and bool(flags & os.O_APPEND):
            log_open_attempted = True
            raise PermissionError(errno.EACCES, "injected log open failure", path)
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == root and dir_fd is None:
            parent_descriptor = descriptor
        return descriptor

    def fail_parent_cleanup(descriptor):
        should_fail = log_open_attempted and descriptor == parent_descriptor
        real_close(descriptor)
        if should_fail:
            raise OSError(errno.EIO, "injected parent cleanup failure")

    monkeypatch.setattr(safeio.os, "open", fail_log_open)
    monkeypatch.setattr(safeio.os, "close", fail_parent_cleanup)

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert log_open_attempted
    assert raised.value.operation == "append"
    assert raised.value.role == "log"
    assert raised.value.cause.errno == errno.EACCES
    assert log.read_bytes() == log_before


def test_log_write_failure_is_not_hidden_or_ignored_by_descriptor_cleanup(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    log = root / "log.md"
    log_before = log.read_bytes()
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/planned.md"), content=document_bytes()
            ),
            log_entry=log_entry(),
        ),
    )
    real_open = safeio.os.open
    real_write = safeio.os.write
    real_close = safeio.os.close
    log_descriptor = None
    cleanup_failed = False

    def track_log_descriptor(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal log_descriptor
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == "log.md" and bool(flags & os.O_APPEND):
            log_descriptor = descriptor
        return descriptor

    def fail_log_write(descriptor, content):
        if descriptor == log_descriptor:
            raise OSError(errno.ENOSPC, "injected log write failure")
        return real_write(descriptor, content)

    def fail_log_cleanup(descriptor):
        nonlocal cleanup_failed
        is_log = descriptor == log_descriptor
        real_close(descriptor)
        if is_log:
            cleanup_failed = True
            raise OSError(errno.EIO, "injected log cleanup failure")

    monkeypatch.setattr(safeio.os, "open", track_log_descriptor)
    monkeypatch.setattr(safeio.os, "write", fail_log_write)
    monkeypatch.setattr(safeio.os, "close", fail_log_cleanup)

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert cleanup_failed
    assert raised.value.operation == "append"
    assert raised.value.role == "log"
    assert raised.value.cause.errno == errno.ENOSPC
    assert log.read_bytes() == log_before


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


def test_existing_target_replacement_fails_before_first_companion_birth(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    target = root / "raw/sources"
    original = root / "raw/sources-original"
    original_index = (target / "index.md").read_bytes()
    class_index_before = (root / "raw/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
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
    replacement_index = b"replacement index\n"
    target.rename(original)
    target.mkdir()
    (target / "index.md").write_bytes(replacement_index)

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.operation == "create"
    assert raised.value.role == "companion"
    assert raised.value.path == Path("raw/sources/evidence.pdf")
    assert sorted(path.name for path in target.iterdir()) == ["index.md"]
    assert (target / "index.md").read_bytes() == replacement_index
    assert sorted(path.name for path in original.iterdir()) == ["index.md"]
    assert (original / "index.md").read_bytes() == original_index
    assert (root / "raw/index.md").read_bytes() == class_index_before
    assert (root / "log.md").read_bytes() == log_before


def test_nearest_existing_ancestor_replacement_blocks_first_missing_directory(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    target = root / "synthetic/parent"
    original = root / "synthetic/parent-original"
    target.mkdir()
    target_index = (
        b"---\ntype: index\ndescription: Parent.\n---\n"
        b"# Parent\n\n## Files\n"
    )
    (target / "index.md").write_bytes(target_index)
    synthetic_index_before = (root / "synthetic/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/parent/a/b/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )
    replacement_index = b"replacement index\n"
    target.rename(original)
    target.mkdir()
    (target / "index.md").write_bytes(replacement_index)

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.operation == "mkdir"
    assert raised.value.role == "directory"
    assert raised.value.path == Path("synthetic/parent/a")
    assert sorted(path.name for path in target.iterdir()) == ["index.md"]
    assert (target / "index.md").read_bytes() == replacement_index
    assert sorted(path.name for path in original.iterdir()) == ["index.md"]
    assert (original / "index.md").read_bytes() == target_index
    assert (root / "synthetic/index.md").read_bytes() == synthetic_index_before
    assert (root / "log.md").read_bytes() == log_before


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
        *,
        parent_expected=None,
    ) -> None:
        if relative == document:
            raise OSError("document failure")
        real_create(
            rooted_at,
            relative,
            content,
            root_identity,
            parent_expected=parent_expected,
        )

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
        *,
        parent_expected=None,
    ) -> None:
        if rooted_at / relative == born_index:
            real_create(
                rooted_at,
                relative,
                b"late index",
                root_identity,
                parent_expected=parent_expected,
            )
        real_create(
            rooted_at,
            relative,
            content,
            root_identity,
            parent_expected=parent_expected,
        )

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


def test_replaced_just_born_directory_receives_no_index_or_document_bytes(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    born = root / "synthetic/a"
    original = root / "synthetic/a-original"
    real_create_directory = pipeline.create_rooted_directory

    def replace_after_mkdir(*args, **kwargs):
        identity = real_create_directory(*args, **kwargs)
        relative = args[1]
        if relative == Path("synthetic/a"):
            born.rename(original)
            born.mkdir()
        return identity

    monkeypatch.setattr(
        pipeline,
        "create_rooted_directory",
        replace_after_mkdir,
    )
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.operation == "create"
    assert raised.value.role == "index"
    assert raised.value.path == Path("synthetic/a/index.md")
    assert list(born.iterdir()) == []
    assert original.is_dir()


def test_directory_replacement_at_first_open_is_bound_for_pipeline_writes(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    parent = root / "synthetic"
    parent_status = parent.stat()
    born = parent / "a"
    real_open = safeio.os.open
    injected = False
    retained_name: str | None = None

    def install_replacement_before_identity_binding(
        path,
        flags,
        mode=0o777,
        *,
        dir_fd=None,
    ):
        nonlocal injected, retained_name
        is_parent = (
            dir_fd is not None
            and os.fstat(dir_fd).st_dev == parent_status.st_dev
            and os.fstat(dir_fd).st_ino == parent_status.st_ino
        )
        is_staging = isinstance(path, str) and path.startswith(".kb-born-")
        if not injected and is_parent and is_staging:
            injected = True
            retained_name = f"{path}-created"
            os.rename(
                path,
                retained_name,
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.mkdir(path, dir_fd=dir_fd)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )
    monkeypatch.setattr(
        safeio.os,
        "open",
        install_replacement_before_identity_binding,
    )

    receipt = apply_write(prepared)

    assert injected
    assert receipt.created == ["synthetic/a/index.md", "synthetic/a/planned.md"]
    assert (born / "index.md").is_file()
    assert (born / "planned.md").read_bytes() == document_bytes()
    assert retained_name is not None
    retained = parent / retained_name
    assert retained.is_dir()
    assert not any(retained.iterdir())


def test_nonempty_replacement_at_first_open_fails_pipeline_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    index_before = (root / "synthetic/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
    real_open = safeio.os.open
    injected = False
    replacement_name: str | None = None

    def install_nonempty_replacement(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected, replacement_name
        is_staging = isinstance(path, str) and path.startswith(".kb-born-")
        if is_staging and not injected:
            injected = True
            replacement_name = path
            os.rename(
                path,
                f"{path}-created",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.mkdir(path, dir_fd=dir_fd)
            replacement_descriptor = real_open(
                path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=dir_fd,
            )
            try:
                os.mkdir("nested", dir_fd=replacement_descriptor)
                rogue_descriptor = real_open(
                    "rogue.md",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o666,
                    dir_fd=replacement_descriptor,
                )
                try:
                    os.write(rogue_descriptor, b"rogue markdown\n")
                finally:
                    os.close(rogue_descriptor)
            finally:
                os.close(replacement_descriptor)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )
    monkeypatch.setattr(safeio.os, "open", install_nonempty_replacement)

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert injected
    assert raised.value.phase == "write"
    assert raised.value.operation == "mkdir"
    assert raised.value.role == "directory"
    assert raised.value.path == Path("synthetic/a")
    assert raised.value.cause.errno == errno.ENOTEMPTY
    assert not (root / "synthetic/a").exists()
    assert not (root / "synthetic/a/index.md").exists()
    assert not (root / "synthetic/a/planned.md").exists()
    assert (root / "synthetic/index.md").read_bytes() == index_before
    assert (root / "log.md").read_bytes() == log_before
    assert replacement_name is not None
    retained = root / "synthetic" / replacement_name
    assert retained.joinpath("rogue.md").read_bytes() == b"rogue markdown\n"
    assert retained.joinpath("nested").is_dir()


def test_post_open_parent_rename_is_typed_with_partial_bytes_on_bound_object(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    born = root / "synthetic/a"
    outside = tmp_path / "outside"
    moved = outside / "moved-a"
    outside.mkdir()
    index_before = (root / "synthetic/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
    real_open = safeio.os.open
    injected = False

    def move_open_parent_before_child_create(
        path,
        flags,
        mode=0o777,
        *,
        dir_fd=None,
    ):
        nonlocal injected
        is_child_create = path == "index.md" and bool(flags & os.O_CREAT)
        if is_child_create and not injected and dir_fd is not None:
            parent_status = os.fstat(dir_fd)
            born_status = born.stat()
            is_bound_born = (
                parent_status.st_dev == born_status.st_dev
                and parent_status.st_ino == born_status.st_ino
            )
            if is_bound_born:
                injected = True
                born.rename(moved)
                born.mkdir()
        return real_open(path, flags, mode, dir_fd=dir_fd)

    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )
    monkeypatch.setattr(
        safeio.os,
        "open",
        move_open_parent_before_child_create,
    )

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert injected
    assert raised.value.phase == "write"
    assert raised.value.operation == "create"
    assert raised.value.role == "document"
    assert raised.value.path == Path("synthetic/a/planned.md")
    assert "identity changed" in str(raised.value.cause)
    assert list(born.iterdir()) == []
    assert not (born / "index.md").exists()
    assert not (born / "planned.md").exists()
    assert moved.is_dir()
    assert (moved / "index.md").is_file()
    assert b"(planned.md)" in (moved / "index.md").read_bytes()
    assert not (moved / "planned.md").exists()
    assert (root / "synthetic/index.md").read_bytes() == index_before
    assert (root / "log.md").read_bytes() == log_before


def test_prebinding_staging_symlink_cannot_redirect_pipeline_writes(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.safeio as safeio

    root = initialized(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker"
    marker.write_bytes(b"outside")
    index_before = (root / "synthetic/index.md").read_bytes()
    log_before = (root / "log.md").read_bytes()
    real_mkdir = safeio.os.mkdir

    def replace_staging_with_outside_symlink(path, mode=0o777, *, dir_fd=None):
        real_mkdir(path, mode, dir_fd=dir_fd)
        if isinstance(path, str) and path.startswith(".kb-born-"):
            os.rename(
                path,
                f"{path}-created",
                src_dir_fd=dir_fd,
                dst_dir_fd=dir_fd,
            )
            os.symlink(
                outside,
                path,
                target_is_directory=True,
                dir_fd=dir_fd,
            )

    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )
    monkeypatch.setattr(safeio.os, "mkdir", replace_staging_with_outside_symlink)

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.operation == "mkdir"
    assert raised.value.role == "directory"
    assert raised.value.path == Path("synthetic/a")
    assert not (root / "synthetic/a").exists()
    assert sorted(path.name for path in outside.iterdir()) == ["marker"]
    assert marker.read_bytes() == b"outside"
    assert (root / "synthetic/index.md").read_bytes() == index_before
    assert (root / "log.md").read_bytes() == log_before


def test_nested_child_birth_requires_captured_born_parent_identity(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    parent = root / "synthetic/a"
    original = root / "synthetic/a-original"
    real_create_file = pipeline.create_rooted_file_bytes

    def replace_after_parent_index(*args, **kwargs):
        result = real_create_file(*args, **kwargs)
        relative = args[1]
        if relative == Path("synthetic/a/index.md"):
            parent.rename(original)
            parent.mkdir()
        return result

    monkeypatch.setattr(
        pipeline,
        "create_rooted_file_bytes",
        replace_after_parent_index,
    )
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

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.operation == "mkdir"
    assert raised.value.role == "directory"
    assert raised.value.path == Path("synthetic/a/b")
    assert list(parent.iterdir()) == []
    assert (original / "index.md").is_file()


def test_final_verification_rejects_replaced_born_directory(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    born = root / "synthetic/a"
    original = root / "synthetic/a-original"
    log_before = (root / "log.md").read_bytes()
    real_create_file = pipeline.create_rooted_file_bytes

    def replace_after_document(*args, **kwargs):
        result = real_create_file(*args, **kwargs)
        relative = args[1]
        if relative == Path("synthetic/a/planned.md"):
            born.rename(original)
            born.mkdir()
        return result

    monkeypatch.setattr(
        pipeline,
        "create_rooted_file_bytes",
        replace_after_document,
    )
    prepared = prepare_write(
        load_write_context(root),
        WriteIntent(
            birth=DocumentBirth(
                path=Path("synthetic/a/planned.md"),
                content=document_bytes(),
            ),
            log_entry=log_entry(),
        ),
    )

    with pytest.raises(WriteFailure) as raised:
        apply_write(prepared)

    assert raised.value.phase == "write"
    assert raised.value.operation == "inspect"
    assert raised.value.role == "directory"
    assert raised.value.path == Path("synthetic/a")
    assert list(born.iterdir()) == []
    assert (original / "index.md").is_file()
    assert (original / "planned.md").is_file()
    assert (root / "log.md").read_bytes() == log_before


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


def test_mutation_write_overwrites_and_logs(tmp_path) -> None:
    root = initialized(tmp_path)
    (root / "synthetic/doc.md").write_bytes(SYNTHETIC_DOC)
    context = load_write_context(root)
    intent = MutationIntent(
        mutations=[
            MutationTarget(key="document", path=Path("synthetic/doc.md"))
        ],
        log_entry=LOG_ENTRY,
    )

    prepared = prepare_mutation_write(context, intent)

    assert prepared.sources["document"].content == SYNTHETIC_DOC
    receipt = apply_mutation_write(
        prepared,
        {"document": b"---\ntype: spec\n---\n"},
    )
    assert receipt.updated == ["synthetic/doc.md"]
    assert receipt.created == []
    assert (root / "synthetic/doc.md").read_bytes() == b"---\ntype: spec\n---\n"
    assert "| revised | kb-cli | KB-000001 |" in (
        root / "log.md"
    ).read_text(encoding="utf-8")


def test_mutation_write_requires_targets_and_matching_keys(tmp_path) -> None:
    root = initialized(tmp_path)
    target = root / "synthetic/doc.md"
    target.write_bytes(SYNTHETIC_DOC)
    context = load_write_context(root)

    with pytest.raises(ValueError):
        prepare_mutation_write(
            context,
            MutationIntent(mutations=[], log_entry=LOG_ENTRY),
        )

    prepared = prepare_mutation_write(
        context,
        MutationIntent(
            mutations=[
                MutationTarget(key="document", path=Path("synthetic/doc.md"))
            ],
            log_entry=LOG_ENTRY,
        ),
    )
    log_before = (root / "log.md").read_bytes()

    with pytest.raises(ValueError, match="exactly match"):
        apply_mutation_write(prepared, {})

    assert target.read_bytes() == SYNTHETIC_DOC
    assert (root / "log.md").read_bytes() == log_before
    receipt = apply_mutation_write(prepared, {"document": b"replacement"})
    assert receipt.updated == ["synthetic/doc.md"]


def test_mutation_write_missing_target_is_preflight_failure(tmp_path) -> None:
    root = initialized(tmp_path)
    context = load_write_context(root)

    with pytest.raises(WriteFailure) as excinfo:
        prepare_mutation_write(
            context,
            MutationIntent(
                mutations=[
                    MutationTarget(
                        key="document",
                        path=Path("synthetic/gone.md"),
                    )
                ],
                log_entry=LOG_ENTRY,
            ),
        )

    assert excinfo.value.phase == "preflight"
    assert excinfo.value.operation == "inspect"
    assert excinfo.value.role == "mutation"
    assert excinfo.value.key == "document"


@pytest.mark.parametrize(
    "mutations",
    [
        [
            MutationTarget(key="document", path=Path("synthetic/one.md")),
            MutationTarget(key="document", path=Path("synthetic/two.md")),
        ],
        [
            MutationTarget(key="one", path=Path("synthetic/one.md")),
            MutationTarget(key="two", path=Path("synthetic/one.md")),
        ],
    ],
)
def test_mutation_write_rejects_duplicate_keys_or_paths_before_writes(
    tmp_path,
    mutations,
) -> None:
    root = initialized(tmp_path)
    (root / "synthetic/one.md").write_bytes(SYNTHETIC_DOC)
    (root / "synthetic/two.md").write_bytes(document_bytes("KB-000002"))
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(ValueError):
        prepare_mutation_write(
            load_write_context(root),
            MutationIntent(mutations=mutations, log_entry=LOG_ENTRY),
        )

    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_mutation_write_rejects_log_collision_before_writes(tmp_path) -> None:
    root = initialized(tmp_path)
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    with pytest.raises(ValueError, match="implicit pipeline path"):
        prepare_mutation_write(
            load_write_context(root),
            MutationIntent(
                mutations=[MutationTarget(key="document", path=Path("log.md"))],
                log_entry=LOG_ENTRY,
            ),
        )

    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_mutation_write_is_single_use(tmp_path) -> None:
    root = initialized(tmp_path)
    (root / "synthetic/doc.md").write_bytes(SYNTHETIC_DOC)
    prepared = prepare_mutation_write(
        load_write_context(root),
        MutationIntent(
            mutations=[
                MutationTarget(key="document", path=Path("synthetic/doc.md"))
            ],
            log_entry=LOG_ENTRY,
        ),
    )

    apply_mutation_write(prepared, {"document": b"replacement"})

    with pytest.raises(ValueError, match="already consumed"):
        apply_mutation_write(prepared, {"document": b"replacement again"})


def test_mutation_write_deep_copy_shares_single_use_state(tmp_path) -> None:
    root = initialized(tmp_path)
    target = root / "synthetic/doc.md"
    target.write_bytes(SYNTHETIC_DOC)
    prepared = prepare_mutation_write(
        load_write_context(root),
        MutationIntent(
            mutations=[
                MutationTarget(key="document", path=Path("synthetic/doc.md"))
            ],
            log_entry=LOG_ENTRY,
        ),
    )
    copied = prepared.model_copy(deep=True)

    apply_mutation_write(prepared, {"document": b"first replacement"})
    target_after_first = target.read_bytes()
    log_after_first = (root / "log.md").read_bytes()

    with pytest.raises(ValueError, match="already consumed"):
        apply_mutation_write(copied, {"document": b"replayed replacement"})

    assert target.read_bytes() == target_after_first
    assert (root / "log.md").read_bytes() == log_after_first


def test_mutation_write_rejects_non_bytes_before_consumption_or_writes(
    tmp_path,
) -> None:
    root = initialized(tmp_path)
    target = root / "synthetic/doc.md"
    target.write_bytes(SYNTHETIC_DOC)
    prepared = prepare_mutation_write(
        load_write_context(root),
        MutationIntent(
            mutations=[
                MutationTarget(key="document", path=Path("synthetic/doc.md"))
            ],
            log_entry=LOG_ENTRY,
        ),
    )
    log_before = (root / "log.md").read_bytes()

    with pytest.raises(TypeError, match="bytes"):
        apply_mutation_write(
            prepared,
            {"document": "not bytes"},  # type: ignore[dict-item]
        )

    assert target.read_bytes() == SYNTHETIC_DOC
    assert (root / "log.md").read_bytes() == log_before
    receipt = apply_mutation_write(prepared, {"document": b"valid replacement"})
    assert receipt.updated == ["synthetic/doc.md"]
    assert target.read_bytes() == b"valid replacement"


def test_mutation_write_preflights_log_content_and_apply_does_not_read_it(
    tmp_path,
    monkeypatch,
) -> None:
    import kb.core.write_pipeline as pipeline

    root = initialized(tmp_path)
    (root / "synthetic/doc.md").write_bytes(SYNTHETIC_DOC)
    prepared = prepare_mutation_write(
        load_write_context(root),
        MutationIntent(
            mutations=[
                MutationTarget(key="document", path=Path("synthetic/doc.md"))
            ],
            log_entry=LOG_ENTRY,
        ),
    )

    def forbidden_read(*_args, **_kwargs):
        raise AssertionError("apply_mutation_write must use preflighted log content")

    monkeypatch.setattr(pipeline, "read_rooted_bytes", forbidden_read)
    apply_mutation_write(prepared, {"document": b"replacement"})

    assert "| revised | kb-cli | KB-000001 |" in (
        root / "log.md"
    ).read_text(encoding="utf-8")
