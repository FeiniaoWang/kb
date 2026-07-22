from __future__ import annotations

import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr

from kb.core.model import Config, ConfigLoadError, DocClass, Document, load_config
from kb.core.scan import (
    ID_REF_PATTERN,
    KB,
    RootDiscoveryError,
    ScannedMarkdown,
    discover_root,
    doc_class_from_type,
    scan,
)

Severity = Literal["error", "warning"]

RESERVED_KEYS = {
    "id",
    "type",
    "title",
    "description",
    "status",
    "derived_from",
    "timestamp",
    "last_human_touch",
    "tags",
    "supersedes",
    "instructions",
    "ingested_at",
    "origin",
    "about",
}
STRING_FIELDS = {
    "id",
    "title",
    "description",
    "origin",
    "instructions",
    "supersedes",
    "about",
}
TIMESTAMP_FIELDS = {"timestamp", "last_human_touch", "ingested_at"}
STATUS_VALUES = {"draft", "current", "superseded", "retired"}
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
CANONICAL_NUMERIC_ID = re.compile(
    r"^(?P<prefix>[A-Z]+)-(?P<number>(?:[0-9]{6}|[1-9][0-9]{6,}))$"
)
RESERVED_SLUG_ID = re.compile(r"^GOVERNANCE-[A-Z][A-Z0-9-]*$")


class Finding(BaseModel):
    code: str
    severity: Severity
    path: str
    id: str | None
    message: str
    _occurrence: tuple[int, int] = PrivateAttr(default=(0, 0))

    @property
    def occurrence(self) -> tuple[int, int]:
        return self._occurrence


class ValidateRequest(BaseModel):
    refs: list[str] = Field(default_factory=list)
    strict: bool = False
    kb_root: Path | None = None


class ValidateResult(BaseModel):
    checked: int
    findings: list[Finding] = Field(default_factory=list)
    unresolved_refs: list[str] = Field(default_factory=list)
    exit_code: Literal[0, 1]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class ValidateFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code: Literal[2] = 2


def _literal_id(file: ScannedMarkdown) -> str | None:
    if file.frontmatter is None:
        return None
    value = file.frontmatter.root.get("id")
    return value if isinstance(value, str) else None


def _finding(
    file: ScannedMarkdown,
    code: str,
    severity: Severity,
    message: str,
    occurrence: int | tuple[int, int] = 0,
) -> Finding:
    finding = Finding(
        code=code,
        severity=severity,
        path=file.path.as_posix(),
        id=_literal_id(file),
        message=message,
    )
    finding._occurrence = (
        occurrence if isinstance(occurrence, tuple) else (occurrence, 0)
    )
    return finding


