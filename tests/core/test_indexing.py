from kb.core.housekeeping import init_kb
from kb.core.indexing import (
    file_listing_line,
    regenerate_directory_index,
    render_index,
    subdirectory_listing_line,
)


def test_listing_line_helpers_match_directory_listing_grammar() -> None:
    assert file_listing_line(
        "retry.md", "KB-000001", "Retry Policy", "Retry rules."
    ) == "* [KB-000001][Retry Policy](retry.md) - Retry rules."
    assert file_listing_line("notes.md", None, "Notes", None) == "* [Notes](notes.md)"
    assert subdirectory_listing_line(
        "specs", "Documents under synthetic/specs/."
    ) == "* [specs](specs/index.md) - Documents under synthetic/specs/."


def test_render_index_remains_byte_identical_to_init_template(tmp_path) -> None:
    result = init_kb(tmp_path)
    assert result.root == tmp_path.resolve()
    assert (tmp_path / "raw/sources/index.md").read_text(
        encoding="utf-8"
    ) == render_index("Sources", "Normalized external evidence (immutable).")


def test_regeneration_preserves_existing_frontmatter_and_heading(tmp_path) -> None:
    init_kb(tmp_path)
    index = tmp_path / "raw/sources/index.md"
    before_frontmatter = index.read_text(encoding="utf-8").split("---", 2)[1]
    (tmp_path / "raw/sources/a.md").write_text(
        "---\nid: RAW-000001\ntype: raw-source\ntitle: A\n---\nbody\n",
        encoding="utf-8",
    )
    regenerated = regenerate_directory_index(tmp_path, index.parent)
    assert regenerated.split("---", 2)[1] == before_frontmatter
    assert "# Sources" in regenerated
    assert "* [RAW-000001][A](a.md)" in regenerated


def test_regeneration_ignores_frontmatter_comments_when_preserving_heading(
    tmp_path,
) -> None:
    init_kb(tmp_path)
    index = tmp_path / "raw/sources/index.md"
    original = index.read_text(encoding="utf-8")
    index.write_text(
        original.replace("type: index\n", "type: index\n# metadata note\n"),
        encoding="utf-8",
    )

    regenerated = regenerate_directory_index(tmp_path, index.parent)
    body = regenerated.split("---", 2)[2]

    assert body.startswith("\n# Sources\n")
    assert "\n# metadata note\n" not in body


def test_regeneration_keeps_subdirectory_heading_and_directory_link_distinct(
    tmp_path,
) -> None:
    init_kb(tmp_path)

    regenerated = regenerate_directory_index(tmp_path, tmp_path)

    assert "* [Governance](governance/index.md)" in regenerated


def test_regeneration_uses_identity_checked_source_and_merges_planned_file(
    tmp_path,
) -> None:
    init_kb(tmp_path)
    directory = tmp_path / "synthetic"
    index = directory / "index.md"
    source = index.read_bytes()
    index.write_text("not the prepared source\n", encoding="utf-8")

    rendered = regenerate_directory_index(
        tmp_path,
        directory,
        source=source,
        planned_files={
            "planned.md": "* [KB-000001][Planned](planned.md) - Planned."
        },
    )

    assert rendered.startswith("---\ntype: index\n")
    assert "not the prepared source" not in rendered
    assert "* [KB-000001][Planned](planned.md) - Planned." in rendered


def test_projected_entries_merge_by_path_key_not_rendered_label(tmp_path) -> None:
    init_kb(tmp_path)
    directory = tmp_path / "synthetic"
    (directory / "zulu.md").write_text(
        "---\nid: KB-000009\ntype: spec\ntitle: A First Label\n"
        "description: Existing.\n---\n",
        encoding="utf-8",
    )

    rendered = regenerate_directory_index(
        tmp_path,
        directory,
        planned_files={
            "alpha.md": "* [KB-000010][Z Last Label](alpha.md) - Planned."
        },
    )

    assert rendered.index("(alpha.md)") < rendered.index("(zulu.md)")
