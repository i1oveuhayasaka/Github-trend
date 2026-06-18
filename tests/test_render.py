from datetime import datetime, timezone
import tempfile
import unittest

from media_digest.models import Item
from media_digest.render import (
    render_markdown,
    render_xiaohongshu_draft,
    update_github_archive,
)


class RenderTest(unittest.TestCase):
    def test_render_markdown_includes_link_and_summary(self):
        item = Item(
            source_id="sample",
            source_name="Sample",
            title="Hello",
            url="https://example.com",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            summary="A useful story.",
            quality=1.0,
            score=12.3,
        )

        text = render_markdown("Digest", [item], "Asia/Shanghai")

        self.assertIn("# Digest", text)
        self.assertIn("[Hello](https://example.com)", text)
        self.assertIn("A useful story.", text)

    def test_update_github_archive_appends_and_replaces_same_day(self):
        item = Item(
            source_id="github_trending_daily",
            source_name="GitHub Trending Daily",
            title="owner/repo",
            url="https://github.com/owner/repo",
            published_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            author="owner",
            summary="A trending repository.",
            language="Python",
            tags=["github", "trending"],
            metrics={"stars": 1200, "stars_today": 88, "forks": 45, "trend_rank": 1},
            translation="这是一个值得关注的 Python 项目。",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = update_github_archive(tmpdir, [item], "Asia/Shanghai")
            first = archive_path.read_text(encoding="utf-8")
            today = datetime.now().strftime("%Y-%m-%d")
            self.assertIn("GitHub Trending 收集归档", first)
            self.assertIn(f"## {today}", first)
            self.assertIn("owner/repo", first)
            self.assertIn("中文介绍", first)
            self.assertIn("这是一个值得关注的 Python 项目。", first)
            self.assertIn("Stars 1,200", first)

            item.translation = "更新后的中文介绍。"
            update_github_archive(tmpdir, [item], "Asia/Shanghai")
            second = archive_path.read_text(encoding="utf-8")
            self.assertEqual(second.count(f"## {today}"), 1)
            self.assertIn("更新后的中文介绍。", second)
            self.assertNotIn("这是一个值得关注的 Python 项目。", second)

    def test_render_xiaohongshu_draft_keeps_full_chinese_summary(self):
        long_summary = (
            "这是一个用于构建开发者工具的开源项目，提供清晰的命令行接口、"
            "可扩展的插件机制和完整的文档示例，适合需要快速搭建内部效率工具的团队。"
            "它最近在 GitHub Trending 上增长明显，说明开发者对轻量自动化工作流仍然有持续需求。"
        )
        item = Item(
            source_id="github_trending_daily",
            source_name="GitHub Trending Daily",
            title="owner/repo",
            url="https://github.com/owner/repo",
            author="owner",
            language="Python",
            metrics={"stars": 12345, "stars_today": 678, "trend_rank": 1},
            translation=long_summary,
        )

        text = render_xiaohongshu_draft("每日高质量信息简报", [item], ["每日资讯", "开源项目"])

        self.assertIn("01｜owner/repo", text)
        self.assertIn("热度：Trending #1 ｜ 12,345 stars ｜ 今日 +678 ｜ Python", text)
        self.assertIn("中文概述：", text)
        self.assertIn(long_summary, text)
        self.assertNotIn("...", text)
        self.assertIn("原始链接：https://github.com/owner/repo", text)


if __name__ == "__main__":
    unittest.main()
