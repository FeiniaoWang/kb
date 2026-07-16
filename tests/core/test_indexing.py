from kb.core.housekeeping import init_kb
from kb.core.indexing import regenerate_directory_index, render_index


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
