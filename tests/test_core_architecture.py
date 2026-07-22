from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest


FORBIDDEN_IMPORT_ROOTS = {"typer", "subprocess"}
FORBIDDEN_SYS_MEMBERS = {"stdin", "stdout", "stderr", "exit"}
FORBIDDEN_OS_EXACT = {"system", "popen"}


def forbidden_os_member(member: str) -> bool:
    return member in FORBIDDEN_OS_EXACT or member.startswith(
        ("spawn", "posix_spawn", "exec")
    )


def _qualified_names(node: ast.AST, aliases: dict[str, set[str]]) -> set[str]:
    if isinstance(node, ast.Name):
        return aliases[node.id] if node.id in aliases else {node.id}
    if isinstance(node, ast.Attribute):
        return {
            f"{owner}.{node.attr}"
            for owner in _qualified_names(node.value, aliases)
        }
    return set()


def _package_for(path: Path) -> list[str] | None:
    parts = path.parts
    candidates = [
        index
        for index, part in enumerate(parts[:-1])
        if part == "kb" and index + 1 < len(parts) and parts[index + 1] == "core"
    ]
    if not candidates:
        return None
    return list(parts[candidates[-1] : -1])


def _resolved_from_module(path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    package = _package_for(path)
    if package is None or node.level > len(package):
        return None
    resolved = package[: len(package) - node.level + 1]
    if node.module:
        resolved.extend(node.module.split("."))
    return ".".join(resolved)


def _is_core_cli(name: str) -> bool:
    return name == "kb.cli" or name.startswith("kb.cli.")


def _stored_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.List, ast.Tuple)):
        return {
            name
            for item in target.elts
            for name in _stored_names(item)
        }
    return set()


@dataclass
class _ScopeInfo:
    local_names: set[str]
    bindings: dict[str, set[str]]


