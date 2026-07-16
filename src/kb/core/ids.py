from __future__ import annotations

import re
from functools import total_ordering
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

NUMERIC_ID_PATTERN = re.compile(r"^(?P<prefix>[A-Z]+)-(?P<number>[0-9]{6,})$")


@total_ordering
class DocId(BaseModel):
    model_config = ConfigDict(frozen=True)

    prefix: str = Field(pattern=r"^[A-Z]+$")
    number: int = Field(ge=0)

    @classmethod
    def parse(cls, value: str) -> DocId:
        match = NUMERIC_ID_PATTERN.fullmatch(value)
        if match is None:
            raise ValueError(f"not a numeric document id: {value}")
        return cls(prefix=match.group("prefix"), number=int(match.group("number")))

    def format(self) -> str:
        return f"{self.prefix}-{self.number:06d}"

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, DocId):
            return NotImplemented
        return (self.prefix, self.number) < (other.prefix, other.number)
