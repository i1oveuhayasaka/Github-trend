from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AppConfig:
    digest_title: str = "每日信息简报"
    timezone: str = "Asia/Shanghai"
    lookback_hours: int = 36
    max_items: int = 25
    db_path: str = "data/digest.db"
    output_dir: str = "outputs"
    user_agent: str = "media-digest/0.1 (+https://github.com)"
    timeout_seconds: int = 20


@dataclass(slots=True)
class TranslationConfig:
    provider: str = "none"
    target_language: str = "zh"
    libretranslate_url: str = ""
    libretranslate_api_key_env: str = "LIBRETRANSLATE_API_KEY"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key_env: str = "OPENAI_API_KEY"
    openai_model: str = "gpt-4.1-mini"


@dataclass(slots=True)
class RankingConfig:
    freshness_half_life_hours: int = 36
    min_score: float = 0.0


@dataclass(slots=True)
class PushTarget:
    enabled: bool = False
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SocialConfig:
    enabled: bool = True
    max_items: int = 8
    hashtags: list[str] = field(default_factory=lambda: ["每日资讯", "科技新闻", "AI"])


@dataclass(slots=True)
class DigestConfig:
    app: AppConfig
    translation: TranslationConfig
    ranking: RankingConfig
    sources: list[dict[str, Any]]
    push: dict[str, PushTarget]
    social: dict[str, SocialConfig]


def load_config(path: str | Path) -> DigestConfig:
    config_path = Path(path)
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    app = AppConfig(**data.get("app", {}))
    translation = TranslationConfig(**data.get("translation", {}))
    ranking = RankingConfig(**data.get("ranking", {}))
    sources = data.get("sources", [])

    push_data = data.get("push", {})
    push = {
        name: PushTarget(enabled=bool(value.get("enabled", False)), settings=dict(value))
        for name, value in push_data.items()
        if isinstance(value, dict)
    }

    retired_social_keys = {
        "publish_enabled",
        "publish_provider",
        "webhook_url_env",
        "publish_script",
        "browser_profile_dir",
        "browser_headless",
        "publish_timeout_seconds",
    }
    social_data = data.get("social", {})
    social = {
        name: SocialConfig(
            **{
                key: setting
                for key, setting in value.items()
                if key not in retired_social_keys
            }
        )
        for name, value in social_data.items()
        if isinstance(value, dict)
    }

    return DigestConfig(
        app=app,
        translation=translation,
        ranking=ranking,
        sources=sources,
        push=push,
        social=social,
    )


def env_setting(settings: dict[str, Any], key: str, default: str = "") -> str:
    direct = settings.get(key)
    if isinstance(direct, str) and direct:
        return direct
    env_key = settings.get(f"{key}_env")
    if isinstance(env_key, str) and env_key:
        return os.environ.get(env_key, default)
    return default
