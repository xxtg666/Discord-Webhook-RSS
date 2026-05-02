import json
import os
import unittest

from ai_handler import AIHandler
from article_history import ArticleHistoryStore


TEST_DIR = os.path.dirname(__file__)


def test_path(filename):
    return os.path.join(TEST_DIR, filename)


def remove_if_exists(filename):
    try:
        os.remove(test_path(filename))
    except FileNotFoundError:
        pass


class RecordingAIHandler(AIHandler):
    def __init__(self, config_file):
        super().__init__(config_file)
        self.recorded_messages = None
        self.recorded_json_mode = None

    def _call_llm(self, messages, json_mode=True, model_override=None):
        self.recorded_messages = messages
        self.recorded_json_mode = json_mode
        return "前文摘要：此前报道了测试事项。\n\n当前文章新增了处理结果。"


class FallbackAIHandler(AIHandler):
    def __init__(self, config_file):
        super().__init__(config_file)
        self.calls = []

    def _post_llm_request(self, base_url, headers, payload, json_mode):
        self.calls.append(dict(payload))
        if payload.get("response_format"):
            retry_payload = dict(payload)
            retry_payload.pop("response_format", None)
            return self._post_llm_request(base_url, headers, retry_payload, json_mode)
        return {"recommend": True, "reason": "ok"}


class AIPreprocessingTests(unittest.TestCase):
    def test_preprocess_uses_structured_json_payload_with_recent_articles(self):
        config_file = test_path("_tmp_ai_config.json")
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "ai_config": {
                            "enabled": True,
                            "preprocessing": {"enabled": True, "prompt": "保留Markdown"},
                        }
                    },
                    f,
                )

            handler = RecordingAIHandler(config_file)
            content = handler.preprocess_article(
                "新文章",
                "正文\n\n🍀[频道](https://t.me/example)",
                recent_articles=[{"title": "旧文章", "link": "https://example.com/old", "summary": "旧摘要"}],
                raw_html='<div class="rsshub-quote"><blockquote>旧文章</blockquote></div>',
                link="https://t.me/zaihuapd/2",
            )
        finally:
            remove_if_exists("_tmp_ai_config.json")

        self.assertEqual(content, "前文摘要：此前报道了测试事项。\n\n当前文章新增了处理结果。")
        self.assertFalse(handler.recorded_json_mode)

        payload = json.loads(handler.recorded_messages[1]["content"])
        self.assertEqual(payload["current_article"]["title"], "新文章")
        self.assertEqual(payload["current_article"]["link"], "https://t.me/zaihuapd/2")
        self.assertIn("rsshub-quote", payload["current_article"]["raw_html"])
        self.assertEqual(payload["recent_pushed_articles"][0]["title"], "旧文章")
        self.assertEqual(payload["task"], "remove_promotions_and_summarize_quotes_only")
        self.assertNotIn("custom_user_preferences", payload)

        system_prompt = handler.recorded_messages[0]["content"]
        self.assertIn("你只能做两件事", system_prompt)
        self.assertIn("禁止总结、润色、翻译、改写", system_prompt)
        self.assertIn("必须逐字保留", system_prompt)
        self.assertIn("直接输出处理后的 Markdown 正文", system_prompt)
        self.assertNotIn("输出必须是 JSON", system_prompt)
        self.assertNotIn("标题和正文重复", system_prompt)

    def test_json_mode_can_retry_without_response_format(self):
        config_file = test_path("_tmp_ai_config.json")
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump({"ai_config": {"enabled": True, "api_key": "test"}}, f)

            handler = FallbackAIHandler(config_file)
            result = handler._call_llm([{"role": "user", "content": "return json"}], json_mode=True)
        finally:
            remove_if_exists("_tmp_ai_config.json")

        self.assertEqual(result, {"recommend": True, "reason": "ok"})
        self.assertEqual(len(handler.calls), 2)
        self.assertIn("response_format", handler.calls[0])
        self.assertNotIn("response_format", handler.calls[1])


class ArticleHistoryStoreTests(unittest.TestCase):
    def test_article_history_keeps_recent_processed_summaries(self):
        history_file = test_path("_tmp_history.json")
        try:
            store = ArticleHistoryStore(history_file, max_items=2)
            store.add({"title": "一", "link": "1"}, "摘要一")
            store.add({"title": "二", "link": "2"}, "摘要二")
            store.add({"title": "三", "link": "3"}, "摘要三")
            store.save()

            loaded = ArticleHistoryStore(history_file, max_items=2)
        finally:
            remove_if_exists("_tmp_history.json")

        self.assertEqual([item["title"] for item in loaded.recent(10)], ["二", "三"])
        self.assertEqual(loaded.recent(1)[0]["summary"], "摘要三")


if __name__ == "__main__":
    unittest.main()
