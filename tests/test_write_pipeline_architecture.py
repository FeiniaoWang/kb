import ast
from importlib.util import resolve_name
from pathlib import Path

import pytest


COMMAND_MODULES = ("src/kb/core/create.py", "src/kb/core/ingest.py")
HOUSEKEEPING_INDEXING_PERSISTENCE = {
    "append_log",
    "create_directory_index",
    "regenerate_directory_index",
}
RETIRED_ORCHESTRATION_HELPERS = {"_new_directories", "_new_index_contents"}
WRITE_PIPELINE_IMPORT_ALLOWLISTS = {
    "src/kb/core/create.py": frozenset(
        {
            "AllocationBlocked",
            "DocumentBirth",
            "MutationTarget",
            "WriteFailure",
            "WriteIntent",
            "apply_write",
            "load_write_context",
            "prepare_write",
        }
    ),
    "src/kb/core/ingest.py": frozenset(
        {
            "AllocationBlocked",
            "CompanionBirth",
            "DocumentBirth",
            "WriteFailure",
            "WriteIntent",
            "apply_write",
            "load_write_context",
            "prepare_write",
        }
    ),
}


def source(relative: str) -> str:
    return Path(relative).read_text(encoding="utf-8")


def parsed(text: str) -> ast.Module:
    return ast.parse(text)


def imported_names(text: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(parsed(text)):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name.rsplit(".", 1)[-1] for alias in node.names)
    return names