class _ScopeCollector:
    def __init__(self, path: Path, arguments: set[str]) -> None:
        self.path = path
        self.local_names = set(arguments)
        self.direct_bindings: dict[str, set[str]] = {}
        self.assignments: list[tuple[set[str], ast.AST]] = []
        self.global_names: set[str] = set()
        self.nonlocal_names: set[str] = set()

    def _record(self, names: set[str], targets: set[str] | None = None) -> None:
        self.local_names.update(names)
        if targets:
            for name in names:
                self.direct_bindings.setdefault(name, set()).update(targets)

    def collect(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self._collect_statement(statement)

    def _collect_statement(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".", 1)[0]
                self._record(
                    {item.asname or root},
                    {item.name if item.asname else root},
                )
            return
        if isinstance(node, ast.ImportFrom):
            module = _resolved_from_module(self.path, node)
            if module is not None:
                for item in node.names:
                    if item.name != "*":
                        target = f"{module}.{item.name}" if module else item.name
                        self._record({item.asname or item.name}, {target})
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self._record({node.name})
            return
        if isinstance(node, ast.Assign):
            names = {
                name
                for target in node.targets
                for name in _stored_names(target)
            }
            self._record(names)
            if names and all(isinstance(target, ast.Name) for target in node.targets):
                self.assignments.append((names, node.value))
            return
        if isinstance(node, ast.AnnAssign):
            names = _stored_names(node.target)
            self._record(names)
            if names and node.value is not None and isinstance(node.target, ast.Name):
                self.assignments.append((names, node.value))
            return
        if isinstance(node, ast.AugAssign):
            self._record(_stored_names(node.target))
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self._record(_stored_names(node.target))
            self.collect(node.body)
            self.collect(node.orelse)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    self._record(_stored_names(item.optional_vars))
            self.collect(node.body)
            return
        if isinstance(node, ast.If):
            self.collect(node.body)
            self.collect(node.orelse)
            return
        if isinstance(node, ast.While):
            self.collect(node.body)
            self.collect(node.orelse)
            return
        if isinstance(node, (ast.Try, ast.TryStar)):
            self.collect(node.body)
            for handler in node.handlers:
                if handler.name is not None:
                    self._record({handler.name})
                self.collect(handler.body)
            self.collect(node.orelse)
            self.collect(node.finalbody)
            return
        if isinstance(node, ast.Match):
            for case in node.cases:
                names = {
                    candidate.name
                    for candidate in ast.walk(case.pattern)
                    if isinstance(candidate, ast.MatchAs) and candidate.name is not None
                }
                self._record(names)
                self.collect(case.body)
            return
        if isinstance(node, ast.Global):
            self.global_names.update(node.names)
            return
        if isinstance(node, ast.Nonlocal):
            self.nonlocal_names.update(node.names)
            return
        if isinstance(node, ast.Delete):
            self._record(
                {
                    name
                    for target in node.targets
                    for name in _stored_names(target)
                }
            )

    def result(self, outer: dict[str, set[str]]) -> _ScopeInfo:
        excluded = self.global_names | self.nonlocal_names
        local_names = self.local_names - excluded
        bindings = {
            name: set(targets)
            for name, targets in self.direct_bindings.items()
            if name in local_names
        }
        aliases = {name: set(targets) for name, targets in outer.items()}
        aliases.update({name: set(bindings.get(name, set())) for name in local_names})
        changed = True
        while changed:
            changed = False
            for names, value in self.assignments:
                targets = _qualified_names(value, aliases)
                for name in names & local_names:
                    previous = bindings.setdefault(name, set())
                    expanded = previous | targets
                    if expanded != previous:
                        bindings[name] = expanded
                        aliases[name] = set(expanded)
                        changed = True
        return _ScopeInfo(local_names=local_names, bindings=bindings)


def _function_arguments(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    arguments = {
        argument.arg
        for argument in [
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ]
    }
    if node.args.vararg is not None:
        arguments.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        arguments.add(node.args.kwarg.arg)
    return arguments


def _scope_info(
    path: Path,
    node: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    outer: dict[str, set[str]],
) -> _ScopeInfo:
    arguments = (
        _function_arguments(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        else set()
    )
    collector = _ScopeCollector(path, arguments)
    collector.collect(node.body)
    return collector.result(outer)


@dataclass
class _ScopeFrame:
    kind: str
    info: _ScopeInfo
    outer: dict[str, set[str]]
    lexical_outer: dict[str, set[str]]
    flow: dict[str, set[str]]


class _ArchitectureScanner(ast.NodeVisitor):
    def __init__(self, path: Path, tree: ast.Module) -> None:
        self.path = path
        self.found: set[str] = set()
        module_info = _scope_info(path, tree, {})
        self.frames = [
            _ScopeFrame(
                kind="module",
                info=module_info,
                outer={},
                lexical_outer={},
                flow={},
            )
        ]

    @property
    def current_frame(self) -> _ScopeFrame:
        return self.frames[-1]

    @property
    def current_aliases(self) -> dict[str, set[str]]:
        aliases = {
            name: set(targets)
            for name, targets in self.current_frame.outer.items()
        }
        aliases.update(
            {
                name: set(targets)
                for name, targets in self.current_frame.flow.items()
            }
        )
        return aliases

    def _bind(self, name: str, targets: set[str]) -> None:
        self.current_frame.flow[name] = set(targets)

    def _conservative_bindings(self) -> dict[str, set[str]]:
        frame = self.current_frame
        if frame.kind == "class":
            return {
                name: set(targets)
                for name, targets in frame.lexical_outer.items()
            }
        bindings = {
            name: set(targets)
            for name, targets in frame.outer.items()
        }
        bindings.update(
            {
                name: set(frame.info.bindings.get(name, set()))
                for name in frame.info.local_names
            }
        )
        return bindings

    def _report_qualified(self, node: ast.AST) -> None:
        for qualified in _qualified_names(node, self.current_aliases):
            parts = qualified.split(".")
            if (
                len(parts) >= 2
                and parts[0] == "sys"
                and parts[1] in FORBIDDEN_SYS_MEMBERS
            ):
                self.found.add(f"forbidden process global: sys.{parts[1]}")

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            root = item.name.split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                self.found.add(f"forbidden import: {root}")
            if _is_core_cli(item.name):
                self.found.add("forbidden core-to-CLI import: kb.cli")
            local = item.asname or root
            target = item.name if item.asname else root
            self._bind(local, {target})

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = _resolved_from_module(self.path, node)
        if module is None:
            return
        root = module.split(".", 1)[0]
        if root in FORBIDDEN_IMPORT_ROOTS:
            self.found.add(f"forbidden import: {root}")
        if _is_core_cli(module):
            self.found.add("forbidden core-to-CLI import: kb.cli")
        for item in node.names:
            if item.name == "*":
                if module in {"os", "sys"}:
                    self.found.add(f"forbidden wildcard import: {module}")
                continue
            target = f"{module}.{item.name}" if module else item.name
            if _is_core_cli(target):
                self.found.add("forbidden core-to-CLI import: kb.cli")
            if module == "sys" and item.name in FORBIDDEN_SYS_MEMBERS:
                self.found.add(f"forbidden process global: sys.{item.name}")
            self._bind(item.asname or item.name, {target})

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._report_qualified(node)
        self.visit(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        called_names = _qualified_names(node.func, self.current_aliases)
        if {"print", "builtins.print"} & called_names:
            self.found.add("forbidden output call: print")
        for called in called_names:
            parts = called.split(".")
            if (
                len(parts) == 2
                and parts[0] == "os"
                and forbidden_os_member(parts[1])
            ):
                self.found.add(f"forbidden process launch: {called}")
        self.visit(node.func)
        for argument in node.args:
            self.visit(argument)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        targets = _qualified_names(node.value, self.current_aliases)
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._bind(target.id, targets)
            else:
                self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        if isinstance(node.target, ast.Name):
            targets = (
                _qualified_names(node.value, self.current_aliases)
                if node.value is not None
                else set()
            )
            self._bind(node.target.id, targets)
        else:
            self.visit(node.target)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        if node.returns is not None:
            self.visit(node.returns)

        outer = self._conservative_bindings()
        info = _scope_info(self.path, node, outer)
        self.frames.append(
            _ScopeFrame(
                kind="function",
                info=info,
                outer=outer,
                lexical_outer=outer,
                flow={name: set() for name in info.local_names},
            )
        )
        for statement in node.body:
            self.visit(statement)
        self.frames.pop()
        self._bind(node.name, set())

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for decorator in node.decorator_list:
            self.visit(decorator)
        class_outer = self.current_aliases
        lexical_outer = self._conservative_bindings()
        info = _scope_info(self.path, node, class_outer)
        self.frames.append(
            _ScopeFrame(
                kind="class",
                info=info,
                outer=class_outer,
                lexical_outer=lexical_outer,
                flow={},
            )
        )
        for statement in node.body:
            self.visit(statement)
        self.frames.pop()
        self._bind(node.name, set())

    def _visit_branch(
        self,
        statements: list[ast.stmt],
        starting_flow: dict[str, set[str]],
    ) -> dict[str, set[str]]:
        frame = self.current_frame
        original = frame.flow
        frame.flow = {
            name: set(targets)
            for name, targets in starting_flow.items()
        }
        for statement in statements:
            self.visit(statement)
        result = {
            name: set(targets)
            for name, targets in frame.flow.items()
        }
        frame.flow = original
        return result

    @staticmethod
    def _merge_flows(
        flows: list[dict[str, set[str]]],
    ) -> dict[str, set[str]]:
        names = {name for flow in flows for name in flow}
        return {
            name: set().union(*(flow.get(name, set()) for flow in flows))
            for name in names
        }

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        before = {
            name: set(targets)
            for name, targets in self.current_frame.flow.items()
        }
        body_flow = self._visit_branch(node.body, before)
        else_flow = self._visit_branch(node.orelse, before) if node.orelse else before
        self.current_frame.flow = self._merge_flows([body_flow, else_flow])

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is not None:
            raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if {"SystemExit", "builtins.SystemExit"} & _qualified_names(
                raised, self.current_aliases
            ):
                self.found.add("forbidden process exit: SystemExit")
            self.visit(node.exc)
        if node.cause is not None:
            self.visit(node.cause)


def violations(path: Path, source: str) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    scanner = _ArchitectureScanner(path, tree)
    scanner.visit(tree)
    return sorted(scanner.found)


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


@pytest.mark.parametrize(
    ("path", "source"),
    [
        (Path("src/kb/core/example.py"), "import kb.cli.ingest\n"),
        (Path("src/kb/core/example.py"), "from kb.cli import ingest\n"),
        (Path("src/kb/core/example.py"), "from kb.cli import *\n"),
        (Path("src/kb/core/example.py"), "from kb import cli\n"),
        (Path("src/kb/core/example.py"), "from ..cli import ingest\n"),
        (Path("src/kb/core/example.py"), "from ..cli import *\n"),
        (Path("src/kb/core/nested/example.py"), "from ...cli import ingest\n"),
        (Path("src/kb/core/nested/example.py"), "from ... import cli\n"),
    ],
)
def test_scanner_rejects_core_to_cli_imports(path: Path, source: str) -> None:
    assert violations(path, source) == ["forbidden core-to-CLI import: kb.cli"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "import os\nlaunch = os.system\nlaunch('x')\n",
            ["forbidden process launch: os.system"],
        ),
        ("from os import *\nsystem('x')\n", ["forbidden wildcard import: os"]),
        ("from sys import *\nstdin.read()\n", ["forbidden wildcard import: sys"]),
    ],
)
def test_scanner_rejects_launch_alias_bypasses(
    source: str,
    expected: list[str],
) -> None:
    assert violations(Path("src/kb/core/example.py"), source) == expected


def test_scanner_allows_function_local_safe_shadowing() -> None:
    source = (
        "import os as dependency\n"
        "def local() -> None:\n"
        "    import pathlib as dependency\n"
        "    dependency.system('not a process launch')\n"
    )
    assert violations(Path("src/kb/core/example.py"), source) == []


def test_scanner_uses_late_module_bindings_for_function_globals() -> None:
    source = (
        "import pathlib as dependency\n"
        "def launch() -> None:\n"
        "    dependency.system('x')\n"
        "import os as dependency\n"
        "launch()\n"
    )
    assert violations(Path("src/kb/core/example.py"), source) == [
        "forbidden process launch: os.system"
    ]


def test_scanner_merges_possible_conditional_bindings() -> None:
    source = (
        "if choose_os:\n"
        "    import os as dependency\n"
        "else:\n"
        "    import pathlib as dependency\n"
        "dependency.system('x')\n"
    )
    assert violations(Path("src/kb/core/example.py"), source) == [
        "forbidden process launch: os.system"
    ]


def test_class_namespace_does_not_shadow_module_global_in_method() -> None:
    source = (
        "import os as dependency\n"
        "class Runner:\n"
        "    import pathlib as dependency\n"
        "    def launch(self) -> None:\n"
        "        dependency.system('x')\n"
    )
    assert violations(Path("src/kb/core/example.py"), source) == [
        "forbidden process launch: os.system"
    ]


def test_core_contains_no_delivery_or_process_dependencies() -> None:
    root = Path(__file__).parents[1] / "src" / "kb" / "core"
    found = [
        f"{path.relative_to(root)}: {item}"
        for path in sorted(root.rglob("*.py"))
        for item in violations(path, path.read_text(encoding="utf-8"))
    ]
    assert found == []
