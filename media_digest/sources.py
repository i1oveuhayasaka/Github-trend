from __future__ import annotations

import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import Item
from .net import HttpClient
from .timeutil import date_placeholder, parse_datetime


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _child_text(element: ET.Element, names: Iterable[str]) -> str:
    wanted = set(names)
    for child in list(element):
        if child.tag.split("}")[-1] in wanted and child.text:
            return _clean_text(child.text)
    return ""


def _link_from_entry(entry: ET.Element) -> str:
    for child in list(entry):
        name = child.tag.split("}")[-1]
        if name == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text:
                return child.text.strip()
    return ""


def _apply_placeholders(value: str) -> str:
    text = value
    for days in range(1, 61):
        text = text.replace(f"{{date_{days}d}}", date_placeholder(days))
    text = text.replace("{today}", date_placeholder(0))
    return text


def _parse_int(text: str | None) -> float:
    if not text:
        return 0.0
    match = re.search(r"[\d,]+", _clean_text(text))
    if not match:
        return 0.0
    return float(match.group(0).replace(",", ""))


@dataclass(slots=True)
class SourceResult:
    source_id: str
    ok: bool
    items: list[Item]
    error: str = ""


class Source:
    def __init__(self, config: dict[str, Any], client: HttpClient):
        self.config = config
        self.client = client
        self.source_id = str(config["id"])
        self.name = str(config.get("name") or self.source_id)
        self.quality = float(config.get("quality", 1.0))
        self.tags = list(config.get("tags", []))
        self.max_items = int(config.get("max_items", 30))

    def fetch(self) -> list[Item]:
        raise NotImplementedError

    def enrich(self, item: Item) -> Item:
        item.quality = self.quality
        item.tags = sorted(set([*item.tags, *self.tags]))
        return item


class RSSSource(Source):
    def fetch(self) -> list[Item]:
        url = _apply_placeholders(str(self.config["url"]))
        xml = self.client.fetch_text(url)
        root = ET.fromstring(xml)
        entries = root.findall(".//item")
        if not entries:
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        if not entries:
            entries = [
                child for child in root.iter()
                if child.tag.split("}")[-1] in {"item", "entry"}
            ]

        items: list[Item] = []
        for entry in entries[: self.max_items]:
            title = _child_text(entry, ["title"])
            link = _child_text(entry, ["link"]) or _link_from_entry(entry)
            summary = _child_text(entry, ["description", "summary", "content", "encoded"])
            metrics: dict[str, float] = {}
            points_match = re.search(r"Points:\s*(\d+)", summary)
            comments_match = re.search(r"#\s*Comments:\s*(\d+)", summary)
            if points_match:
                metrics["points"] = float(points_match.group(1))
            if comments_match:
                metrics["comments"] = float(comments_match.group(1))
            if "Comments URL:" in summary and (points_match or comments_match):
                points = points_match.group(1) if points_match else "0"
                comments = comments_match.group(1) if comments_match else "0"
                summary = f"Hacker News 热门讨论：{points} points，{comments} comments。"
            published = parse_datetime(
                _child_text(entry, ["pubDate", "published", "updated", "dc:date"])
            )
            author = _child_text(entry, ["author", "creator"])
            if title and link:
                items.append(
                    self.enrich(
                        Item(
                            source_id=self.source_id,
                            source_name=self.name,
                            title=title,
                            url=link,
                            published_at=published,
                            author=author,
                            summary=summary,
                            metrics=metrics,
                        )
                    )
                )
        return items


class GitHubSearchSource(Source):
    def fetch(self) -> list[Item]:
        query = _apply_placeholders(str(self.config["query"]))
        sort = str(self.config.get("sort", "stars"))
        order = str(self.config.get("order", "desc"))
        per_page = min(int(self.config.get("per_page", self.max_items)), 100)
        params = urllib.parse.urlencode(
            {"q": query, "sort": sort, "order": order, "per_page": per_page}
        )
        url = f"https://api.github.com/search/repositories?{params}"
        data = self.client.fetch_json(
            url,
            headers={"Accept": "application/vnd.github+json"},
        )
        items: list[Item] = []
        for repo in data.get("items", [])[: self.max_items]:
            owner = repo.get("owner") or {}
            title = repo.get("full_name") or repo.get("name") or ""
            homepage = repo.get("html_url") or ""
            description = repo.get("description") or ""
            published = parse_datetime(repo.get("created_at")) or parse_datetime(repo.get("updated_at"))
            topics = repo.get("topics") if isinstance(repo.get("topics"), list) else []
            metrics = {
                "stars": float(repo.get("stargazers_count") or 0),
                "forks": float(repo.get("forks_count") or 0),
                "watchers": float(repo.get("watchers_count") or 0),
            }
            if title and homepage:
                items.append(
                    self.enrich(
                        Item(
                            source_id=self.source_id,
                            source_name=self.name,
                            title=title,
                            url=homepage,
                            published_at=published,
                            author=owner.get("login") or "",
                            summary=description,
                            language=repo.get("language") or "",
                            tags=[str(topic) for topic in topics[:6]],
                            metrics=metrics,
                            raw={"license": (repo.get("license") or {}).get("spdx_id")},
                        )
                    )
                )
        return items


