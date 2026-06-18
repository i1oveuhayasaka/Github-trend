from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from dataclasses import dataclass

from .config import PushTarget, env_setting
from .net import HttpClient


@dataclass(slots=True)
class PushResult:
    target: str
    ok: bool
    message: str


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    text = text.replace("sctapi.ftqq.com/", "sctapi.ftqq.com/<redacted>")
    text = text.replace("oapi.dingtalk.com/robot/send?access_token=", "oapi.dingtalk.com/robot/send?access_token=<redacted>")
    return text


def _split_markdown(text: str, limit: int = 3600) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in text.split("\n## "):
        if block and not block.startswith("#"):
            block = "## " + block
        if current_len + len(block) + 2 > limit and current:
            chunks.append("\n".join(current).strip())
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += len(block) + 2
    if current:
        chunks.append("\n".join(current).strip())
    return chunks


def _sign_dingtalk(webhook: str, secret: str) -> str:
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    secret_bytes = secret.encode("utf-8")
    sign = urllib.parse.quote_plus(
        base64.b64encode(hmac.new(secret_bytes, string_to_sign, hashlib.sha256).digest())
    )
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign}"


def push_dingtalk(client: HttpClient, target: PushTarget, title: str, markdown: str) -> PushResult:
    webhook = env_setting(target.settings, "webhook")
    secret = env_setting(target.settings, "secret")
    if not webhook:
        return PushResult("dingtalk", False, "missing webhook")
    try:
        for index, chunk in enumerate(_split_markdown(markdown), start=1):
            chunk_title = title if index == 1 else f"{title} ({index})"
            client.post_json(
                _sign_dingtalk(webhook, secret),
                {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": chunk_title,
                        "text": chunk,
                    },
                },
            )
        return PushResult("dingtalk", True, "sent")
    except Exception as exc:
        return PushResult("dingtalk", False, _safe_error(exc))


def push_bark(client: HttpClient, target: PushTarget, title: str, markdown: str) -> PushResult:
    server = str(target.settings.get("server", "https://api.day.app")).rstrip("/")
    key = env_setting(target.settings, "key")
    if not key:
        return PushResult("bark", False, "missing key")
    payload = {
        "title": title,
        "body": markdown[:3500],
        "group": str(target.settings.get("group", "media-digest")),
    }
    try:
        client.post_json(f"{server}/{key}", payload)
        return PushResult("bark", True, "sent")
    except Exception as exc:
        return PushResult("bark", False, _safe_error(exc))


def push_serverchan(client: HttpClient, target: PushTarget, title: str, markdown: str) -> PushResult:
    sendkey = env_setting(target.settings, "sendkey")
    if not sendkey:
        return PushResult("serverchan", False, "missing sendkey")
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    try:
        client.post_form(url, {"title": title, "desp": markdown})
        return PushResult("serverchan", True, "sent")
    except Exception as exc:
        return PushResult("serverchan", False, _safe_error(exc))


def push_generic_webhook(
    client: HttpClient,
    target_name: str,
    target: PushTarget,
    title: str,
    markdown: str,
) -> PushResult:
    url = env_setting(target.settings, "url")
    if not url:
        return PushResult(target_name, False, "missing url")
    try:
        client.post_json(url, {"title": title, "markdown": markdown})
        return PushResult(target_name, True, "sent")
    except Exception as exc:
        return PushResult(target_name, False, _safe_error(exc))


def push_all(
    client: HttpClient,
    targets: dict[str, PushTarget],
    title: str,
    markdown: str,
    dry_run: bool,
) -> list[PushResult]:
    results: list[PushResult] = []
    for name, target in targets.items():
        if not target.enabled:
            continue
        if dry_run:
            results.append(PushResult(name, True, "dry-run skipped send"))
            continue
        if name == "dingtalk":
            results.append(push_dingtalk(client, target, title, markdown))
        elif name == "bark":
            results.append(push_bark(client, target, title, markdown))
        elif name == "serverchan":
            results.append(push_serverchan(client, target, title, markdown))
        else:
            results.append(push_generic_webhook(client, name, target, title, markdown))
    return results
