from __future__ import annotations

import re
import unicodedata


def slug(value: str, fallback: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode()
    candidate = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return candidate or fallback.lower()
