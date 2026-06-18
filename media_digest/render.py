from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Item
from .timeutil import format_local

GITHUB_ARCHIVE_FILENAME = "github_trending_archive.md"
GITHUB_ARCHIVE_PREAMBLE = (
    "# GitHub Trending 收集归档\n\n"
    "按收集日期整理的 GitHub 仓库信息，便于后续查阅。\n"
)
_GITHUB_ARCHIVE_SECTION_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def render_markdown(
    title: str,
    items: list[Item],
    tz_name: str,
    source_errors: list[str] | None = None,
) -> str:
    now = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {title}",
        "",
        f"> 生成时间：{now} ｜ 共 {len(items)} 条",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.append(f"## {index}. [{item.title}]({item.url})")
        meta = [
            item.source_name,
            format_local(item.published_at, tz_name),
            f"score {item.score:.1f}",
        ]
        if item.language:
            meta.append(item.language)
        if item.metrics:
            metrics = []
            if item.metrics.get("trend_rank"):
                metrics.append(f"trend #{int(item.metrics['trend_rank'])}")
            if item.metrics.get("stars"):
                metrics.append(f"stars {int(item.metrics['stars'])}")
            if item.metrics.get("stars_today"):
                metrics.append(f"today +{int(item.metrics['stars_today'])}")
            if item.metrics.get("forks"):
                metrics.append(f"forks {int(item.metrics['forks'])}")
            if item.metrics.get("points"):
                metrics.append(f"points {int(item.metrics['points'])}")
            if item.metrics.get("comments"):
                metrics.append(f"comments {int(item.metrics['comments'])}")
            if metrics:
                meta.append(" / ".join(metrics))
        lines.append(" · ".join(meta))
        if item.author:
            lines.append(f"作者/来源：{item.author}")
        if item.translation:
            lines.append("")
            lines.append(f"概述：{_clip(item.translation, 420)}")
            if item.summary:
                lines.append("")
                lines.append(f"原文：{_clip(item.summary, 280)}")
        elif item.summary:
            lines.append("")
            lines.append(f"摘要：{_clip(item.summary, 360)}")
        if item.tags:
            lines.append("")
            lines.append("标签：" + " ".join(f"`{tag}`" for tag in item.tags[:8]))
        lines.append("")

    if source_errors:
        lines.extend(["---", "### 采集提醒"])
        lines.extend(f"- {error}" for error in source_errors)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _github_metrics_line(item: Item) -> str:
    metrics: list[str] = []
    if item.metrics.get("trend_rank"):
        metrics.append(f"Trending #{int(item.metrics['trend_rank'])}")
    if item.metrics.get("stars"):
        metrics.append(f"Stars {int(item.metrics['stars']):,}")
    if item.metrics.get("stars_today"):
        metrics.append(f"今日 +{int(item.metrics['stars_today']):,}")
    if item.metrics.get("forks"):
        metrics.append(f"Forks {int(item.metrics['forks']):,}")
    return " ｜ ".join(metrics)


def _xiaohongshu_metrics_line(item: Item) -> str:
    metrics: list[str] = []
    if item.metrics.get("trend_rank"):
        metrics.append(f"Trending #{int(item.metrics['trend_rank'])}")
    if item.metrics.get("stars"):
        metrics.append(f"{int(item.metrics['stars']):,} stars")
    if item.metrics.get("stars_today"):
        metrics.append(f"今日 +{int(item.metrics['stars_today']):,}")
    if item.language:
        metrics.append(item.language)
    return " ｜ ".join(metrics)


def _xiaohongshu_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def render_github_repo_entry(index: int, item: Item) -> str:
    lines = [f"### {index}. [{item.title}]({item.url})", ""]
    if item.author:
        lines.append(f"- **作者/组织**：{item.author}")
    if item.language:
        lines.append(f"- **语言**：{item.language}")
    metrics = _github_metrics_line(item)
    if metrics:
        lines.append(f"- **指标**：{metrics}")
    if item.tags:
        lines.append(
            "- **标签**：" + " ".join(f"`{tag}`" for tag in item.tags[:8])
        )
    lines.append("")
    if item.translation:
        lines.append(f"**中文介绍**：{item.translation}")
        lines.append("")
    if item.summary:
        lines.append(f"**原始描述**：{_clip(item.summary, 500)}")
        lines.append("")
    lines.append("---")
    return "\n".join(lines)


