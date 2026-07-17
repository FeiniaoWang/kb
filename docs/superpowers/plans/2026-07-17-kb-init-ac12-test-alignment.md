# KB Init AC12 Test Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the one-to-one `kb init` AC12 acceptance test explicitly prove all twelve manifest entries are created while unrelated files and directories remain untouched.

**Architecture:** Keep this as a CLI acceptance-test-only alignment because the revised AC12 changes command ownership language, not `kb init` behavior. Exercise the real Typer command through the existing `invoke_init` fixture, assert the complete filesystem and output contract, and change `src/kb/core/housekeeping.py` only if the stronger test exposes a production defect.

**Tech Stack:** Python 3.14, pytest, Typer `CliRunner`, `uv`

## Global Constraints

- Implementation context is exactly `docs/specs/commands/00-shared.md` plus `docs/specs/commands/kb-init.md`.
- One acceptance criterion maps to one test named `test_ac<NN>_<slug>`.
- `kb init` writes only its twelve-entry manifest and never adds `index.md` to a foreign directory.
- Core logic remains free of Typer, printing, and `sys.exit`.
- Dependencies remain `typer`, `PyYAML`, and `pydantic` 2.x only.

---

### Task 1: Strengthen AC12 acceptance coverage

**Files:**
- Modify: `tests/cli/test_init.py:209`
- Modify only if the stronger test fails: `src/kb/core/housekeeping.py:358`

**Interfaces:**
- Consumes: `invoke_init(root: Path, *args: str)` and `expected_manifest(timestamp: str) -> dict[str, str]` from the existing pytest fixtures/helpers.
- Produces: `test_ac12_foreign_content_is_untouched`, a complete acceptance test for the revised AC12.

- [x] **Step 1: Preserve the pre-change diagnostic result**

Run:

```bash
uv run pytest tests/cli/test_init.py::test_ac12_foreign_content_is_untouched -vv
```

Expected: PASS, establishing that the currently asserted foreign-content behavior already exists.

- [x] **Step 2: Strengthen the AC12 test**

Replace the existing test with:

```python
def test_ac12_foreign_content_is_untouched(tmp_path, invoke_init) -> None:
    notes = tmp_path / "notes.txt"
    notes_content = b"private notes\x00"
    notes.write_bytes(notes_content)
    misc = tmp_path / "misc"
    misc.mkdir()
    foreign = misc / "data.bin"
    foreign_content = b"foreign\xff"
    foreign.write_bytes(foreign_content)

    result = invoke_init(tmp_path)

    manifest_paths = sorted(expected_manifest("unused"))
    expected_lines = [f"created  {path}" for path in manifest_paths]
    expected_lines.append(
        f"KB ready at {tmp_path.resolve()} — 12 created, 0 overwritten, 0 skipped"
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == expected_lines
    assert files_under(tmp_path) == set(manifest_paths) | {
        "notes.txt",
        "misc/data.bin",
    }
    assert notes.read_bytes() == notes_content
    assert foreign.read_bytes() == foreign_content
    assert not (misc / "index.md").exists()
```

- [x] **Step 3: Run the strengthened test**

Run:

```bash
uv run pytest tests/cli/test_init.py::test_ac12_foreign_content_is_untouched -vv
```

Expected: PASS because the implementation already limits writes to the manifest. If it fails for an AC12 behavior, retain the failure as RED and minimally correct `init_kb` before rerunning it to GREEN.

- [x] **Step 4: Run the complete init acceptance suite**

Run:

```bash
uv run pytest tests/cli/test_init.py -q
```

Expected: all init acceptance tests PASS.

- [x] **Step 5: Run the full regression suite**

Run:

```bash
uv run pytest -q
```

Expected: all tests PASS with no new warnings or errors.

- [x] **Step 6: Review the final diff**

Run:

```bash
git diff --check
git diff -- tests/cli/test_init.py src/kb/core/housekeeping.py docs/superpowers/plans/2026-07-17-kb-init-ac12-test-alignment.md
```

Expected: only the AC12 test and this implementation plan changed; production code remains unchanged unless Step 3 exposed an actual defect.
