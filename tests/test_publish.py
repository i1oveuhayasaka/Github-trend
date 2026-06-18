import unittest

from media_digest.publish import parse_xiaohongshu_draft
from scripts.publish_xiaohongshu_playwright import _parse_draft_text


class PublishTest(unittest.TestCase):
    def test_parse_xiaohongshu_draft_limits_title(self):
        draft = "GitHub热门趋势项目\n\n正文内容"
        title, content = parse_xiaohongshu_draft(draft)
        self.assertEqual(title, "GitHub热门趋势项目")
        self.assertEqual(content, draft)

    def test_parse_xiaohongshu_draft_clips_long_title(self):
        draft = "这是一个超过二十个字的小红书标题应该被截断"
        title, _ = parse_xiaohongshu_draft(draft)
        self.assertEqual(len(title), 20)

    def test_playwright_draft_parser_splits_title_and_body(self):
        draft = "GitHub热门趋势项目\n\n今天值得关注的几条信息：\n\n#每日资讯"
        title, body = _parse_draft_text(draft)
        self.assertEqual(title, "GitHub热门趋势项目")
        self.assertEqual(body, "今天值得关注的几条信息：\n\n#每日资讯")


if __name__ == "__main__":
    unittest.main()
