from __future__ import annotations

import os

from .config import TranslationConfig
from .models import Item
from .net import HttpClient


class TranslationError(Exception):
    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("\n".join(failures))


def _item_source_text(item: Item) -> str:
    return (item.summary or item.title or "").strip()


def _needs_translation(item: Item) -> bool:
    return bool(_item_source_text(item))


def _format_metrics(item: Item) -> str:
    parts: list[str] = []
    if item.language:
        parts.append(f"language={item.language}")
    if item.metrics.get("trend_rank"):
        parts.append(f"trend_rank={int(item.metrics['trend_rank'])}")
    if item.metrics.get("stars"):
        parts.append(f"stars={int(item.metrics['stars'])}")
    if item.metrics.get("stars_today"):
        parts.append(f"stars_today=+{int(item.metrics['stars_today'])}")
    if item.metrics.get("forks"):
        parts.append(f"forks={int(item.metrics['forks'])}")
    if item.tags:
        parts.append("tags=" + ",".join(item.tags[:6]))
    return "; ".join(parts)


def _is_github_item(item: Item) -> bool:
    return item.source_id.startswith("github") or "github.com/" in item.url


class Translator:
    def translate_items(self, items: list[Item]) -> list[Item]:
        return items


class NoopTranslator(Translator):
    pass


class LibreTranslateTranslator(Translator):
    def __init__(self, config: TranslationConfig, client: HttpClient):
        self.config = config
        self.client = client

    def translate_items(self, items: list[Item]) -> list[Item]:
        if not self.config.libretranslate_url:
            return items
        api_key = os.environ.get(self.config.libretranslate_api_key_env, "")
        endpoint = self.config.libretranslate_url.rstrip("/") + "/translate"
        failures: list[str] = []
        for item in items:
            text = _item_source_text(item)
            if not text:
                continue
            payload = {
                "q": text[:2500],
                "source": "auto",
                "target": self.config.target_language,
                "format": "text",
            }
            if api_key:
                payload["api_key"] = api_key
            try:
                result = self.client.post_json(endpoint, payload)
                item.translation = str(result.get("translatedText") or "").strip()
                if not item.translation:
                    failures.append(f"{item.title}: empty translation")
            except Exception as exc:
                failures.append(f"{item.title}: {exc}")
        if failures:
            raise TranslationError(failures)
        return items


class OpenAICompatibleTranslator(Translator):
    def __init__(self, config: TranslationConfig, client: HttpClient):
        self.config = config
        self.client = client

    def translate_items(self, items: list[Item]) -> list[Item]:
        api_key = os.environ.get(self.config.openai_api_key_env, "")
        if not api_key:
            missing = [item.title for item in items if _needs_translation(item)]
            if missing:
                raise TranslationError(
                    [f"{title}: missing {self.config.openai_api_key_env}" for title in missing]
                )
            return items
        endpoint = self.config.openai_base_url.rstrip("/") + "/chat/completions"
        failures: list[str] = []
        for item in items:
            text = _item_source_text(item)
            if not text:
                continue
            if _is_github_item(item):
                prompt = (
                    "请为下面的 GitHub 项目生成中文整理，面向每天阅读开源趋势的技术用户。"
                    "输出 2-3 句中文，不要编造 README 中没有的信息，不要营销腔。"
                    "请包含：1. 这个项目是什么；2. 可能适合谁或什么场景；"
                    "3. 如果趋势数据明显，说明为什么值得关注。\n\n"
                    f"项目：{item.title}\n"
                    f"链接：{item.url}\n"
                    f"作者/组织：{item.author}\n"
                    f"指标：{_format_metrics(item)}\n"
                    f"原始描述：{text[:3000]}"
                )
                system_prompt = "你是严谨的开源项目研究员，擅长用中文解释项目价值。"
            else:
                prompt = (
                    "请把下面的信息翻译成简洁中文，并保留关键事实。"
                    "如果原文已经是中文，请整理成一句中文摘要。\n\n"
                    f"标题：{item.title}\n正文：{text[:3000]}"
                )
                system_prompt = "你是严谨的新闻翻译编辑。"
            payload = {
                "model": self.config.openai_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
            try:
                result = self.client.post_json(
                    endpoint,
                    payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                choices = result.get("choices") or []
                if choices:
                    item.translation = (
                        choices[0].get("message", {}).get("content", "").strip()
                    )
                if not item.translation:
                    failures.append(f"{item.title}: empty translation")
            except Exception as exc:
                failures.append(f"{item.title}: {exc}")
        if failures:
            raise TranslationError(failures)
        return items


def build_translator(config: TranslationConfig, client: HttpClient) -> Translator:
    provider = config.provider.lower().strip()
    if provider == "libretranslate":
        return LibreTranslateTranslator(config, client)
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleTranslator(config, client)
    return NoopTranslator()