def imported_modules(text: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(parsed(text)):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def wildcard_imports(text: str) -> set[str]:
    return {
        node.module
        for node in ast.walk(parsed(text))
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and any(alias.name == "*" for alias in node.names)
    }


def resolved_import_from_module(
    node: ast.ImportFrom,
    package: str = "kb.core",
) -> str:
    module = node.module or ""
    if node.level == 0:
        return module
    try:
        return resolve_name(f"{'.' * node.level}{module}", package)
    except ImportError:
        return ""


def safeio_import_dependencies(text: str) -> set[str]:
    dependencies: set[str] = set()
    for node in ast.walk(parsed(text)):
        if isinstance(node, ast.ImportFrom):
            module = resolved_import_from_module(node)
            if (
                module == "kb.core.safeio"
                or module.startswith("kb.core.safeio.")
                or (
                    module == "kb.core"
                    and any(alias.name == "safeio" for alias in node.names)
                )
            ):
                dependencies.add("kb.core.safeio")
        elif isinstance(node, ast.Import) and any(
            alias.name == "kb.core.safeio"
            or alias.name.startswith("kb.core.safeio.")
            for alias in node.names
        ):
            dependencies.add("kb.core.safeio")
    return dependencies


def write_pipeline_import_violations(
    text: str,
    allowed: set[str] | frozenset[str],
) -> set[str]:
    module_name = "kb.core.write_pipeline"
    violations: set[str] = set()
    for node in ast.walk(parsed(text)):
        if isinstance(node, ast.ImportFrom):
            module = resolved_import_from_module(node)
            if module == module_name:
                violations.update(
                    f"{module_name}.{alias.name}"
                    for alias in node.names
                    if alias.name == "*" or alias.name not in allowed
                )
            elif module == "kb.core" and any(
                alias.name == "write_pipeline" for alias in node.names
            ):
                violations.add(module_name)
        elif isinstance(node, ast.Import):
            violations.update(
                alias.name
                for alias in node.names
                if alias.name == module_name
                or alias.name.startswith(f"{module_name}.")
            )
    return violations


def _simple_callable_bindings(tree: ast.Module) -> dict[str, set[str]]:
    bindings: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname is not None:
                    bindings.setdefault(alias.asname, set()).add(alias.name)
    for node in ast.walk(tree):
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if isinstance(value, ast.Name):
            referenced_name = value.id
        elif isinstance(value, ast.Attribute):
            referenced_name = value.attr
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                bindings.setdefault(target.id, set()).add(referenced_name)
    return bindings


def _reachable_names(name: str, bindings: dict[str, set[str]]) -> set[str]:
    reachable: set[str] = set()
    seen: set[str] = set()
    pending = [name]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        targets = bindings.get(current)
        if targets:
            pending.extend(targets)
        else:
            reachable.add(current)
    return reachable


def directly_called_names(text: str) -> set[str]:
    tree = parsed(text)
    bindings = _simple_callable_bindings(tree)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.update(_reachable_names(node.func.id, bindings))
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def qualified_called_names(text: str) -> set[str]:
    tree = parsed(text)
    import_bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                if alias.name != "*":
                    import_bindings[alias.asname or alias.name] = (
                        f"{node.module}.{alias.name}"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                import_bindings[bound_name] = alias.name if alias.asname else bound_name

    def qualified_name(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return import_bindings.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            value = qualified_name(node.value)
            return None if value is None else f"{value}.{node.attr}"
        return None

    return {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (name := qualified_name(node.func)) is not None
    }


PATH_MUTATORS = {
    "chmod",
    "copy",
    "copy_into",
    "hardlink_to",
    "lchmod",
    "link_to",
    "mkdir",
    "move",
    "move_into",
    "rename",
    "replace",
    "rmdir",
    "symlink_to",
    "touch",
    "unlink",
    "write_bytes",
    "write_text",
}
FILE_MUTATORS = {"truncate", "write", "writelines"}
OS_MUTATORS = {
    "chflags",
    "chmod",
    "chown",
    "copy_file_range",
    "fchmod",
    "fchown",
    "fdopen",
    "ftruncate",
    "lchflags",
    "lchmod",
    "lchown",
    "link",
    "makedirs",
    "mkfifo",
    "mkdir",
    "mknod",
    "open",
    "posix_fallocate",
    "pwrite",
    "pwritev",
    "remove",
    "removexattr",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "rmdir",
    "sendfile",
    "setxattr",
    "splice",
    "symlink",
    "truncate",
    "unlink",
    "utime",
    "write",
    "writev",
}
SHUTIL_MUTATORS = {
    "chown",
    "copy",
    "copy2",
    "copyfile",
    "copyfileobj",
    "copymode",
    "copystat",
    "copytree",
    "make_archive",
    "move",
    "rmtree",
    "unpack_archive",
}
READ_ONLY_OPEN_MODES = {"r", "rb", "rt"}


def filesystem_write_violations(text: str) -> set[str]:
    tree = parsed(text)
    origins: dict[str, set[str]] = {"open": {"builtins.open"}}

    def add_origin(name: str, origin: str) -> None:
        origins.setdefault(name, set()).add(origin)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", 1)[0]
                add_origin(bound, alias.name if alias.asname else bound)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            module = resolved_import_from_module(node)
            for alias in node.names:
                if alias.name != "*":
                    add_origin(alias.asname or alias.name, f"{module}.{alias.name}")

    def expression_origins(node: ast.expr | None) -> set[str]:
        if node is None:
            return set()
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {"Scalar"}
        if isinstance(node, ast.JoinedStr):
            return {"Scalar"}
        if isinstance(node, ast.Name):
            return set(origins.get(node.id, {node.id}))
        if isinstance(node, ast.Attribute):
            result: set[str] = set()
            for base in expression_origins(node.value):
                if base == "PathInstance" and node.attr in {
                    "anchor",
                    "drive",
                    "name",
                    "stem",
                    "suffix",
                }:
                    result.add("Scalar")
                else:
                    result.add(f"{base}.{node.attr}")
            return result
        if isinstance(node, ast.Call):
            result: set[str] = set()
            for called in expression_origins(node.func):
                attribute = called.rsplit(".", 1)[-1]
                if called == "pathlib.Path":
                    result.add("PathInstance")
                elif called.startswith("PathInstance.") and attribute in {
                    "absolute",
                    "expanduser",
                    "resolve",
                    "with_name",
                    "with_suffix",
                }:
                    result.add("PathInstance")
                elif called in {"builtins.open", "io.open"}:
                    result.add("FileObject")
                elif attribute in {
                    "decode",
                    "lower",
                    "lstrip",
                    "rstrip",
                    "strip",
                    "upper",
                } or (attribute == "replace" and called.startswith("Scalar.")):
                    result.add("Scalar")
                elif attribute == "replace" and called.startswith("PathInstance."):
                    result.add("PathInstance")
            return result
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            if "PathInstance" in expression_origins(node.left):
                return {"PathInstance"}
        return set()

    def bind(target: ast.expr, new_origins: set[str]) -> bool:
        if not new_origins or not isinstance(target, ast.Name):
            return False
        bound = origins.setdefault(target.id, set())
        before = len(bound)
        bound.update(new_origins)
        return len(bound) != before

    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            if isinstance(node, ast.Assign):
                new_origins = expression_origins(node.value)
                changed |= any(bind(target, new_origins) for target in node.targets)
            else:
                new_origins = expression_origins(node.value)
                if not new_origins and "pathlib.Path" in expression_origins(
                    node.annotation
                ):
                    new_origins = {"PathInstance"}
                changed |= bind(node.target, new_origins)
        if not changed:
            break

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            if "pathlib.Path" in expression_origins(argument.annotation):
                add_origin(argument.arg, "PathInstance")

    def open_mode(
        node: ast.Call,
        qualified: str,
        label: str,
    ) -> ast.expr | None:
        for keyword in node.keywords:
            if keyword.arg == "mode":
                return keyword.value
        position = (
            1
            if label == "Path.open" and qualified == "pathlib.Path.open"
            else 0 if label == "Path.open" else 1
        )
        return node.args[position] if len(node.args) > position else None

    violations: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for qualified in expression_origins(node.func):
            attribute = qualified.rsplit(".", 1)[-1]

            if qualified.startswith("os.") and attribute in OS_MUTATORS:
                violations.add(f"os.{attribute}")
                continue
            if qualified.startswith("shutil.") and attribute in SHUTIL_MUTATORS:
                violations.add(f"shutil.{attribute}")
                continue
            if attribute in FILE_MUTATORS:
                violations.add(f"file.{attribute}")
                continue
            if attribute in PATH_MUTATORS and not (
                attribute == "replace" and qualified.startswith("Scalar.")
            ):
                violations.add(f"Path.{attribute}")
                continue

            open_label: str | None = None
            if qualified == "builtins.open":
                open_label = "builtins.open"
            elif qualified == "io.open":
                open_label = "io.open"
            elif attribute == "open":
                open_label = "Path.open"
            if open_label is None:
                continue
            mode = open_mode(node, qualified, open_label)
            if mode is None:
                continue
            if not (
                isinstance(mode, ast.Constant)
                and isinstance(mode.value, str)
                and mode.value in READ_ONLY_OPEN_MODES
            ):
                violations.add(open_label)
    return violations


def function_definitions(text: str) -> list[str]:
    return [
        node.name
        for node in ast.walk(parsed(text))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def test_ast_names_detect_aliased_and_formatting_varied_persistence() -> None:
    text = """
from kb.core.safeio import create_rooted_file_bytes as birth
import kb.core.safeio as safeio

birth(root, path, content, identity)
safeio.overwrite_rooted_bytes (root, path, content, identity, expected)
"""

    assert "create_rooted_file_bytes" in imported_names(text)
    assert {
        "create_rooted_file_bytes",
        "overwrite_rooted_bytes",
    } <= directly_called_names(text)


def test_ast_names_follow_wildcard_callable_rebinding() -> None:
    text = """
from kb.core.safeio import *

birth = create_rooted_file_bytes
wrapped_birth = birth
wrapped_birth(root, path, content, identity)
"""

    assert wildcard_imports(text) == {"kb.core.safeio"}
    assert "create_rooted_file_bytes" in directly_called_names(text)


def test_ast_gate_detects_aliased_direct_safeio_read_dependency() -> None:
    text = "from kb.core.safeio import read_rooted_bytes as read\n"

    assert safeio_import_dependencies(text) == {"kb.core.safeio"}


def test_ast_gate_detects_aliased_safeio_module_dependency() -> None:
    text = "import kb.core.safeio as safeio\n"

    assert safeio_import_dependencies(text) == {"kb.core.safeio"}


def test_ast_gate_detects_wildcard_and_parent_module_safeio_dependencies() -> None:
    assert safeio_import_dependencies("from kb.core.safeio import *\n") == {
        "kb.core.safeio"
    }
    assert safeio_import_dependencies("from kb.core import safeio as storage\n") == {
        "kb.core.safeio"
    }


def test_ast_gate_resolves_deeper_relative_safeio_dependencies() -> None:
    assert safeio_import_dependencies(
        "from ..core.safeio import read_rooted_bytes as read\n"
    ) == {"kb.core.safeio"}
    assert safeio_import_dependencies(
        "from ..core import safeio as storage\n"
    ) == {"kb.core.safeio"}


def test_ast_gate_rejects_write_pipeline_reexports_and_module_bypasses() -> None:
    allowed = {
        "AllocationBlocked",
        "DocumentBirth",
        "MutationTarget",
        "WriteFailure",
        "WriteIntent",
        "apply_write",
        "load_write_context",
        "prepare_write",
    }
    assert write_pipeline_import_violations(
        "from kb.core.write_pipeline import create_rooted_file_bytes as persist\n",
        allowed,
    ) == {"kb.core.write_pipeline.create_rooted_file_bytes"}
    assert write_pipeline_import_violations(
        "import kb.core.write_pipeline as pipeline\n",
        allowed,
    ) == {"kb.core.write_pipeline"}
    assert write_pipeline_import_violations(
        "from ..core import write_pipeline as pipeline\n",
        allowed,
    ) == {"kb.core.write_pipeline"}
    assert write_pipeline_import_violations(
        "from kb.core.write_pipeline import *\n",
        allowed,
    ) == {"kb.core.write_pipeline.*"}


def test_ast_names_follow_module_attribute_callable_rebinding() -> None:
    text = """
import kb.core.safeio as safeio

birth = safeio.create_rooted_file_bytes
wrapped_birth = birth
wrapped_birth(root, path, content, identity)
"""

    assert "create_rooted_file_bytes" in directly_called_names(text)


def test_ast_names_preserve_forbidden_edges_after_later_reassignment() -> None:
    text = """
import kb.core.safeio as safeio

birth = safeio.create_rooted_file_bytes
birth(root, path, content, identity)
birth = domain.harmless
"""

    assert "create_rooted_file_bytes" in directly_called_names(text)


def test_ast_names_preserve_forbidden_edges_across_scope_reuse() -> None:
    text = """
import kb.core.safeio as safeio

def persist():
    birth = safeio.create_rooted_file_bytes
    birth(root, path, content, identity)

def benign():
    birth = domain.harmless
    birth()
"""

    assert "create_rooted_file_bytes" in directly_called_names(text)


def test_ast_names_terminate_on_alias_cycles_and_keep_forbidden_edges() -> None:
    text = """
import kb.core.safeio as safeio

birth = safeio.create_rooted_file_bytes
wrapped_birth = birth
birth = wrapped_birth
wrapped_birth(root, path, content, identity)
"""

    assert "create_rooted_file_bytes" in directly_called_names(text)


def test_qualified_calls_accept_module_style_imports() -> None:
    text = """
import kb.core.naming as naming

naming.slug("Title", "fallback")
"""

    assert "kb.core.naming.slug" in qualified_called_names(text)


def test_direct_write_gate_allows_current_read_only_external_acquisition() -> None:
    text = """
import io
from pathlib import Path

Path("source.md").read_bytes()
Path("source.md").read_text(encoding="utf-8")
open("source.md")
open("source.md", "rb")
io.open("source.md", mode="rt")
Path("source.md").open()
Path("source.md").open("r")
Path("source.md").open(mode="rb")
Path.open(Path("source.md"), "rt")
reader = Path.open
reader(Path("source.md"), "rb")
value = "old"
value.replace("old", "new")
model.model_dump()
LogEntry(action="created")
"""

    assert filesystem_write_violations(text) == set()


def test_direct_write_gate_detects_mutating_path_methods_through_aliases() -> None:
    text = """
from pathlib import Path as P

target: P = P("target.md")
target.write_text("content")
target.mkdir()
target.replace(P("replacement.md"))
P("mode.md").chmod(0o600)
target.copy(P("copy.md"))
target.copy_into(P("copies"))
target.move(P("moved.md"))
target.move_into(P("moves"))
target.lchmod(0o600)
"""

    assert {
        "Path.write_text",
        "Path.mkdir",
        "Path.replace",
        "Path.chmod",
        "Path.copy",
        "Path.copy_into",
        "Path.move",
        "Path.move_into",
        "Path.lchmod",
    } <= filesystem_write_violations(text)


def test_direct_write_gate_treats_unproven_replace_as_path_mutation() -> None:
    text = """
target = request.kb_root / "target.md"
target.replace(request.kb_root / "replacement.md")
"""

    assert "Path.replace" in filesystem_write_violations(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('open("target", "w")', "builtins.open"),
        (
            "from builtins import open as acquire\n"
            "mode = choose_mode()\n"
            'acquire("target", mode)',
            "builtins.open",
        ),
        (
            "import io as streams\n"
            'streams.open("target", "a")',
            "io.open",
        ),
        (
            "from pathlib import Path as P\n"
            'P("target").open("r+")',
            "Path.open",
        ),
        (
            "from pathlib import Path\n"
            "mode = choose_mode()\n"
            'Path("target").open(mode=mode)',
            "Path.open",
        ),
        (
            "from pathlib import Path as P\n"
            'P.open(P("target"), "w")',
            "Path.open",
        ),
    ],
)
def test_direct_write_gate_rejects_write_capable_or_dynamic_open_modes(
    text: str,
    expected: str,
) -> None:
    assert expected in filesystem_write_violations(text)


def test_direct_write_gate_detects_low_level_and_shutil_mutators() -> None:
    text = """
import os as operating
from os import remove as erase
import shutil as transfers
from shutil import move as relocate

operating.open("target", flags)
operating.rename("before", "after")
operating.pwrite(fd, content, offset)
operating.pwritev(fd, buffers, offset)
operating.writev(fd, buffers)
operating.sendfile(out_fd, in_fd, offset, count)
operating.copy_file_range(in_fd, out_fd, count)
operating.ftruncate(fd, length)
erase("target")
transfers.copy2("source", "target")
transfers.copyfileobj(source_stream, target_stream)
relocate("source", "target")
"""

    assert {
        "os.open",
        "os.rename",
        "os.pwrite",
        "os.pwritev",
        "os.writev",
        "os.sendfile",
        "os.copy_file_range",
        "os.ftruncate",
        "os.remove",
        "shutil.copy2",
        "shutil.copyfileobj",
        "shutil.move",
    } <= filesystem_write_violations(text)


def test_direct_write_gate_preserves_dangerous_aliases_after_reassignment() -> None:
    text = """
import os
from pathlib import Path

erase = os.remove
erase("target")
erase = domain.harmless
persist = Path.write_text
persist(Path("target"), "content")
persist = domain.harmless
"""

    assert {
        "os.remove",
        "Path.write_text",
    } <= filesystem_write_violations(text)


def test_direct_write_gate_preserves_dangerous_aliases_across_scope_reuse() -> None:
    text = """
import os
from pathlib import Path

def dangerous():
    operation = os.remove
    operation("target")

def also_dangerous():
    operation = Path.write_text
    operation(Path("target"), "content")

def harmless():
    operation = domain.harmless
    operation()
"""

    assert {
        "os.remove",
        "Path.write_text",
    } <= filesystem_write_violations(text)


def test_direct_write_gate_alias_cycles_terminate_and_retain_dangerous_edges() -> None:
    text = """
import os

erase = os.remove
wrapped = erase
erase = wrapped
wrapped = erase
wrapped("target")
"""

    assert "os.remove" in filesystem_write_violations(text)


def test_direct_write_gate_detects_file_object_mutation_calls() -> None:
    text = """
stream.write(content)
stream.writelines(lines)
stream.truncate(0)
"""

    assert {
        "file.write",
        "file.writelines",
        "file.truncate",
    } <= filesystem_write_violations(text)


def test_create_consumes_shared_write_pipeline() -> None:
    assert "kb.core.write_pipeline" in imported_modules(source(COMMAND_MODULES[0]))


def test_ingest_consumes_shared_write_pipeline() -> None:
    assert "kb.core.write_pipeline" in imported_modules(source(COMMAND_MODULES[1]))


def test_create_and_ingest_do_not_own_persistence_primitives() -> None:
    forbidden_names = HOUSEKEEPING_INDEXING_PERSISTENCE | RETIRED_ORCHESTRATION_HELPERS
    for path in COMMAND_MODULES:
        text = source(path)
        assert not safeio_import_dependencies(text)
        assert not wildcard_imports(text)
        assert not (imported_names(text) & forbidden_names)
        assert not (directly_called_names(text) & forbidden_names)
        assert not (set(function_definitions(text)) & forbidden_names)
        assert not write_pipeline_import_violations(
            text,
            WRITE_PIPELINE_IMPORT_ALLOWLISTS[path],
        )
        assert not filesystem_write_violations(text)


def test_slug_has_one_definition_and_both_commands_import_it() -> None:
    definitions = [
        path.as_posix()
        for path in sorted(Path("src/kb/core").glob("*.py"))
        for name in function_definitions(path.read_text(encoding="utf-8"))
        if name == "slug"
    ]

    assert definitions == ["src/kb/core/naming.py"]
    for path in COMMAND_MODULES:
        assert "kb.core.naming.slug" in qualified_called_names(source(path))
