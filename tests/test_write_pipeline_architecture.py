from pathlib import Path


def source(relative: str) -> str:
    return Path(relative).read_text(encoding="utf-8")


def test_create_consumes_shared_write_pipeline() -> None:
    text = source("src/kb/core/create.py")
    assert "from kb.core.write_pipeline import" in text
    for forbidden in (
        "create_file_bytes(",
        "overwrite_mutable_bytes(",
        "append_log(",
        "regenerate_directory_index(",
        "def _new_index_contents(",
    ):
        assert forbidden not in text
