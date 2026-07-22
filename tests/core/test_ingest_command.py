from pathlib import Path

import pytest

from kb.core.ingest import (
    AdapterPayload,
    IngestFailure,
    IngestRequest,
    IngestSourceShape,
    execute_ingest,
    prepare_ingest,
)
from kb.core.model import RawClass


def request(root: Path) -> IngestRequest:
    return IngestRequest(raw_class=RawClass.CHAT, kb_root=root)


def test_prepare_then_execute_accepts_explicit_payload(initialized_kb: Path) -> None:
    prepared = prepare_ingest(
        request(initialized_kb),
        IngestSourceShape(source_kind="stdin", locator_present=False),
    )
    result = execute_ingest(
        prepared,
        AdapterPayload(
            source_kind="stdin",
            data=b"chat\r\n",
            default_origin="stdin",
        ),
    )
    assert result.id == "CHAT-000001"
    assert (initialized_kb / result.path).read_bytes().endswith(b"---\nchat\n")


@pytest.mark.parametrize(
    ("source_kind", "locator_present", "message"),
    [
        ("file", False, "SOURCE is required with --from file"),
        ("stdin", True, "SOURCE is forbidden with --from stdin"),
        ("clipboard", True, "SOURCE is forbidden with --from clipboard"),
    ],
)
def test_prepare_validates_source_shape_before_acquisition(
    initialized_kb: Path,
    source_kind: str,
    locator_present: bool,
    message: str,
) -> None:
    with pytest.raises(IngestFailure) as raised:
        prepare_ingest(
            request(initialized_kb),
            IngestSourceShape(
                source_kind=source_kind,
                locator_present=locator_present,
            ),
        )
    assert (raised.value.code, raised.value.message, raised.value.exit_code) == (
        "E_INGEST_USAGE",
        message,
        2,
    )


def test_execute_rejects_payload_for_another_prepared_source(
    initialized_kb: Path,
) -> None:
    prepared = prepare_ingest(
        request(initialized_kb),
        IngestSourceShape(source_kind="stdin", locator_present=False),
    )
    with pytest.raises(ValueError, match="payload source kind does not match prepared ingest"):
        execute_ingest(
            prepared,
            AdapterPayload(
                source_kind="clipboard",
                data=b"chat\n",
                default_origin="clipboard",
            ),
        )
