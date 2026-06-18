from __future__ import annotations

import email.utils
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None

    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass

    candidates = [
        text,
        text.replace("Z", "+00:00"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def format_local(dt: datetime | None, tz_name: str) -> str:
    if dt is None:
        return "时间未知"
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")


def cutoff(hours: int) -> datetime:
    return now_utc() - timedelta(hours=hours)


def date_placeholder(days_ago: int) -> str:
    return (now_utc() - timedelta(days=days_ago)).date().isoformat()
