import ast
from pathlib import Path


COMMAND_MODULES = ("src/kb/core/create.py", "src/kb/core/ingest.py")
PERSISTENCE_PRIMITIVES = {
    "append_log",
    "append_rooted_bytes",
    "create_directory_index",
    "create_file_bytes",
    "create_rooted_directory",
    "create_rooted_file_bytes",
    "inspect_mutable_file",
    "inspect_rooted_file",
    "overwrite_mutable_bytes",
    "overwrite_rooted_bytes",
    "regenerate_directory_index",
}
RETIRED_ORCHESTRATION_HELPERS = {"_new_directories", "_new_index_contents"}


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


def _simple_callable_bindings(tree: ast.Module) -> dict[str, str]:
    bindings = {
        alias.asname: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.asname is not None
    }
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
                bindings[target.id] = referenced_name
    return bindings


def _resolved_name(name: str, bindings: dict[str, str]) -> str:
    seen: set[str] = set()
    while name in bindings and name not in seen:
        seen.add(name)
        name = bindings[name]
    return name


def directly_called_names(text: str) -> set[str]:
    tree = parsed(text)
    bindings = _simple_callable_bindings(tree)
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(_resolved_name(node.func.id, bindings))
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


def test_ast_names_follow_module_attribute_callable_rebinding() -> None:
    text = """
import kb.core.safeio as safeio

birth = safeio.create_rooted_file_bytes
wrapped_birth = birth
wrapped_birth(root, path, content, identity)
"""

    assert "create_rooted_file_bytes" in directly_called_names(text)


def test_qualified_calls_accept_module_style_imports() -> None:
    text = """
import kb.core.naming as naming

naming.slug("Title", "fallback")
"""

    assert "kb.core.naming.slug" in qualified_called_names(text)


def test_create_consumes_shared_write_pipeline() -> None:
    assert "kb.core.write_pipeline" in imported_modules(source(COMMAND_MODULES[0]))


def test_ingest_consumes_shared_write_pipeline() -> None:
    assert "kb.core.write_pipeline" in imported_modules(source(COMMAND_MODULES[1]))


def test_create_and_ingest_do_not_own_persistence_primitives() -> None:
    forbidden_names = PERSISTENCE_PRIMITIVES | RETIRED_ORCHESTRATION_HELPERS
    for path in COMMAND_MODULES:
        text = source(path)
        assert not wildcard_imports(text)
        assert not (imported_names(text) & forbidden_names)
        assert not (directly_called_names(text) & forbidden_names)
        assert not (set(function_definitions(text)) & forbidden_names)


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
