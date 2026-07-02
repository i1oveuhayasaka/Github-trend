import tempfile
import unittest
from pathlib import Path

from media_digest.config import load_config


class ConfigTest(unittest.TestCase):
    def test_retired_xiaohongshu_publish_settings_are_ignored(self):
        text = """
[social.xiaohongshu]
enabled = true
max_items = 6
publish_enabled = true
publish_provider = "script"
publish_script = "scripts/publish_xiaohongshu_playwright.py"
browser_profile_dir = "data/xhs-browser-profile"
browser_headless = true
publish_timeout_seconds = 300
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(text, encoding="utf-8")
            config = load_config(path)

        xiaohongshu = config.social["xiaohongshu"]
        self.assertTrue(xiaohongshu.enabled)
        self.assertEqual(xiaohongshu.max_items, 6)
        self.assertFalse(hasattr(xiaohongshu, "publish_enabled"))


if __name__ == "__main__":
    unittest.main()
