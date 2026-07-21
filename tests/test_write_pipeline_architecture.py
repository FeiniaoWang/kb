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


def imported_symbols(text: str) -> set[tuple[str, str]]:
    return {
        (node.module, alias.name)
        for node in ast.walk(parsed(text))
        if isinstance(node, ast.ImportFrom) and node.module is not None
        for alias in node.names
    }


def directly_called_names(text: str) -> set[str]:
    tree = parsed(text)
    aliases = {
        alias.asname: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.asname is not None
    }
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(aliases.get(node.func.id, node.func.id))
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


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


def test_create_consumes_shared_write_pipeline() -> None:
    assert "kb.core.write_pipeline" in imported_modules(source(COMMAND_MODULES[0]))


def test_ingest_consumes_shared_write_pipeline() -> None:
    assert "kb.core.write_pipeline" in imported_modules(source(COMMAND_MODULES[1]))


def test_create_and_ingest_do_not_own_persistence_primitives() -> None:
    forbidden_names = PERSISTENCE_PRIMITIVES | RETIRED_ORCHESTRATION_HELPERS
    for path in COMMAND_MODULES:
        text = source(path)
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
        assert ("kb.core.naming", "slug") in imported_symbols(source(path))
