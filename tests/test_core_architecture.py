from __future__ import annotations

import ast
from pathlib import Path

import pytest


FORBIDDEN_IMPORT_ROOTS = {"typer", "subprocess"}
FORBIDDEN_SYS_MEMBERS = {"stdin", "stdout", "stderr", "exit"}
FORBIDDEN_OS_EXACT = {"system", "popen"}


def forbidden_os_member(member: str) -> bool:
    return member in FORBIDDEN_OS_EXACT or member.startswith(
        ("spawn", "posix_spawn", "exec")
    )


def _import_aliases(tree: ast.AST) -> dict[str, set[str]]:
    aliases: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                local = item.asname or item.name.split(".", 1)[0]
                target = item.name if item.asname else local
                aliases.setdefault(local, set()).add(target)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for item in node.names:
                if item.name == "*":
                    continue
                local = item.asname or item.name
                aliases.setdefault(local, set()).add(f"{node.module}.{item.name}")
    return aliases


def _qualified_names(node: ast.AST, aliases: dict[str, set[str]]) -> set[str]:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, {node.id})
    if isinstance(node, ast.Attribute):
        return {
            f"{owner}.{node.attr}"
            for owner in _qualified_names(node.value, aliases)
        }
    return set()


def violations(path: Path, source: str) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    aliases = _import_aliases(tree)
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".", 1)[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    found.add(f"forbidden import: {root}")
            continue

        if isinstance(node, ast.ImportFrom) and node.module is not None:
            root = node.module.split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                found.add(f"forbidden import: {root}")
            if node.module == "sys":
                for item in node.names:
                    if item.name in FORBIDDEN_SYS_MEMBERS:
                        found.add(f"forbidden process global: sys.{item.name}")
            continue

        for qualified in _qualified_names(node, aliases):
            parts = qualified.split(".")
            if len(parts) >= 2 and parts[0] == "sys" and parts[1] in FORBIDDEN_SYS_MEMBERS:
                found.add(f"forbidden process global: sys.{parts[1]}")

        if isinstance(node, ast.Call):
            called_names = _qualified_names(node.func, aliases)
            if {"print", "builtins.print"} & called_names:
                found.add("forbidden output call: print")
            for called in called_names:
                parts = called.split(".")
                if len(parts) == 2 and parts[0] == "os" and forbidden_os_member(parts[1]):
                    found.add(f"forbidden process launch: {called}")

        if isinstance(node, ast.Raise) and node.exc is not None:
            raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if {"SystemExit", "builtins.SystemExit"} & _qualified_names(raised, aliases):
                found.add("forbidden process exit: SystemExit")

    return sorted(found)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import typer\n", ["forbidden import: typer"]),
        ("import subprocess as sp\nsp.run(['x'])\n", ["forbidden import: subprocess"]),
        ("from sys import stdin as stream\nstream.read()\n", ["forbidden process global: sys.stdin"]),
        ("import sys as runtime\nruntime.stdout.write('x')\n", ["forbidden process global: sys.stdout"]),
        ("from sys import stderr as stream\n", ["forbidden process global: sys.stderr"]),
        ("from sys import exit as stop\n", ["forbidden process global: sys.exit"]),
        (
            "import sys\nsys.stderr.write('x')\nsys.exit(1)\n",
            [
                "forbidden process global: sys.exit",
                "forbidden process global: sys.stderr",
            ],
        ),
        ("print('x')\n", ["forbidden output call: print"]),
        ("import builtins\nbuiltins.print('x')\n", ["forbidden output call: print"]),
        (
            "import os\n"
            "os.system('x')\n"
            "os.popen('x')\n"
            "os.spawnv(0, 'x', ['x'])\n"
            "os.posix_spawn('/x', ['/x'], {})\n"
            "os.execve('/x', ['/x'], {})\n",
            [
                "forbidden process launch: os.execve",
                "forbidden process launch: os.popen",
                "forbidden process launch: os.posix_spawn",
                "forbidden process launch: os.spawnv",
                "forbidden process launch: os.system",
            ],
        ),
        ("from os import execv as replace\nreplace('/x', ['/x'])\n", ["forbidden process launch: os.execv"]),
        ("raise SystemExit\n", ["forbidden process exit: SystemExit"]),
        ("raise SystemExit('message')\n", ["forbidden process exit: SystemExit"]),
        ("import os.path\nos.system('x')\n", ["forbidden process launch: os.system"]),
        (
            "import os as runner\n"
            "runner.system('x')\n"
            "import pathlib as runner\n",
            ["forbidden process launch: os.system"],
        ),
        (
            "import os as runner\n"
            "def local() -> None:\n"
            "    import pathlib as runner\n"
            "runner.system('x')\n",
            ["forbidden process launch: os.system"],
        ),
        ("import os\nos.open('x', 0)\nos.fdopen(0)\n", []),
        ("from pathlib import Path\nPath('x')\n", []),
    ],
)
def test_scanner_detects_aliases(source: str, expected: list[str]) -> None:
    assert violations(Path("example.py"), source) == expected


def test_core_contains_no_delivery_or_process_dependencies() -> None:
    root = Path(__file__).parents[1] / "src" / "kb" / "core"
    found = [
        f"{path.relative_to(root)}: {item}"
        for path in sorted(root.rglob("*.py"))
        for item in violations(path, path.read_text(encoding="utf-8"))
    ]
    assert found == []
