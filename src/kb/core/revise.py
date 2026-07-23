from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr

from kb.core.frontmatter import replace_document_body, replace_frontmatter_keys
from kb.core.housekeeping import LogEntry, utc_now
from kb.core.model import Config, ConfigLoadError, DocClass, Document
from kb.core.safeio import (
    FileIdentity,
    inspect_rooted_file,
    read_rooted_bytes,
)
from kb.core.scan import KB, RootDiscoveryError, resolve_ref, scan_snapshot
from kb.core.validate import Finding, all_findings
from kb.core.write_pipeline import (
    AllocationBlocked,
    MutationIntent,
    MutationTarget,
    WriteContext,
    WriteFailure,
    apply_mutation_write,
    load_write_context,
    prepare_mutation_write,
)

ReviseStatus = Literal["draft", "current", "retired"]


class ReviseRequest(BaseModel):
    ref: str
    add_parents: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    status: ReviseStatus | None = None
    pending: list[str] = Field(default_factory=list)
    clear_pending: list[str] = Field(default_factory=list)
    body_change: bool = False
    human: bool = False
    actor: str = "kb-cli"
    kb_root: Path | None = None


class ReviseResult(BaseModel):
    id: str
    path: str
    updated: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PreparedRevise(BaseModel):
    request: ReviseRequest
    root: Path
    config: Config
    kb: KB
    link_pairs: list[tuple[str, str]]
    target_path: Path | None = None
    target_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    _context: WriteContext = PrivateAttr()
    _target_identity: FileIdentity | None = PrivateAttr(default=None)
    _target_content: bytes | None = PrivateAttr(default=None)
    _reference_snapshots: dict[Path, tuple[FileIdentity, bytes]] = PrivateAttr(
        default_factory=dict
    )
    _revised_frontmatter: bytes | None = PrivateAttr(default=None)
    _timestamp: str | None = PrivateAttr(default=None)
    _note: str | None = PrivateAttr(default=None)