class GitHubTrendingSource(Source):
    def fetch(self) -> list[Item]:
        since = str(self.config.get("since", "daily"))
        language = str(self.config.get("language", "")).strip().lower()
        spoken_language = str(self.config.get("spoken_language_code", "")).strip()
        path = f"/trending/{urllib.parse.quote(language)}" if language else "/trending"
        params = {"since": since}
        if spoken_language:
            params["spoken_language_code"] = spoken_language
        url = f"https://github.com{path}?{urllib.parse.urlencode(params)}"

        page = self.client.fetch_text(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://github.com/trending",
            },
        )
        blocks = re.findall(
            r"<article\b[^>]*class=\"[^\"]*Box-row[^\"]*\"[^>]*>(.*?)</article>",
            page,
            flags=re.DOTALL,
        )
        items: list[Item] = []
        now = datetime.now(timezone.utc)
        for trend_rank, block in enumerate(blocks[: self.max_items], start=1):
            repo_match = re.search(
                r"<h2\b.*?<a\b[^>]*href=\"/([^\"]+)\"[^>]*>(.*?)</a>",
                block,
                flags=re.DOTALL,
            )
            if not repo_match:
                continue
            repo_path = repo_match.group(1).strip("/")
            title = _clean_text(repo_match.group(2))
            title = re.sub(r"\s*/\s*", "/", title).strip()
            if not title or "/" not in title:
                title = repo_path

            desc_match = re.search(
                r"<p\b[^>]*class=\"[^\"]*(?:color-fg-muted|text-gray)[^\"]*\"[^>]*>(.*?)</p>",
                block,
                flags=re.DOTALL,
            )
            language_match = re.search(
                r"<span\b[^>]*itemprop=\"programmingLanguage\"[^>]*>(.*?)</span>",
                block,
                flags=re.DOTALL,
            )
            stars_match = re.search(
                rf'href="/{re.escape(repo_path)}/stargazers"[^>]*>(.*?)</a>',
                block,
                flags=re.DOTALL,
            )
            forks_match = re.search(
                rf'href="/{re.escape(repo_path)}/(?:forks|network/members)"[^>]*>(.*?)</a>',
                block,
                flags=re.DOTALL,
            )
            stars_today_match = re.search(
                r"([\d,]+)\s+stars?\s+(?:today|this week|this month)",
                _clean_text(block),
                flags=re.IGNORECASE,
            )
            metrics = {
                "stars": _parse_int(stars_match.group(1) if stars_match else ""),
                "forks": _parse_int(forks_match.group(1) if forks_match else ""),
                "stars_today": _parse_int(
                    stars_today_match.group(1) if stars_today_match else ""
                ),
                "trend_rank": float(trend_rank),
            }
            summary = _clean_text(desc_match.group(1) if desc_match else "")
            if metrics["stars_today"]:
                summary = (
                    f"GitHub Trending {since}: +{int(metrics['stars_today'])} stars. "
                    + summary
                ).strip()
            owner = repo_path.split("/", 1)[0]
            items.append(
                self.enrich(
                    Item(
                        source_id=self.source_id,
                        source_name=self.name,
                        title=title,
                        url=f"https://github.com/{repo_path}",
                        published_at=now,
                        author=owner,
                        summary=summary,
                        language=_clean_text(language_match.group(1) if language_match else ""),
                        metrics=metrics,
                    )
                )
            )
        return items


