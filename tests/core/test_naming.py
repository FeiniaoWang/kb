import pytest

from kb.core.naming import slug


@pytest.mark.parametrize(
    ("value", "fallback", "expected"),
    [
        ("Webhook Retry Policy", "KB-000001", "webhook-retry-policy"),
        ("Résumé / Über", "KB-000002", "resume-uber"),
        ("___", "RAW-000003", "raw-000003"),
        ("Already--Spaced", "KB-000004", "already-spaced"),
    ],
)
def test_slug_is_ascii_deterministic_and_uses_lowercase_fallback(
    value: str,
    fallback: str,
    expected: str,
) -> None:
    assert slug(value, fallback) == expected
