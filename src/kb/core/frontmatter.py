from __future__ import annotations

import re
from collections.abc import Mapping

import yaml
from yaml.nodes import MappingNode, ScalarNode
from yaml.tokens import FlowEntryToken, FlowMappingEndToken, ScalarToken, Token

from kb.core.model import SyntheticFrontmatter


def yaml_scalar(value: str) -> str:
    dumped = yaml.safe_dump(
        value,
        allow_unicode=True,
        default_flow_style=True,
    ).strip()
    lines = dumped.splitlines()
    if lines and lines[-1] == "...":
        lines.pop()
    return "\n".join(lines).rstrip()


def render_synthetic_document(
    frontmatter: SyntheticFrontmatter,
    body: str,
) -> str:
    lines = [
        f"id: {yaml_scalar(frontmatter.id)}",
        f"type: {yaml_scalar(frontmatter.type)}",
        f"title: {yaml_scalar(frontmatter.title)}",
        f"description: {yaml_scalar(frontmatter.description)}",
        f"status: {yaml_scalar(frontmatter.status)}",
        "derived_from:",
        *(f"  - {yaml_scalar(parent)}" for parent in frontmatter.derived_from),
        f"timestamp: {frontmatter.timestamp}",
        f"last_human_touch: {frontmatter.last_human_touch}",
    ]
    if frontmatter.tags is not None:
        lines.extend(["tags:", *(f"  - {yaml_scalar(tag)}" for tag in frontmatter.tags)])
    if frontmatter.supersedes is not None:
        lines.append(f"supersedes: {yaml_scalar(frontmatter.supersedes)}")
    if frontmatter.instructions is not None:
        lines.append(f"instructions: {yaml_scalar(frontmatter.instructions)}")
    document = "---\n" + "\n".join(lines) + "\n---"
    return document if not body else document + "\n" + body


def _frontmatter_bounds(text: str) -> tuple[int, int, str]:
    opening = re.match(r"---(?P<eol>\r\n|\n|\r)", text)
    if opening is None:
        raise ValueError("missing opening frontmatter delimiter")
    eol = opening.group("eol")
    closing = re.search(r"(?m)^---(?:\r\n|\n|\r|$)", text[opening.end() :])
    if closing is None:
        raise ValueError("missing closing frontmatter delimiter")
    return opening.end(), opening.end() + closing.start(), eol


def _styled_scalar(value: str, style: str | None) -> str:
    if style == "'":
        return "'" + value.replace("'", "''") + "'"
    if style == '"':
        return yaml.safe_dump(value, default_style='"').strip().removesuffix("\n...")
    return value


def _render_scalar_token(source: str, token: ScalarToken, value: str) -> str:
    if token.style not in ("|", ">"):
        return _styled_scalar(value, token.style)
    original = source[token.start_mark.index : token.end_mark.index]
    header_end = re.search(r"\r\n|\n|\r", original)
    if header_end is None:
        raise ValueError("block scalar is missing its header line ending")
    content_start = header_end.end()
    content = original[content_start:]
    indentation = re.match(r"[ \t]*", content).group()
    trailing = re.search(r"(?:(?:[ \t]*)(?:\r\n|\n|\r))+\Z", content)
    suffix = "" if trailing is None else trailing.group()
    return original[:content_start] + indentation + value + suffix


def _missing_scalar_insertion(
    yaml_text: str,
    node: MappingNode,
    tokens: list[Token],
    missing: list[str],
    replacements: Mapping[str, str],
    eol: str,
) -> tuple[int, str]:
    rendered = [f"{key}: {replacements[key]}" for key in missing]
    if node.flow_style:
        closing = next(
            (
                token
                for token in tokens
                if isinstance(token, FlowMappingEndToken)
                and token.end_mark.index == node.end_mark.index
            ),
            None,
        )
        if closing is None:
            raise ValueError("top-level flow mapping has no closing token")
        closing_index = tokens.index(closing)
        has_trailing_separator = isinstance(tokens[closing_index - 1], FlowEntryToken)
        separator = "" if not node.value or has_trailing_separator else ", "
        return closing.start_mark.index, separator + ", ".join(rendered)
    insertion_at = node.end_mark.index
    prefix = "" if yaml_text[:insertion_at].endswith(("\n", "\r")) else eol
    return insertion_at, prefix + eol.join(rendered) + eol


