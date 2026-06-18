import unittest
from unittest.mock import MagicMock, patch

from media_digest.config import TranslationConfig
from media_digest.models import Item
from media_digest.translator import OpenAICompatibleTranslator, TranslationError


class TranslatorTest(unittest.TestCase):
    def test_openai_translation_failure_raises(self):
        config = TranslationConfig(
            provider="openai_compatible",
            target_language="zh",
            openai_base_url="https://example.com/v1",
            openai_api_key_env="TEST_OPENAI_KEY",
            openai_model="test-model",
        )
        item = Item(
            source_id="github_trending_daily",
            source_name="GitHub Trending Daily",
            title="owner/repo",
            url="https://github.com/owner/repo",
            summary="A trending repository.",
        )
        client = MagicMock()
        client.post_json.side_effect = RuntimeError("upstream unavailable")
        translator = OpenAICompatibleTranslator(config, client)
        with patch.dict("os.environ", {"TEST_OPENAI_KEY": "secret"}):
            with self.assertRaises(TranslationError) as ctx:
                translator.translate_items([item])
        self.assertIn("owner/repo", ctx.exception.failures[0])
        self.assertIn("upstream unavailable", ctx.exception.failures[0])


if __name__ == "__main__":
    unittest.main()
