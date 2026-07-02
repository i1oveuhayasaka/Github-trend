from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo


def china_today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def is_china_workday(day: date) -> bool:
    try:
        from chinese_calendar import is_workday
    except ImportError as exc:
        raise RuntimeError(
            "chinese-calendar is required; install the project dependencies"
        ) from exc
    return bool(is_workday(day))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether a date is a statutory workday in China."
    )
    parser.add_argument(
        "--date",
        help="Date in YYYY-MM-DD format. Defaults to today in Asia/Shanghai.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        day = date.fromisoformat(args.date) if args.date else china_today()
        workday = is_china_workday(day)
    except (RuntimeError, ValueError, NotImplementedError) as exc:
        print(f"China workday check failed: {exc}", file=sys.stderr)
        return 2

    if workday:
        print(f"{day.isoformat()} is a statutory workday in China.")
        return 0
    print(f"{day.isoformat()} is not a statutory workday in China; skipping digest.")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