def _validate_prepared_frontmatter(
    yaml_text: str, replacements: Mapping[str, str]
) -> None:
    try:
        effective = yaml.safe_load(yaml_text)
        node = yaml.compose(yaml_text)
    except yaml.YAMLError as error:
        raise ValueError(f"prepared frontmatter is invalid YAML: {error}") from error
    if not isinstance(effective, dict) or not isinstance(node, MappingNode):
        raise ValueError("prepared frontmatter must be a YAML mapping")
    prepared: dict[str, ScalarNode] = {}
    for key_node, value_node in node.value:
        if not isinstance(key_node, ScalarNode) or key_node.value not in replacements:
            continue
        if key_node.value in prepared:
            raise ValueError(
                f"prepared frontmatter key {key_node.value!r} must occur exactly once"
            )
        if not isinstance(value_node, ScalarNode):
            raise ValueError(
                f"prepared frontmatter value for {key_node.value!r} is not scalar"
            )
        prepared[key_node.value] = value_node
    for key, replacement in replacements.items():
        if key not in prepared or prepared[key].value != replacement:
            raise ValueError(
                f"prepared frontmatter value for {key!r} does not match replacement"
            )


def replace_frontmatter_scalars(
    source: bytes,
    replacements: Mapping[str, str],
    *,
    append_missing: tuple[str, ...] = (),
) -> bytes:
    text = source.decode("utf-8", errors="strict")
    start, end, eol = _frontmatter_bounds(text)
    yaml_text = text[start:end]
    node = yaml.compose(yaml_text)
    if not isinstance(node, MappingNode):
        raise ValueError("frontmatter must be a YAML mapping")
    effective = yaml.safe_load(yaml_text)
    if not isinstance(effective, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    tokens = list(yaml.scan(yaml_text))
    scalar_tokens = [token for token in tokens if isinstance(token, ScalarToken)]
    spans: list[tuple[int, int, str]] = []
    found: set[str] = set()
    for key_node, value_node in node.value:
        if not isinstance(key_node, ScalarNode):
            continue
        key = key_node.value
        if key not in replacements:
            continue
        if key in found:
            raise ValueError(f"frontmatter key {key!r} must occur exactly once")
        found.add(key)
        if not isinstance(value_node, ScalarNode):
            raise ValueError(f"frontmatter value for {key!r} is not directly editable")
        matching_tokens = [
            token
            for token in scalar_tokens
            if value_node.start_mark.index <= token.start_mark.index
            and token.end_mark.index <= value_node.end_mark.index
            and key_node.end_mark.index <= token.start_mark.index
        ]
        if len(matching_tokens) != 1:
            raise ValueError(f"frontmatter value for {key!r} is not directly editable")
        token = matching_tokens[0]
        spans.append(
            (
                token.start_mark.index,
                token.end_mark.index,
                _render_scalar_token(yaml_text, token, replacements[key]),
            )
        )
    indirect = [key for key in replacements if key not in found and key in effective]
    if indirect:
        raise ValueError(
            f"frontmatter value for {indirect[0]!r} must be an explicit key"
        )
    required = [
        key for key in replacements if key not in found and key not in append_missing
    ]
    if required:
        raise ValueError(
            f"frontmatter value for {required[0]!r} must be an explicit key"
        )
    missing = [key for key in append_missing if key not in found]
    if missing:
        insertion_at, insertion = _missing_scalar_insertion(
            yaml_text, node, tokens, missing, replacements, eol
        )
        spans.append((insertion_at, insertion_at, insertion))
    for value_start, value_end, replacement in sorted(spans, reverse=True):
        yaml_text = yaml_text[:value_start] + replacement + yaml_text[value_end:]
    _validate_prepared_frontmatter(yaml_text, replacements)
    return (text[:start] + yaml_text + text[end:]).encode("utf-8")