def _fm0(file: ScannedMarkdown, root: Path) -> list[Finding]:
    if file.parse_error is not None:
        reason = " ".join(file.parse_error.split())
        return [
            _finding(
                file,
                "FM0_UNPARSEABLE",
                "error",
                f"frontmatter cannot be parsed: {reason}",
            )
        ]
    try:
        (root / file.path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        reason = " ".join(str(error).split())
        return [
            _finding(
                file,
                "FM0_UNPARSEABLE",
                "error",
                f"frontmatter cannot be parsed: {reason}",
            )
        ]
    assert file.frontmatter is not None
    type_name = file.frontmatter.root.get("type")
    if not isinstance(type_name, str) or not type_name:
        return [
            _finding(
                file,
                "FM0_MISSING_TYPE",
                "error",
                "missing mandatory type frontmatter field",
            )
        ]
    return []


def _type_name(file: ScannedMarkdown) -> str:
    assert file.frontmatter is not None
    value = file.frontmatter.root["type"]
    assert isinstance(value, str) and value
    return value


def _canonical_numeric_id(value: str) -> tuple[str, str] | None:
    match = CANONICAL_NUMERIC_ID.fullmatch(value)
    return None if match is None else (match.group("prefix"), match.group("number"))


def _reserved_slug_id(value: str) -> bool:
    return RESERVED_SLUG_ID.fullmatch(value) is not None


def _class_contract(type_name: str) -> tuple[str, tuple[str, ...], set[str]]:
    if type_name in {"raw-source", "chat"}:
        return (
            "raw",
            ("id", "ingested_at", "origin"),
            {"id", "ingested_at", "origin", "title"},
        )
    if type_name == "feedback":
        return (
            "raw",
            ("id", "ingested_at", "origin", "about"),
            {"id", "ingested_at", "origin", "title", "about"},
        )
    if type_name in {"charter", "conventions", "kb-config", "health"}:
        return (
            "governance",
            ("id", "title", "description"),
            {"id", "title", "description"},
        )
    if type_name == "index":
        return "index", ("description",), {"description", "title"}
    return (
        "synthetic",
        (
            "id",
            "title",
            "description",
            "status",
            "derived_from",
            "timestamp",
            "last_human_touch",
        ),
        {
            "id",
            "title",
            "description",
            "status",
            "derived_from",
            "timestamp",
            "last_human_touch",
            "tags",
            "supersedes",
            "instructions",
        },
    )


def _location_expectation(type_name: str) -> tuple[bool, str]:
    if type_name == "index":
        return True, "a file named index.md"
    if type_name == "raw-source":
        return False, "under raw/sources/"
    if type_name == "chat":
        return False, "under raw/chats/"
    if type_name == "feedback":
        return False, "under raw/feedback/"
    if type_name in {"charter", "conventions", "kb-config", "health"}:
        return False, "under governance/"
    if type_name == "log":
        return False, "the root log.md"
    return False, "under synthetic/"


def _location_matches(file: ScannedMarkdown, type_name: str) -> bool:
    path = file.path
    if type_name == "index":
        return path.name == "index.md"
    if path.name == "index.md":
        return False
    if type_name == "log":
        return path == Path("log.md")
    expected = {
        "raw-source": Path("raw/sources"),
        "chat": Path("raw/chats"),
        "feedback": Path("raw/feedback"),
    }.get(type_name)
    if expected is None:
        expected = (
            Path("governance")
            if type_name in {"charter", "conventions", "kb-config", "health"}
            else Path("synthetic")
        )
    return path.parent == expected or expected in path.parent.parents


def _location_findings(file: ScannedMarkdown) -> list[Finding]:
    type_name = _type_name(file)
    if _location_matches(file, type_name):
        return []
    _, expectation = _location_expectation(type_name)
    return [
        _finding(
            file,
            "LOC_TYPE_MISMATCH",
            "error",
            f"type '{type_name}' does not agree with location "
            f"'{file.path.as_posix()}' (expected {expectation})",
        )
    ]


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _invalid_reason(field: str, value: object) -> str | None:
    if field in STRING_FIELDS:
        return (
            None
            if isinstance(value, str) and value.strip()
            else "must be a non-empty string"
        )
    if field == "status":
        return (
            None
            if isinstance(value, str) and value in STATUS_VALUES
            else "must be one of draft, current, superseded, retired"
        )
    if field in {"derived_from", "tags"}:
        valid = isinstance(value, list) and all(
            isinstance(item, str) and item.strip() for item in value
        )
        return None if valid else "must be a list of non-empty strings"
    if field in TIMESTAMP_FIELDS:
        return (
            None
            if _parse_timestamp(value) is not None
            else "must be an ISO-8601 date-time string"
        )
    return None


def _schema_findings(file: ScannedMarkdown) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    if type_name == "log":
        return []
    class_name, mandatory, legal = _class_contract(type_name)
    findings: list[Finding] = []
    for occurrence, field in enumerate(mandatory):
        if field not in values:
            findings.append(
                _finding(
                    file,
                    "FM1_FIELD_MISSING",
                    "error",
                    f"missing mandatory field '{field}' for {class_name} documents",
                    occurrence,
                )
            )
    for occurrence, (field, value) in enumerate(values.items()):
        if field == "type" or field not in RESERVED_KEYS:
            continue
        if field not in legal:
            findings.append(
                _finding(
                    file,
                    "FM1_KEY_FORBIDDEN",
                    "error",
                    f"key '{field}' is not part of the {class_name} schema",
                    occurrence,
                )
            )
            continue
        reason = _invalid_reason(field, value)
        if reason is not None:
            findings.append(
                _finding(
                    file,
                    "FM1_FIELD_INVALID",
                    "error",
                    f"field '{field}' is invalid: {reason}",
                    occurrence,
                )
            )
    description = values.get("description")
    if (
        "description" in legal
        and isinstance(description, str)
        and len(SENTENCE_END.findall(description)) > 2
    ):
        findings.append(
            _finding(
                file,
                "FM1_DESCRIPTION_LONG",
                "warning",
                "description exceeds two sentences",
                list(values).index("description"),
            )
        )
    return findings


def _vocabulary_findings(file: ScannedMarkdown, config: Config) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    if doc_class_from_type(type_name) is not DocClass.SYNTHETIC:
        return []
    findings: list[Finding] = []
    if config.types and type_name not in config.types:
        findings.append(
            _finding(
                file,
                "TYPE_UNDECLARED",
                "warning",
                f"type '{type_name}' is not declared in the kb-config.json types vocabulary",
                list(values).index("type"),
            )
        )
    tags = values.get("tags")
    if isinstance(tags, list) and all(
        isinstance(tag, str) and tag.strip() for tag in tags
    ):
        key_occurrence = list(values).index("tags") if "tags" in values else 0
        for offset, tag in enumerate(tags):
            if tag not in config.tags:
                findings.append(
                    _finding(
                        file,
                        "TAG_UNDECLARED",
                        "warning",
                        f"tag '{tag}' is not declared in the kb-config.json tags vocabulary",
                        (key_occurrence, offset),
                    )
                )
    return findings


def _prefix_contract(type_name: str) -> str | None:
    if type_name == "raw-source":
        return "source"
    if type_name in {"chat", "feedback"}:
        return type_name
    if doc_class_from_type(type_name) is DocClass.SYNTHETIC:
        return "synthetic"
    return None


def _id_findings(file: ScannedMarkdown, config: Config) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    class_name, _, legal = _class_contract(type_name)
    raw_id = values.get("id")
    if "id" not in legal or not isinstance(raw_id, str):
        return []
    occurrence = list(values).index("id")
    if class_name == "governance":
        if _reserved_slug_id(raw_id):
            return []
        return [
            _finding(
                file,
                "ID_INVALID",
                "error",
                f"id '{raw_id}' is not a valid governance id",
                occurrence,
            )
        ]
    parsed = _canonical_numeric_id(raw_id)
    if parsed is None:
        return [
            _finding(
                file,
                "ID_INVALID",
                "error",
                f"id '{raw_id}' is not a valid {class_name} id",
                occurrence,
            )
        ]
    class_key = _prefix_contract(type_name)
    if class_key is None:
        return []
    prefix, _ = parsed
    expected = config.id_prefixes[class_key]
    if prefix == expected:
        return []
    return [
        _finding(
            file,
            "ID_PREFIX_MISMATCH",
            "error",
            f"id prefix '{prefix}' does not match the configured {class_key} prefix '{expected}'",
            occurrence,
        )
    ]


def _resolved_document(kb: KB, value: str) -> Document | None:
    return kb.by_id.get(value)


def _well_shaped_string_list(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _relationship_findings(file: ScannedMarkdown, kb: KB) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    type_name = _type_name(file)
    doc_class = doc_class_from_type(type_name)
    findings: list[Finding] = []
    if doc_class is DocClass.SYNTHETIC:
        derived_from = values.get("derived_from")
        if _well_shaped_string_list(derived_from):
            occurrence = list(values).index("derived_from")
            for offset, parent in enumerate(derived_from):
                if _resolved_document(kb, parent) is None:
                    findings.append(
                        _finding(
                            file,
                            "LINK_UNRESOLVED",
                            "error",
                            f"derived_from reference '{parent}' does not resolve to a document id",
                            (occurrence, offset),
                        )
                    )
            if not derived_from:
                findings.append(
                    _finding(
                        file,
                        "DG1_NO_PARENTS",
                        "error",
                        "derived_from is empty — every synthetic document declares at least one parent",
                        occurrence,
                    )
                )
            elif not any(
                parent_doc is not None
                and parent_doc.frontmatter.root.get("type") == "chat"
                for parent_doc in (
                    _resolved_document(kb, parent) for parent in derived_from
                )
            ):
                findings.append(
                    _finding(
                        file,
                        "DG5_NO_SESSION_PARENT",
                        "error",
                        "no session record (type chat) among derived_from parents",
                        occurrence,
                    )
                )
        supersedes = values.get("supersedes")
        if (
            isinstance(supersedes, str)
            and supersedes.strip()
            and _resolved_document(kb, supersedes) is None
        ):
            findings.append(
                _finding(
                    file,
                    "LINK_UNRESOLVED",
                    "error",
                    f"supersedes reference '{supersedes}' does not resolve to a document id",
                    list(values).index("supersedes"),
                )
            )
    if type_name == "feedback":
        about = values.get("about")
        if (
            isinstance(about, str)
            and about.strip()
            and _resolved_document(kb, about) is None
        ):
            findings.append(
                _finding(
                    file,
                    "LINK_UNRESOLVED",
                    "error",
                    f"about reference '{about}' does not resolve to a document id",
                    list(values).index("about"),
                )
            )
    return findings


def _lifecycle_findings(file: ScannedMarkdown, kb: KB) -> list[Finding]:
    assert file.frontmatter is not None
    values = file.frontmatter.root
    if doc_class_from_type(_type_name(file)) is not DocClass.SYNTHETIC:
        return []
    findings: list[Finding] = []
    supersedes = values.get("supersedes")
    own_id = values.get("id")
    if isinstance(supersedes, str) and supersedes.strip():
        occurrence = list(values).index("supersedes")
        if isinstance(own_id, str) and supersedes == own_id:
            findings.append(
                _finding(
                    file,
                    "LS_SUPERSEDES_SELF",
                    "error",
                    "document supersedes itself",
                    occurrence,
                )
            )
        else:
            target = kb.by_id.get(supersedes)
            if target is not None:
                if target.doc_class is not DocClass.SYNTHETIC:
                    findings.append(
                        _finding(
                            file,
                            "LS_SUPERSEDES_NOT_SYNTHETIC",
                            "error",
                            f"supersedes target {supersedes} is not a synthetic document",
                            occurrence,
                        )
                    )
                else:
                    status = target.frontmatter.root.get("status")
                    if status != "superseded":
                        state = (
                            "has no status"
                            if "status" not in target.frontmatter.root
                            else f"has status '{status}'"
                        )
                        findings.append(
                            _finding(
                                file,
                                "LS_SUPERSEDES_NOT_MARKED",
                                "error",
                                f"supersedes target {supersedes} {state}, expected 'superseded'",
                                occurrence,
                            )
                        )
    timestamp = _parse_timestamp(values.get("timestamp"))
    touched = _parse_timestamp(values.get("last_human_touch"))
    if timestamp is not None and touched is not None:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if touched.tzinfo is None:
            touched = touched.replace(tzinfo=timezone.utc)
        if touched > timestamp:
            findings.append(
                _finding(
                    file,
                    "LS_TOUCH_AFTER_TIMESTAMP",
                    "warning",
                    f"last_human_touch {values['last_human_touch']} is later than timestamp {values['timestamp']}",
                    list(values).index("last_human_touch"),
                )
            )
    return findings


def _duplicate_id_findings(kb: KB) -> list[Finding]:
    participants: dict[str, list[ScannedMarkdown]] = {}
    for file in kb.files:
        if file.frontmatter is None:
            continue
        type_name = file.frontmatter.root.get("type")
        raw_id = file.frontmatter.root.get("id")
        if (
            isinstance(type_name, str)
            and type_name
            and type_name != "log"
            and isinstance(raw_id, str)
        ):
            participants.setdefault(raw_id, []).append(file)
    findings: list[Finding] = []
    for raw_id, files in participants.items():
        if len(files) < 2:
            continue
        for file in files:
            others = sorted(
                item.path.as_posix() for item in files if item.path != file.path
            )
            occurrence = list(file.frontmatter.root).index("id")
            findings.append(
                _finding(
                    file,
                    "ID_DUPLICATE",
                    "error",
                    f"id '{raw_id}' is also carried by {', '.join(others)}",
                    occurrence,
                )
            )
    return findings


def _finish_order(nodes: list[str], graph: dict[str, list[str]]) -> list[str]:
    visited: set[str] = set()
    finished: list[str] = []
    for start in nodes:
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, 0)]
        while stack:
            current, target_index = stack[-1]
            targets = graph.get(current, [])
            if target_index >= len(targets):
                stack.pop()
                finished.append(current)
                continue
            target = targets[target_index]
            stack[-1] = (current, target_index + 1)
            if target not in visited:
                visited.add(target)
                stack.append((target, 0))
    return finished


