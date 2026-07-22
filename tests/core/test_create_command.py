from pathlib import Path

import pytest

from kb.core.create import (
    CreateFailure,
    CreateRequest,
    execute_create,
    prepare_create,
)


def add_chat(root: Path) -> None:
    path = root / "raw/chats/planning.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "id: CHAT-000001\n"
        "type: chat\n"
        "ingested_at: 2026-07-16T09:00:00Z\n"
        "origin: stdin\n"
        "title: Planning\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )


def request(root: Path) -> CreateRequest:
    return CreateRequest(
        type_name="spec",
        title="Explicit body",
        description="Exercises explicit body bytes.",
        derived_from=["CHAT-000001"],
        kb_root=root,
    )


def test_prepare_then_execute_accepts_explicit_body_bytes(initialized_kb: Path) -> None:
    add_chat(initialized_kb)
    prepared = prepare_create(request(initialized_kb))
    result = execute_create(prepared, b"body\r\n")
    assert result.id == "KB-000001"
    assert (initialized_kb / result.path).read_bytes().endswith(b"---\nbody\n")


def test_execute_create_keeps_strict_utf8_in_core(initialized_kb: Path) -> None:
    add_chat(initialized_kb)
    prepared = prepare_create(request(initialized_kb))
    with pytest.raises(CreateFailure) as raised:
        execute_create(prepared, b"\xff")
    assert (raised.value.code, raised.value.exit_code) == (
        "E_CREATE_BODY_NOT_TEXT",
        1,
    )