class ReviseFailure(Exception):
    def __init__(self, code: str, message: str, exit_code: Literal[1, 2]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def _well_shaped_string_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _has_changes(request: ReviseRequest) -> bool:
    return bool(
        request.add_parents
        or request.links
        or request.status is not None
        or request.pending
        or request.clear_pending
        or request.body_change
    )


def _parse_link_tokens(tokens: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for token in tokens:
        link_type, separator, ref = token.partition("=")
        if not separator or not link_type.strip() or not ref.strip():
            raise ReviseFailure(
                "E_REVISE_LINK_INVALID",
                f"--link must be TYPE=REF: {token}",
                2,
            )
        pairs.append((link_type.strip(), ref.strip()))
    return pairs


def prepare_revise(request: ReviseRequest) -> PreparedRevise:
    try:
        context = load_write_context(request.kb_root)
    except RootDiscoveryError as error:
        raise ReviseFailure(error.code, error.message, 2) from error
    except ConfigLoadError as error:
        raise ReviseFailure(error.code, error.message, 2) from error
    except AllocationBlocked as error:
        paths = ", ".join(path.as_posix() for path in error.paths)
        raise ReviseFailure(
            "E_REVISE_MALFORMED",
            f"malformed documents block revision: {paths}; run kb validate",
            2,
        ) from error
    except WriteFailure as error:
        raise ReviseFailure("E_REVISE_IO", str(error.cause), 2) from error

    if not _has_changes(request):
        raise ReviseFailure(
            "E_REVISE_NO_CHANGES",
            "at least one change option is required (--add-parent, --link, "
            "--body-file, --status, --pending, --clear-pending)",
            2,
        )
    link_pairs = _parse_link_tokens(request.links)
    bound_path: Path | None = None
    bound_id: str | None = None
    prepared = PreparedRevise(
        request=request,
        root=context.root,
        config=context.config,
        kb=context.kb,
        link_pairs=link_pairs,
        target_path=bound_path,
        target_id=bound_id,
    )
    prepared._context = context
    target = _resolve_target(context.kb, request.ref)
    identity, content = _snapshot_document(prepared, target)
    prepared.target_path = target.path
    prepared.target_id = target.id
    prepared._target_identity = identity
    prepared._target_content = content
    _prepare_domain(prepared, target)
    return prepared


def _resolve_target(kb: KB, ref: str) -> Document:
    document = resolve_ref(kb, ref)
    if document is None:
        raise ReviseFailure(
            "E_REVISE_TARGET_UNRESOLVED",
            f"target cannot be resolved to a document: {ref}",
            1,
        )
    status = document.frontmatter.root.get("status")
    if (
        document.doc_class is not DocClass.SYNTHETIC
        or document.id is None
        or status == "superseded"
    ):
        raise ReviseFailure(
            "E_REVISE_TARGET_INVALID",
            f"target is not a revisable synthetic document: {ref} "
            f"(status={status!r})",
            1,
        )
    return document


def _resolve_id(kb: KB, ref: str, code: str) -> str:
    document = resolve_ref(kb, ref)
    if document is None or document.id is None:
        raise ReviseFailure(
            code,
            f"reference cannot be resolved to a document id: {ref}",
            1,
        )
    return document.id


def _snapshot_document(
    prepared: PreparedRevise,
    document: Document,
) -> tuple[FileIdentity, bytes]:
    try:
        identity = inspect_rooted_file(
            prepared.root,
            document.path,
            prepared._context._root_identity,
        )
        if identity is None:
            raise FileNotFoundError(document.path)
        content = read_rooted_bytes(
            prepared.root,
            document.path,
            prepared._context._root_identity,
            identity,
        )
    except OSError as error:
        raise ReviseFailure("E_REVISE_IO", str(error), 2) from error
    return identity, content


def _derivation_parents(kb: KB, doc_id: str) -> list[str]:
    document = kb.by_id.get(doc_id)
    if document is None or document.doc_class is not DocClass.SYNTHETIC:
        return []
    parents = document.frontmatter.root.get("derived_from")
    if not _well_shaped_string_list(parents):
        return []
    return [
        parent
        for parent in parents
        if (resolved := kb.by_id.get(parent)) is not None
        and resolved.doc_class is DocClass.SYNTHETIC
    ]


def _cycle_check(kb: KB, target_id: str, new_parent: str) -> None:
    parent_doc = kb.by_id.get(new_parent)
    if parent_doc is None or parent_doc.doc_class is not DocClass.SYNTHETIC:
        return
    predecessors: dict[str, str] = {}
    queue = deque([new_parent])
    seen = {new_parent}
    while queue:
        current = queue.popleft()
        if current == target_id:
            walk = [current]
            while walk[-1] != new_parent:
                walk.append(predecessors[walk[-1]])
            walk.append(target_id)
            walk.reverse()
            raise ReviseFailure(
                "E_REVISE_CYCLE",
                "adding this parent creates a derivation cycle: "
                + " -> ".join(walk),
                1,
            )
        for ancestor in _derivation_parents(kb, current):
            if ancestor not in seen:
                seen.add(ancestor)
                predecessors[ancestor] = current
                queue.append(ancestor)


def _decode_body(data: bytes) -> str:
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReviseFailure(
            "E_REVISE_BODY_NOT_TEXT",
            "body is not UTF-8 text",
            1,
        ) from error
    if not decoded.strip():
        return ""
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.rstrip("\n") + "\n"


def _snapshot_frontmatter(kb: KB) -> dict[Path, bytes]:
    snapshots: dict[Path, bytes] = {}
    for file in kb.files:
        if file.frontmatter is None:
            continue
        yaml_text = yaml.safe_dump(
            file.frontmatter.root,
            sort_keys=False,
            allow_unicode=True,
        )
        snapshots[file.path] = f"---\n{yaml_text}---\n".encode("utf-8")
    return snapshots


def _finding_identity(
    finding: Finding,
) -> tuple[str, str, str | None, tuple[int, int]]:
    return finding.code, finding.path, finding.id, finding.occurrence


_LINK_WARNING_TYPE = re.compile(r"link type '([^']+)'")


def _assert_bound_target(prepared: PreparedRevise, target: Document) -> None:
    if (
        prepared.target_path is None
        or prepared.target_id is None
        or prepared._target_identity is None
        or prepared._target_content is None
    ):
        return
    if target.path != prepared.target_path or target.id != prepared.target_id:
        raise ReviseFailure(
            "E_REVISE_IO",
            "target changed between preparation and execution",
            2,
        )
    try:
        identity = inspect_rooted_file(
            prepared.root,
            prepared.target_path,
            prepared._context._root_identity,
        )
        if identity is None:
            raise FileNotFoundError(prepared.target_path)
        content = read_rooted_bytes(
            prepared.root,
            prepared.target_path,
            prepared._context._root_identity,
            identity,
        )
    except OSError as error:
        raise ReviseFailure("E_REVISE_IO", str(error), 2) from error
    if identity != prepared._target_identity or content != prepared._target_content:
        raise ReviseFailure(
            "E_REVISE_IO",
            "target changed between preparation and execution",
            2,
        )


def _validate_proposed(
    prepared: PreparedRevise,
    target: Document,
    revised: bytes,
) -> list[str]:
    assert prepared._target_content is not None
    baseline_snapshots = _snapshot_frontmatter(prepared.kb)
    baseline_snapshots[target.path] = prepared._target_content
    baseline_snapshots.update(
        {
            path: content
            for path, (_, content) in prepared._reference_snapshots.items()
        }
    )
    baseline_kb = scan_snapshot(prepared.root, baseline_snapshots)
    proposed_snapshots = dict(baseline_snapshots)
    proposed_snapshots[target.path] = revised
    proposed_kb = scan_snapshot(prepared.root, proposed_snapshots)
    baseline = all_findings(baseline_kb, prepared.config)
    proposed = all_findings(proposed_kb, prepared.config)
    baseline_errors = {
        _finding_identity(finding)
        for finding in baseline
        if finding.severity == "error"
    }
    blocking = [
        finding
        for finding in proposed
        if finding.severity == "error"
        and (
            finding.path == target.path.as_posix()
            or _finding_identity(finding) not in baseline_errors
        )
    ]
    if blocking:
        codes = list(dict.fromkeys(finding.code for finding in blocking))
        raise ReviseFailure(
            "E_REVISE_VALIDATION",
            "proposed revision fails document-integrity validation: "
            + ", ".join(codes),
            1,
        )
    warnings: list[str] = []
    for finding in proposed:
        if finding.severity != "warning" or finding.path != target.path.as_posix():
            continue
        warnings.append(f"warning: {finding.code}: {finding.message}")
    return warnings


def _revision_timestamp(existing: object, current: str) -> str:
    candidate = datetime.fromisoformat(current.replace("Z", "+00:00"))
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    candidate = candidate.astimezone(timezone.utc)
    if isinstance(existing, str):
        try:
            previous = datetime.fromisoformat(existing.replace("Z", "+00:00"))
        except ValueError:
            previous = None
        if previous is not None:
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            previous = previous.astimezone(timezone.utc)
            if candidate <= previous:
                candidate = previous + timedelta(seconds=1)
    return candidate.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prepare_domain(prepared: PreparedRevise, target: Document) -> None:
    request = prepared.request
    kb = prepared.kb
    assert target.id is not None
    values = target.frontmatter.root

    parents = values.get("derived_from")
    existing_links = values.get("links", {})
    existing_pending = values.get("pending_upstream", [])
    editable = (
        _well_shaped_string_list(parents)
        and isinstance(existing_links, dict)
        and all(
            isinstance(link_type, str)
            and link_type.strip()
            and _well_shaped_string_list(targets)
            for link_type, targets in existing_links.items()
        )
        and _well_shaped_string_list(existing_pending)
    )
    if not editable:
        raise ReviseFailure(
            "E_REVISE_NOT_EDITABLE",
            f"target frontmatter cannot be edited losslessly: {request.ref}; "
            "run kb validate",
            1,
        )

    new_parents = list(parents)
    for ref in request.add_parents:
        parent_id = _resolve_id(kb, ref, "E_REVISE_PARENT_UNRESOLVED")
        if parent_id in new_parents:
            raise ReviseFailure(
                "E_REVISE_PARENT_DUPLICATE",
                f"parent is already declared: {ref} ({parent_id})",
                1,
            )
        _cycle_check(kb, target.id, parent_id)
        new_parents.append(parent_id)
    parents_changed = new_parents != parents

    warnings: list[str] = []
    new_links = {key: list(targets) for key, targets in existing_links.items()}
    warned_types: set[str] = set()
    for link_type, ref in prepared.link_pairs:
        link_id = _resolve_id(kb, ref, "E_REVISE_LINK_UNRESOLVED")
        targets = new_links.setdefault(link_type, [])
        if link_id in targets:
            raise ReviseFailure(
                "E_REVISE_LINK_DUPLICATE",
                f"link target is already declared for {link_type}: "
                f"{ref} ({link_id})",
                1,
            )
        targets.append(link_id)
        if (
            link_type not in prepared.config.link_types
            and link_type not in warned_types
        ):
            warned_types.add(link_type)
            warnings.append(
                "warning: link type is not declared in kb-config.json: "
                f"{link_type}"
            )
    links_changed = new_links != existing_links

    pending_adds = [
        _resolve_id(kb, ref, "E_REVISE_PENDING_UNRESOLVED")
        for ref in request.pending
    ]
    pending_clears = [
        _resolve_id(kb, ref, "E_REVISE_PENDING_UNRESOLVED")
        for ref in request.clear_pending
    ]
    if set(pending_adds) & set(pending_clears):
        raise ReviseFailure(
            "E_REVISE_PENDING_INVALID",
            "the same id cannot be both added and cleared",
            1,
        )
    new_pending = list(existing_pending)
    for marker in pending_adds:
        if marker not in new_parents:
            raise ReviseFailure(
                "E_REVISE_PENDING_INVALID",
                f"pending marker must name a derived_from parent: {marker}",
                1,
            )
        if marker in new_pending:
            raise ReviseFailure(
                "E_REVISE_PENDING_INVALID",
                f"pending marker is already set: {marker}",
                1,
            )
        new_pending.append(marker)
    for marker in pending_clears:
        if marker not in new_pending:
            raise ReviseFailure(
                "E_REVISE_PENDING_INVALID",
                f"pending marker is not set: {marker}",
                1,
            )
        new_pending.remove(marker)
    pending_changed = new_pending != existing_pending

    timestamp = _revision_timestamp(values.get("timestamp"), utc_now())
    set_keys: dict[str, object] = {"timestamp": timestamp}
    remove_keys: tuple[str, ...] = ()
    if request.human:
        set_keys["last_human_touch"] = timestamp
    if parents_changed:
        set_keys["derived_from"] = new_parents
    if links_changed:
        set_keys["links"] = new_links
    if pending_changed:
        if new_pending:
            set_keys["pending_upstream"] = new_pending
        else:
            remove_keys = ("pending_upstream",)
    if request.status is not None:
        set_keys["status"] = request.status

    note_parts: list[str] = []
    note_parts.extend(f"+parent {ref}" for ref in new_parents[len(parents) :])
    note_parts.extend(
        f"+link {link_type}={ref}"
        for link_type, targets in new_links.items()
        for ref in targets
        if ref not in existing_links.get(link_type, [])
    )
    if request.status is not None:
        note_parts.append(f"status {request.status}")
    if request.body_change:
        note_parts.append("body")
    note_parts.extend(f"+pending {ref}" for ref in pending_adds)
    note_parts.extend(f"-pending {ref}" for ref in pending_clears)
    note = target.path.as_posix() + (
        f" ({', '.join(note_parts)})" if note_parts else ""
    )

    try:
        revised = replace_frontmatter_keys(
            prepared._target_content,
            set_keys=set_keys,
            remove_keys=remove_keys,
        )
    except (UnicodeError, ValueError) as error:
        raise ReviseFailure(
            "E_REVISE_NOT_EDITABLE",
            f"target frontmatter cannot be edited losslessly: "
            f"{request.ref}: {error}",
            1,
        ) from error
    referenced_ids = set(new_parents)
    referenced_ids.update(
        target_id for targets in new_links.values() for target_id in targets
    )
    referenced_ids.update(new_pending)
    referenced_ids.update(pending_clears)
    for document_id in sorted(referenced_ids):
        document = kb.by_id.get(document_id)
        if document is None or document.path == target.path:
            continue
        prepared._reference_snapshots[document.path] = _snapshot_document(
            prepared, document
        )

    validation_warnings = _validate_proposed(prepared, target, revised)
    for warning in validation_warnings:
        if warning.startswith("warning: LINKTYPE_UNDECLARED:"):
            match = _LINK_WARNING_TYPE.search(warning)
            if match is not None and match.group(1) in warned_types:
                continue
        if warning not in warnings:
            warnings.append(warning)

    prepared.warnings = warnings
    prepared._revised_frontmatter = revised
    prepared._timestamp = timestamp
    prepared._note = note


def _assert_bound_references(prepared: PreparedRevise) -> None:
    for path, (expected_identity, expected_content) in (
        prepared._reference_snapshots.items()
    ):
        document = next(
            (candidate for candidate in prepared.kb.documents if candidate.path == path),
            None,
        )
        if document is None:
            raise ReviseFailure(
                "E_REVISE_IO",
                f"referenced document changed between preparation and execution: {path}",
                2,
            )
        identity, content = _snapshot_document(prepared, document)
        if identity != expected_identity or content != expected_content:
            raise ReviseFailure(
                "E_REVISE_IO",
                f"referenced document changed between preparation and execution: {path}",
                2,
            )


def execute_revise(
    prepared: PreparedRevise,
    body_data: bytes | None,
) -> ReviseResult:
    request = prepared.request
    target = _resolve_target(prepared.kb, request.ref)
    _assert_bound_target(prepared, target)
    _assert_bound_references(prepared)
    assert target.id is not None
    assert prepared._revised_frontmatter is not None
    assert prepared._timestamp is not None
    assert prepared._note is not None

    body = _decode_body(body_data) if body_data is not None else None
    revised = prepared._revised_frontmatter
    if body is not None:
        revised = replace_document_body(revised, body)

    intent = MutationIntent(
        mutations=[MutationTarget(key="document", path=target.path)],
        log_entry=LogEntry(
            at=prepared._timestamp,
            action="revised",
            actor=request.actor,
            doc_ids=[target.id],
            note=prepared._note,
        ),
    )
    try:
        prepared_write = prepare_mutation_write(prepared._context, intent)
    except WriteFailure as error:
        raise ReviseFailure("E_REVISE_IO", str(error.cause), 2) from error
    if prepared_write.sources["document"].content != prepared._target_content:
        raise ReviseFailure(
            "E_REVISE_IO",
            "target changed between preparation and execution",
            2,
        )

    try:
        receipt = apply_mutation_write(
            prepared_write,
            {"document": revised},
        )
    except WriteFailure as error:
        raise ReviseFailure("E_REVISE_IO", str(error.cause), 2) from error
    return ReviseResult(
        id=target.id,
        path=target.path.as_posix(),
        updated=receipt.updated,
        warnings=prepared.warnings,
    )