class ArxivSource(Source):
    def fetch(self) -> list[Item]:
        query = _apply_placeholders(str(self.config["query"]))
        max_results = min(int(self.config.get("max_results", self.max_items)), 100)
        params = urllib.parse.urlencode(
            {
                "search_query": query,
                "start": 0,
                "max_results": max_results,
                "sortBy": self.config.get("sort_by", "submittedDate"),
                "sortOrder": self.config.get("sort_order", "descending"),
            }
        )
        url = f"https://export.arxiv.org/api/query?{params}"
        xml = self.client.fetch_text(url)
        root = ET.fromstring(xml)
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        items: list[Item] = []
        for entry in entries[: self.max_items]:
            title = _child_text(entry, ["title"])
            summary = _child_text(entry, ["summary"])
            link = _link_from_entry(entry)
            published = parse_datetime(_child_text(entry, ["published", "updated"]))
            authors = [
                _child_text(author, ["name"])
                for author in entry.findall("{http://www.w3.org/2005/Atom}author")
            ]
            categories = [
                child.attrib.get("term", "")
                for child in list(entry)
                if child.tag.split("}")[-1] == "category"
            ]
            if title and link:
                items.append(
                    self.enrich(
                        Item(
                            source_id=self.source_id,
                            source_name=self.name,
                            title=title,
                            url=link,
                            published_at=published,
                            author=", ".join([a for a in authors if a][:4]),
                            summary=summary,
                            tags=[tag for tag in categories if tag],
                        )
                    )
                )
        return items


class GDELTSource(Source):
    def fetch(self) -> list[Item]:
        query = _apply_placeholders(str(self.config["query"]))
        max_records = min(int(self.config.get("max_records", self.max_items)), 250)
        timespan = str(self.config.get("timespan", "24h"))
        params = urllib.parse.urlencode(
            {
                "query": query,
                "mode": "artlist",
                "format": "json",
                "timespan": timespan,
                "maxrecords": max_records,
                "sort": self.config.get("sort", "hybridrel"),
            }
        )
        url = f"https://api.gdeltproject.org/api/v2/doc/doc?{params}"
        data = self.client.fetch_json(url)
        items: list[Item] = []
        for article in data.get("articles", [])[: self.max_items]:
            title = article.get("title") or ""
            link = article.get("url") or ""
            published = parse_datetime(article.get("seendate"))
            source_country = article.get("sourcecountry") or ""
            domain = article.get("domain") or ""
            if title and link:
                items.append(
                    self.enrich(
                        Item(
                            source_id=self.source_id,
                            source_name=self.name,
                            title=title,
                            url=link,
                            published_at=published,
                            author=domain,
                            summary=article.get("socialimage") or "",
                            language=article.get("language") or "",
                            tags=[tag for tag in [source_country, domain] if tag],
                        )
                    )
                )
        return items


class SampleSource(Source):
    def fetch(self) -> list[Item]:
        now = datetime.now(timezone.utc)
        samples = [
            Item(
                source_id=self.source_id,
                source_name=self.name,
                title="Open source model tooling project gains traction",
                url="https://example.com/open-source-model-tooling",
                published_at=now,
                author="Example News",
                summary="A new developer tool for model evaluation and observability is getting attention.",
                tags=["ai", "tools"],
                metrics={"stars": 1280, "forks": 96},
            ),
            Item(
                source_id=self.source_id,
                source_name=self.name,
                title="example/research-agent",
                url="https://github.com/example/research-agent",
                published_at=now,
                author="example",
                summary="A lightweight research automation agent with RSS, arXiv, and GitHub integrations.",
                language="Python",
                tags=["github", "agent"],
                metrics={"stars": 420, "forks": 37},
            ),
        ]
        return [self.enrich(item) for item in samples[: self.max_items]]


SOURCE_TYPES = {
    "rss": RSSSource,
    "github_search": GitHubSearchSource,
    "github_trending": GitHubTrendingSource,
    "arxiv": ArxivSource,
    "gdelt": GDELTSource,
    "sample": SampleSource,
}


def fetch_all_sources(
    source_configs: list[dict[str, Any]],
    client: HttpClient,
    sample_only: bool = False,
) -> list[SourceResult]:
    results: list[SourceResult] = []
    for source_config in source_configs:
        source_type = str(source_config.get("type", "rss"))
        if sample_only and source_type != "sample":
            continue
        if not sample_only and not bool(source_config.get("enabled", True)):
            continue
        source_cls = SOURCE_TYPES.get(source_type)
        if source_cls is None:
            results.append(
                SourceResult(
                    source_id=str(source_config.get("id", "unknown")),
                    ok=False,
                    items=[],
                    error=f"Unsupported source type: {source_type}",
                )
            )
            continue
        source = source_cls(source_config, client)
        try:
            results.append(SourceResult(source.source_id, True, source.fetch()))
        except Exception as exc:
            results.append(SourceResult(source.source_id, False, [], str(exc)))
    return results
