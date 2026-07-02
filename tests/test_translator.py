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

    def test_openai_translation_falls_back_to_candidate_model(self):
        config = TranslationConfig(
            provider="openai_compatible",
            openai_base_url="https://example.com/v1",
            openai_api_key_env="TEST_OPENAI_KEY",
            openai_model="gpt-5.4-mini",
            openai_model_candidates=["deepseek-v4-flash"],
        )
        item = Item(
            source_id="github_trending_daily",
            source_name="GitHub Trending Daily",
            title="owner/repo",
            url="https://github.com/owner/repo",
            summary="A trending repository.",
        )
        client = MagicMock()
        client.post_json.side_effect = [
            RuntimeError("primary unavailable"),
            {"choices": [{"message": {"content": "备用模型翻译成功"}}]},
        ]

        translator = OpenAICompatibleTranslator(config, client)
        with patch.dict("os.environ", {"TEST_OPENAI_KEY": "secret"}):
            translator.translate_items([item])

        models = [call.args[1]["model"] for call in client.post_json.call_args_list]
        self.assertEqual(models, ["gpt-5.4-mini", "deepseek-v4-flash"])
        self.assertEqual(item.translation, "备用模型翻译成功")


if __name__ == "__main__":
    unittest.main()