def _component_routes(
    root: str,
    members: set[str],
    graph: dict[str, list[str]],
    reverse: dict[str, list[str]],
) -> tuple[dict[str, str | None], dict[str, str]]:
    from_root: dict[str, str | None] = {root: None}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for target in graph.get(current, []):
            if target in members and target not in from_root:
                from_root[target] = current
                queue.append(target)

    to_root: dict[str, str] = {}
    queue = deque([root])
    reached = {root}
    while queue:
        current = queue.popleft()
        for predecessor in reverse[current]:
            if predecessor in members and predecessor not in reached:
                reached.add(predecessor)
                to_root[predecessor] = current
                queue.append(predecessor)
    return from_root, to_root


def _route_from_root(target: str, predecessors: dict[str, str | None]) -> list[str]:
    reversed_route = [target]
    while (predecessor := predecessors[reversed_route[-1]]) is not None:
        reversed_route.append(predecessor)
    return list(reversed(reversed_route))


def _simple_cycle(start: str, closed_walk: list[str]) -> list[str]:
    cycle: list[str] = []
    positions: dict[str, int] = {}
    for node in closed_walk:
        if node == start and cycle:
            return [*cycle, start]
        previous = positions.get(node)
        if previous is None:
            positions[node] = len(cycle)
            cycle.append(node)
            continue
        for removed in cycle[previous + 1 :]:
            positions.pop(removed)
        cycle = cycle[: previous + 1]
    raise AssertionError("cycle reconstruction did not return to its participant")