def render_github_archive_section(
    date_str: str,
    items: list[Item],
    tz_name: str,
    collected_at: datetime,
) -> str:
    collected_label = collected_at.astimezone(ZoneInfo(tz_name)).strftime(
        "%Y-%m-%d %H:%M %Z"
    )
    lines = [
        f"## {date_str}",
        "",
        f"> 收集时间：{collected_label} ｜ 共 {len(items)} 个仓库",
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.append(render_github_repo_entry(index, item))
        lines.append("")
    return "\n".join(lines).strip()


def _split_github_archive_sections(content: str) -> tuple[str, dict[str, str]]:
    matches = list(_GITHUB_ARCHIVE_SECTION_RE.finditer(content))
    if not matches:
        preamble = content.strip()
        if preamble:
            preamble += "\n"
        return preamble or GITHUB_ARCHIVE_PREAMBLE, {}

    preamble = content[: matches[0].start()].strip()
    if not preamble:
        preamble = GITHUB_ARCHIVE_PREAMBLE
    else:
        preamble += "\n"

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        date_str = match.group(1)
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections[date_str] = content[start:end].strip()
    return preamble, sections


def update_github_archive(
    output_dir: str,
    items: list[Item],
    tz_name: str,
    *,
    filename: str = GITHUB_ARCHIVE_FILENAME,
) -> Path:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    collected_at = datetime.now(ZoneInfo(tz_name))
    date_str = collected_at.strftime("%Y-%m-%d")
    new_section = render_github_archive_section(
        date_str,
        items,
        tz_name,
        collected_at,
    )

    if path.exists():
        preamble, sections = _split_github_archive_sections(
            path.read_text(encoding="utf-8")
        )
    else:
        preamble = GITHUB_ARCHIVE_PREAMBLE
        sections = {}

    sections[date_str] = new_section
    body = preamble.rstrip() + "\n\n"
    body += "\n\n".join(sections[date_key] for date_key in sorted(sections, reverse=True))
    body += "\n"
    path.write_text(body, encoding="utf-8")
    return path


def render_xiaohongshu_draft(title: str, items: list[Item], hashtags: list[str]) -> str:
    is_github_digest = any(
        item.source_id.startswith("github") or "github.com/" in item.url
        for item in items
    )
    intro = (
        f"今天整理 {len(items)} 个值得关注的 GitHub Trending 项目。"
        "每个项目都附上中文概述、适用场景和原始链接，方便后续深读。"
        if is_github_digest
        else f"今天整理 {len(items)} 条值得关注的信息，保留关键事实和原始链接，方便后续深读。"
    )
    lines = [
        title,
        "",
        intro,
        "",
    ]
    for index, item in enumerate(items, start=1):
        summary = item.translation or item.summary or item.title
        section_title = f"{index:02d}｜{item.title}"
        metrics = _xiaohongshu_metrics_line(item)

        lines.append(section_title)
        if metrics:
            lines.append(f"热度：{metrics}")
        if item.author:
            lines.append(f"作者/组织：{item.author}")
        lines.append("")
        lines.append("中文概述：")
        lines.append(_xiaohongshu_text(summary))
        lines.append("")
        lines.append(f"原始链接：{item.url}")
        lines.append("")
        if index != len(items):
            lines.append("---")
            lines.append("")

    tags = " ".join(f"#{tag}" for tag in hashtags)
    if tags:
        lines.append(tags)
    return "\n".join(lines).strip() + "\n"


def write_outputs(
    output_dir: str,
    digest_markdown: str,
    xiaohongshu_draft: str | None,
) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    paths = {
        "digest": directory / f"digest_{stamp}.md",
    }
    paths["digest"].write_text(digest_markdown, encoding="utf-8")
    if xiaohongshu_draft:
        paths["xiaohongshu"] = directory / f"xiaohongshu_{stamp}.md"
        paths["xiaohongshu"].write_text(xiaohongshu_draft, encoding="utf-8")
    return paths
