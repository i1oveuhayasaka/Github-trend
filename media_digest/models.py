from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass(slots=True)
class Item:
    source_id: str
    source_name: str
    title: str
    url: str
    published_at: datetime | None = None
    author: str = ""
    summary: str = ""
    content: str = ""
    language: str = ""
    tags: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    quality: float = 1.0
    raw: dict[str, Any] = field(default_factory=dict)
    translation: str = ""
    score: float = 0.0

    @property
    def stable_id(self) -> str:
        seed = self.url.strip() or f"{self.source_id}:{self.title}:{self.published_key}"
        return sha256(seed.encode("utf-8")).hexdigest()

    @property
    def published_key(self) -> str:
        if self.published_at is None:
            return ""
        return self.published_at.astimezone(timezone.utc).isoformat()
