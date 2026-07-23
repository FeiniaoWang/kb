import io
from pathlib import Path

import pytest

from kb.core.ids import next_id
from kb.core.model import DocClass
from kb.core.scan import (
    RootDiscoveryError,
    discover_root,
    doc_class_from_type,
    resolve_ref,
    scan,
)


class ObservedBytesIO(io.BytesIO):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        content = super().read(size)
        self.bytes_read += len(content)
        return content

    def readline(self, size: int = -1) -> bytes:
        content = super().readline(size)
        self.bytes_read += len(content)
        return content


def write_doc(root: Path, relative: str, frontmatter: str, body: str = "body\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return path


def test_discover_root_uses_explicit_or_closest_ancestor(tmp_path) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    leaf = inner / "a" / "b"
    leaf.mkdir(parents=True)
    (outer / "kb-config.json").write_text("{}", encoding="utf-8")
    (inner / "kb-config.json").write_text("{}", encoding="utf-8")
    assert discover_root(None, cwd=leaf) == inner.resolve()
    assert discover_root(outer, cwd=leaf) == outer.resolve()


def test_discover_root_reports_shared_error(tmp_path) -> None:
    with pytest.raises(RootDiscoveryError) as caught:
        discover_root(None, cwd=tmp_path)
    assert caught.value.code == "E_NO_KB"
    assert caught.value.message == (
        "not inside a knowledge base (no kb-config.json found); "
        "run 'kb init' or pass --kb"
    )


def test_scan_classifies_every_document_class_from_type(tmp_path) -> None:
    write_doc(tmp_path, "raw/sources/a.md", "id: RAW-000001\ntype: raw-source\n")
    write_doc(tmp_path, "synthetic/a.md", "id: KB-000001\ntype: coding-spec\n")
    write_doc(tmp_path, "governance/a.md", "id: GOVERNANCE-A\ntype: conventions\n")
    write_doc(tmp_path, "index.md", "type: index\ndescription: Root.\n")
    write_doc(tmp_path, "log.md", "type: log\n")
    kb = scan(tmp_path)
    assert [doc.doc_class for doc in kb.documents] == [
        DocClass.GOVERNANCE,
        DocClass.INDEX,
        DocClass.OPERATIONAL,
        DocClass.RAW,
        DocClass.SYNTHETIC,
    ]
    assert "RAW-000001" in kb.by_id
    assert next(doc for doc in kb.documents if doc.path == Path("log.md")).id is None


def test_charter_type_classifies_as_governance():
    assert doc_class_from_type("charter") is DocClass.GOVERNANCE


def test_scan_retains_parse_failures_and_missing_type_in_complete_file_view(tmp_path) -> None:
    write_doc(tmp_path, "bad-yaml.md", "type: [\n")
    write_doc(tmp_path, "missing-type.md", "id: RAW-000004\n")
    kb = scan(tmp_path)
    assert kb.documents == []
    assert [item.path.as_posix() for item in kb.files] == [
        "bad-yaml.md",
        "missing-type.md",
    ]
    assert kb.files[0].frontmatter is None
    assert kb.files[0].parse_error is not None
    assert kb.files[1].frontmatter is not None
    assert kb.files[1].parse_error is None
    assert [path.as_posix() for path, _ in kb.malformed] == [
        "bad-yaml.md",
        "missing-type.md",
    ]


def test_scan_keeps_bad_id_shapes_classifiable_for_validate(tmp_path) -> None:
    write_doc(tmp_path, "raw/sources/z-invalid.md", "id: [RAW-000009]\ntype: raw-source\n")
    write_doc(tmp_path, "raw/sources/a-invalid.md", "id: 7\ntype: raw-source\n")
    write_doc(tmp_path, "raw/sources/middle.md", "id: RAW-000005\ntype: raw-source\n")
    kb = scan(tmp_path)
    assert [document.path.as_posix() for document in kb.documents] == [
        "raw/sources/a-invalid.md",
        "raw/sources/middle.md",
        "raw/sources/z-invalid.md",
    ]
    assert [document.id for document in kb.documents] == [None, "RAW-000005", None]
    assert kb.malformed == []


def test_scan_retains_log_as_path_addressed_operational_document(tmp_path) -> None:
    write_doc(tmp_path, "log.md", "type: log\nid: KB-000099\ncustom: ignored\n")
    kb = scan(tmp_path)
    assert [item.path.as_posix() for item in kb.files] == ["log.md"]
    assert kb.files[0].frontmatter.root["type"] == "log"
    assert len(kb.documents) == 1
    assert kb.documents[0].doc_class is DocClass.OPERATIONAL
    assert kb.documents[0].id is None
    assert kb.by_id == {}
    assert kb.malformed == []


def test_scan_indexes_only_canonical_ids_on_id_bearing_classes(tmp_path) -> None:
    write_doc(tmp_path, "index.md", "type: index\ndescription: Root.\nid: KB-000001\n")
    write_doc(tmp_path, "raw/sources/bad.md", "id: RAW-0000001\ntype: raw-source\n")
    write_doc(tmp_path, "governance/charter.md", "id: GOVERNANCE-CHARTER\ntype: charter\n")
    kb = scan(tmp_path)
    assert kb.by_id == {"GOVERNANCE-CHARTER": kb.documents[0]}
    assert next(doc for doc in kb.documents if doc.path == Path("index.md")).id is None
    assert next(doc for doc in kb.documents if doc.path == Path("raw/sources/bad.md")).id is None


def test_document_body_is_loaded_lazily(tmp_path, monkeypatch) -> None:
    path = write_doc(tmp_path, "raw/sources/a.md", "id: RAW-000001\ntype: raw-source\n", "one\n")
    kb = scan(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("one", "two"), encoding="utf-8")
    assert kb.documents[0].body == "two\n"


def test_scan_reads_only_frontmatter_prefix_and_retains_no_source_bytes(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "synthetic/large.md"
    path.parent.mkdir(parents=True)
    prefix = b"---\nid: KB-000001\ntype: spec\ntitle: Large\n---\n"
    content = prefix + (b"body bytes that allocation must not read\n" * 100_000)
    path.write_bytes(content)
    opened: list[ObservedBytesIO] = []
    real_open = Path.open

    def observed_open(candidate: Path, mode: str = "r", *args, **kwargs):
        if candidate == path and mode == "rb":
            stream = ObservedBytesIO(content)
            opened.append(stream)
            return stream
        return real_open(candidate, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed_open)

    kb = scan(tmp_path)

    assert len(opened) == 1
    assert opened[0].bytes_read == len(prefix)
    document = kb.by_id["KB-000001"]
    assert not hasattr(document, "_source_bytes")


def test_scan_reads_to_eof_when_closing_delimiter_is_missing(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "synthetic/unclosed.md"
    path.parent.mkdir(parents=True)
    content = b"---\nid: KB-000001\ntype: spec\n" + (b"not a delimiter\n" * 500)
    path.write_bytes(content)
    opened: list[ObservedBytesIO] = []
    real_open = Path.open

    def observed_open(candidate: Path, mode: str = "r", *args, **kwargs):
        if candidate == path and mode == "rb":
            stream = ObservedBytesIO(content)
            opened.append(stream)
            return stream
        return real_open(candidate, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed_open)

    kb = scan(tmp_path)

    assert len(opened) == 1
    assert opened[0].bytes_read == len(content)
    assert kb.malformed[0][0] == Path("synthetic/unclosed.md")
    assert "closing frontmatter delimiter" in kb.malformed[0][1]


def test_resolve_ref_prefers_ids_and_accepts_extensionless_paths(tmp_path) -> None:
    write_doc(tmp_path, "synthetic/specs/webhook.md", "id: KB-000007\ntype: coding-spec\n")
    kb = scan(tmp_path)
    assert resolve_ref(kb, "KB-000007").path == Path("synthetic/specs/webhook.md")
    assert resolve_ref(kb, "synthetic/specs/webhook").id == "KB-000007"
    assert resolve_ref(kb, "/absolute.md") is None
    assert resolve_ref(kb, "KB-999999") is None


def test_resolve_ref_appends_md_without_replacing_existing_suffix(tmp_path) -> None:
    write_doc(tmp_path, "synthetic/specs/release.v2.md", "id: KB-000008\ntype: coding-spec\n")
    write_doc(tmp_path, "synthetic/specs/wrong.md", "id: KB-000009\ntype: coding-spec\n")
    kb = scan(tmp_path)
    assert resolve_ref(kb, "synthetic/specs/release.v2").id == "KB-000008"
    assert resolve_ref(kb, "synthetic/specs/wrong.txt") is None


def test_next_id_uses_max_numeric_id_for_prefix(tmp_path) -> None:
    write_doc(tmp_path, "raw/sources/a.md", "id: RAW-000001\ntype: raw-source\n")
    write_doc(tmp_path, "raw/sources/b.md", "id: RAW-000005\ntype: raw-source\n")
    write_doc(tmp_path, "governance/x.md", "id: GOVERNANCE-X\ntype: conventions\n")
    kb = scan(tmp_path)
    assert next_id(kb, "RAW").format() == "RAW-000006"
    assert next_id(kb, "CHAT").format() == "CHAT-000001"


def test_next_id_refuses_reserved_governance_prefix(tmp_path) -> None:
    kb = scan(tmp_path)
    with pytest.raises(ValueError, match="reserved id prefix: GOVERNANCE"):
        next_id(kb, "GOVERNANCE")
