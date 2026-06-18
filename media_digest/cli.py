from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import load_config
from .net import HttpClient
from .ranking import rank_items
from .render import (
    render_markdown,
    render_xiaohongshu_draft,
    update_github_archive,
    write_outputs,
)
from .publish import publish_xiaohongshu
from .sources import fetch_all_sources
from .store import DigestStore
from .timeutil import cutoff
from .translator import TranslationError, build_translator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect, rank, render and push media digest.")
    parser.add_argument("--config", default="config.example.toml", help="Path to config TOML.")
    parser.add_argument("--env-file", default=".env", help="Optional env file for push keys.")
    parser.add_argument("--dry-run", action="store_true", help="Render outputs without sending push.")
    parser.add_argument("--sample-only", action="store_true", help="Use only sample sources.")
    parser.add_argument("--include-seen", action="store_true", help="Do not filter items already sent.")
    parser.add_argument("--no-store", action="store_true", help="Do not update SQLite dedupe store.")
    parser.add_argument("--limit", type=int, default=None, help="Override max digest items.")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Only run one source id. Repeat to include multiple sources.",
    )
    return parser


def load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env_file(args.env_file)
    config = load_config(args.config)
    client = HttpClient(config.app.user_agent, config.app.timeout_seconds)
    source_configs = config.sources
    if args.source:
        selected = set(args.source)
        source_configs = [
            source for source in source_configs
            if str(source.get("id")) in selected
        ]
        missing = selected - {str(source.get("id")) for source in source_configs}
        if missing:
            print(f"Unknown source id(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    results = fetch_all_sources(source_configs, client, sample_only=args.sample_only)
    source_errors = [
        f"{result.source_id}: {result.error}"
        for result in results
        if not result.ok
    ]
    items = [item for result in results for item in result.items]
    if not items:
        print("No items collected.", file=sys.stderr)
        for error in source_errors:
            print(f"Source error: {error}", file=sys.stderr)
        return 2

    min_time = cutoff(config.app.lookback_hours)
    items = [
        item for item in items
        if item.published_at is None or item.published_at >= min_time
    ]

    store = None
    if not args.include_seen and not args.no_store:
        store = DigestStore(config.app.db_path)
        items = store.filter_unseen(items)
        if not items:
            store.close()
            print("No new items after dedupe.", file=sys.stderr)
            return 3

    max_items = args.limit or config.app.max_items
    ranked = rank_items(
        items,
        max_items=max_items,
        min_score=config.ranking.min_score,
        freshness_half_life_hours=config.ranking.freshness_half_life_hours,
    )
    translator = build_translator(config.translation, client)
    try:
        translated = translator.translate_items(ranked)
    except TranslationError as exc:
        print("Translation failed.", file=sys.stderr)
        for failure in exc.failures:
            print(f"  - {failure}", file=sys.stderr)
        if store:
            store.close()
        return 4

    digest = render_markdown(
        config.app.digest_title,
        translated,
        config.app.timezone,
        source_errors=source_errors,
    )

    xhs_draft = None
    xhs_config = config.social.get("xiaohongshu")
    if xhs_config and xhs_config.enabled:
        xhs_draft = render_xiaohongshu_draft(
            config.app.digest_title,
            translated[: xhs_config.max_items],
            xhs_config.hashtags,
        )

    paths = write_outputs(config.app.output_dir, digest, xhs_draft)
    print(f"Wrote digest: {paths['digest']}")
    if "xiaohongshu" in paths:
        print(f"Wrote xiaohongshu draft: {paths['xiaohongshu']}")

    publish_result = None
    if (
        xhs_config
        and xhs_config.enabled
        and xhs_config.publish_enabled
        and xhs_draft
        and "xiaohongshu" in paths
    ):
        publish_result = publish_xiaohongshu(
            client,
            xhs_config,
            paths["xiaohongshu"],
            xhs_draft,
            config.app.digest_title,
            Path(args.config).resolve().parent,
            dry_run=args.dry_run,
        )
        status = "ok" if publish_result.ok else "failed"
        print(f"Publish xiaohongshu: {status} - {publish_result.message}")

    github_items = [
        item for item in translated
        if item.source_id.startswith("github")
    ]
    if github_items:
        archive_path = update_github_archive(
            config.app.output_dir,
            github_items,
            config.app.timezone,
        )
        print(f"Wrote github archive: {archive_path}")

    push_results = __import__("media_digest.push", fromlist=["push_all"]).push_all(
        client,
        config.push,
        config.app.digest_title,
        digest,
        dry_run=args.dry_run,
    )
    for result in push_results:
        status = "ok" if result.ok else "failed"
        print(f"Push {result.target}: {status} - {result.message}")

    if store:
        try:
            enabled_push = any(target.enabled for target in config.push.values())
            push_succeeded = not enabled_push or any(result.ok for result in push_results)
            publish_required = bool(
                xhs_config
                and xhs_config.enabled
                and xhs_config.publish_enabled
            )
            publish_succeeded = (
                not publish_required
                or (publish_result is not None and publish_result.ok)
            )
            if not args.dry_run and push_succeeded and publish_succeeded:
                store.mark_seen(translated)
                print(f"Marked seen items: {len(translated)}")
            elif args.dry_run:
                print("Skipped marking seen items: dry-run")
            else:
                print("Skipped marking seen items: push or publish failed")
        finally:
            store.close()

    if publish_result is not None and not publish_result.ok:
        return 5
    return 0 if ranked else 3