def _component_cycle_paths(
    component: list[str],
    graph: dict[str, list[str]],
    reverse: dict[str, list[str]],
) -> dict[str, list[str]]:
    members = set(component)
    root = component[0]
    from_root, to_root = _component_routes(root, members, graph, reverse)
    paths: dict[str, list[str]] = {}
    for participant in component:
        next_node = next(
            target for target in graph.get(participant, []) if target in members
        )
        if next_node == participant:
            paths[participant] = [participant, participant]
            continue
        closed_walk = [participant, next_node]
        while closed_walk[-1] != root:
            closed_walk.append(to_root[closed_walk[-1]])
        route_back = _route_from_root(participant, from_root)
        closed_walk.extend(route_back[1:])
        paths[participant] = _simple_cycle(participant, closed_walk)
    return paths


def _cycle_paths(graph: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return deterministic cycles after one iterative SCC discovery pass."""

    nodes = list(graph)
    reverse: dict[str, list[str]] = {node: [] for node in nodes}
    self_loops: set[str] = set()
    for source, targets in graph.items():
        for target in targets:
            if target not in reverse:
                reverse[target] = []
                nodes.append(target)
            reverse[target].append(source)
            if target == source:
                self_loops.add(source)

    finished = _finish_order(nodes, graph)
    assigned: set[str] = set()
    cyclic_components: list[list[str]] = []
    node_order = {node: index for index, node in enumerate(nodes)}
    for start in reversed(finished):
        if start in assigned:
            continue
        assigned.add(start)
        component: list[str] = []
        stack = [start]
        while stack:
            current = stack.pop()
            component.append(current)
            for predecessor in reversed(reverse[current]):
                if predecessor not in assigned:
                    assigned.add(predecessor)
                    stack.append(predecessor)
        component.sort(key=node_order.__getitem__)
        if len(component) > 1 or component[0] in self_loops:
            cyclic_components.append(component)

    paths: dict[str, list[str]] = {}
    for component in cyclic_components:
        paths.update(_component_cycle_paths(component, graph, reverse))
    return {node: paths[node] for node in nodes if node in paths}


def _cycle_from(start: str, graph: dict[str, list[str]]) -> list[str] | None:
    return _cycle_paths(graph).get(start)


def _derivation_graph(kb: KB) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for document in kb.by_id.values():
        if document.doc_class is not DocClass.SYNTHETIC or document.id is None:
            continue
        parents = document.frontmatter.root.get("derived_from")
        if not _well_shaped_string_list(parents):
            continue
        synthetic_parents = [
            parent
            for parent in parents
            if (resolved := kb.by_id.get(parent)) is not None
            and resolved.doc_class is DocClass.SYNTHETIC
        ]
        graph[document.id] = list(dict.fromkeys(synthetic_parents))
    return graph


def _cycle_findings(kb: KB) -> list[Finding]:
    graph = _derivation_graph(kb)
    cycle_paths = _cycle_paths(graph)
    files_by_path = {file.path: file for file in kb.files}
    findings: list[Finding] = []
    for document in kb.by_id.values():
        if document.doc_class is not DocClass.SYNTHETIC or document.id is None:
            continue
        cycle = cycle_paths.get(document.id)
        if cycle is None:
            continue
        file = files_by_path[document.path]
        parents = file.frontmatter.root.get("derived_from")
        occurrence = (
            list(file.frontmatter.root).index("derived_from")
            if _well_shaped_string_list(parents)
            else 0
        )
        findings.append(
            _finding(
                file,
                "DG2_CYCLE",
                "error",
                f"derivation cycle: {' -> '.join(cycle)}",
                occurrence,
            )
        )
    return findings


def _file_findings(file: ScannedMarkdown, config: Config, kb: KB) -> list[Finding]:
    fm0 = _fm0(file, kb.root)
    if fm0:
        return fm0
    findings = _location_findings(file)
    if _type_name(file) != "log":
        findings.extend(_schema_findings(file))
        findings.extend(_vocabulary_findings(file, config))
        findings.extend(_id_findings(file, config))
        findings.extend(_relationship_findings(file, kb))
        findings.extend(_lifecycle_findings(file, kb))
    return findings


def _all_findings(kb: KB, config: Config) -> list[Finding]:
    findings = [
        finding for file in kb.files for finding in _file_findings(file, config, kb)
    ]
    findings.extend(_duplicate_id_findings(kb))
    findings.extend(_cycle_findings(kb))
    return sorted(findings, key=lambda item: (item.path, item.code, item.occurrence))


def _stable_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _path_ref(ref: str) -> Path | None:
    candidate = PurePosixPath(ref)
    if candidate.is_absolute() or any(
        part in {".", ".."} for part in ref.split("/")
    ):
        return None
    if not str(candidate).endswith(".md"):
        candidate = PurePosixPath(f"{candidate}.md")
    return Path(*candidate.parts)


def _resolve_scope(kb: KB, refs: list[str]) -> tuple[set[Path], list[str]]:
    universe = {file.path for file in kb.files}
    if not refs:
        return universe, []
    scope: set[Path] = set()
    unresolved: list[str] = []
    for ref in _stable_unique(refs):
        resolved: Path | None
        if ID_REF_PATTERN.fullmatch(ref):
            document = kb.by_id.get(ref)
            resolved = None if document is None else document.path
        else:
            candidate = _path_ref(ref)
            resolved = candidate if candidate in universe else None
        if resolved is None:
            unresolved.append(ref)
        else:
            scope.add(resolved)
    return scope, unresolved


def validate(request: ValidateRequest) -> ValidateResult:
    try:
        root = discover_root(request.kb_root)
        config = load_config(root)
    except (RootDiscoveryError, ConfigLoadError) as error:
        raise ValidateFailure(error.code, error.message) from error
    kb = scan(root)
    all_findings = _all_findings(kb, config)
    scope, unresolved = _resolve_scope(kb, request.refs)
    findings = [item for item in all_findings if Path(item.path) in scope]
    failed = bool(unresolved) or any(
        item.severity == "error" for item in findings
    )
    if request.strict and findings:
        failed = True
    return ValidateResult(
        checked=len(scope),
        findings=findings,
        unresolved_refs=unresolved,
        exit_code=1 if failed else 0,
    )
