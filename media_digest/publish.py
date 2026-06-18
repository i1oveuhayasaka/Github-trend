from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import SocialConfig, env_setting
from .net import HttpClient


@dataclass(slots=True)
class PublishResult:
    platform: str
    ok: bool
    message: str


def parse_xiaohongshu_draft(draft: str) -> tuple[str, str]:
    text = draft.strip()
    lines = text.splitlines()
    title = (lines[0] if lines else "每日资讯").strip()[:20]
    return title, text


def publish_xiaohongshu_webhook(
    client: HttpClient,
    config: SocialConfig,
    draft_path: Path,
    draft: str,
    digest_title: str,
) -> PublishResult:
    url = os.environ.get(config.webhook_url_env, "").strip()
    if not url:
        return PublishResult("xiaohongshu", False, f"missing {config.webhook_url_env}")

    title, content = parse_xiaohongshu_draft(draft)
    payload = {
        "platform": "xiaohongshu",
        "digest_title": digest_title,
        "title": title,
        "content": content,
        "hashtags": config.hashtags,
        "draft_path": str(draft_path),
    }
    try:
        client.post_json(url, payload)
        return PublishResult("xiaohongshu", True, "sent")
    except Exception as exc:
        return PublishResult("xiaohongshu", False, str(exc))


def publish_xiaohongshu_script(
    config: SocialConfig,
    draft_path: Path,
    draft: str,
    digest_title: str,
    project_dir: Path,
) -> PublishResult:
    script = Path(config.publish_script)
    if not script.is_absolute():
        script = project_dir / script
    if not script.exists():
        return PublishResult("xiaohongshu", False, f"script not found: {script}")

    title, content = parse_xiaohongshu_draft(draft)
    env = os.environ.copy()
    env.update(
        {
            "XHS_DRAFT_PATH": str(draft_path),
            "XHS_DRAFT_TITLE": title,
            "XHS_DRAFT_CONTENT": content,
            "XHS_DIGEST_TITLE": digest_title,
            "XHS_BROWSER_PROFILE_DIR": str(project_dir / config.browser_profile_dir),
            "XHS_BROWSER_HEADLESS": "1" if config.browser_headless else "0",
        }
    )
    command = [sys.executable, str(script), str(draft_path)]
    try:
        completed = subprocess.run(
            command,
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=config.publish_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PublishResult("xiaohongshu", False, "publish script timed out")

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return PublishResult(
            "xiaohongshu",
            False,
            detail or f"script exited with code {completed.returncode}",
        )
    message = (completed.stdout or "published").strip().splitlines()[-1]
    return PublishResult("xiaohongshu", True, message)


def publish_xiaohongshu(
    client: HttpClient,
    config: SocialConfig,
    draft_path: Path,
    draft: str,
    digest_title: str,
    project_dir: Path,
    dry_run: bool,
) -> PublishResult:
    if dry_run:
        return PublishResult("xiaohongshu", True, "dry-run skipped publish")

    provider = config.publish_provider.lower().strip()
    if provider == "webhook":
        return publish_xiaohongshu_webhook(client, config, draft_path, draft, digest_title)
    if provider in {"script", "playwright"}:
        return publish_xiaohongshu_script(
            config,
            draft_path,
            draft,
            digest_title,
            project_dir,
        )
    return PublishResult("xiaohongshu", False, f"unknown publish provider: {provider}")
