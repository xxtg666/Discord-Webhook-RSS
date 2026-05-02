import unittest

from discord_client import split_message
from rss_processing import (
    extract_media_urls,
    generate_item_id,
    html_to_markdown,
)


class RSSProcessingTests(unittest.TestCase):
    def test_generate_item_id_prefers_link(self):
        first_id = generate_item_id({"title": "same", "link": "https://example.com/a"})
        second_id = generate_item_id({"title": "same", "link": "https://example.com/b"})

        self.assertNotEqual(first_id, second_id)

    def test_html_to_markdown_keeps_basic_formatting_and_removes_media_tags(self):
        html = '<p><strong>Hello</strong><br><a href="https://example.com">link</a></p><img src="x.jpg">'

        self.assertEqual(html_to_markdown(html), "**Hello**\n[link](https://example.com)")

    def test_extract_media_urls_finds_images_and_video_posters(self):
        html = '<img src="a.jpg"><video src="b.mp4" poster="c.png"></video>'

        self.assertEqual(extract_media_urls(html), ["a.jpg", "b.mp4", "c.png"])

    def test_html_to_markdown_marks_rsshub_quote_blocks(self):
        html = (
            '<div class="rsshub-quote"><blockquote>'
            '<p><a href="https://t.me/zaihuapd/41141"><b>科技圈在花频道</b>:</a></p>'
            "<p>OpenAI Codex 系统提示禁止 GPT-5.5 谈论妖精</p>"
            "</blockquote></div>"
            "<p><b>Codex 应用新增可选的 Codex pets</b><br><br>正文。</p>"
        )

        markdown = html_to_markdown(html)

        self.assertIn("[前文引用]", markdown)
        self.assertIn("[**科技圈在花频道**:](https://t.me/zaihuapd/41141)", markdown)
        self.assertIn("[/前文引用]", markdown)
        self.assertIn("**Codex 应用新增可选的 Codex pets**", markdown)

class DiscordClientTests(unittest.TestCase):
    def test_split_message_keeps_parts_under_limit(self):
        content = "a" * 10 + "\n\n" + "b" * 10 + "\n\n" + "c" * 10

        parts = split_message(content, limit=25)

        self.assertEqual(parts, ["aaaaaaaaaa\n\nbbbbbbbbbb", "cccccccccc"])
        self.assertTrue(all(len(part) <= 25 for part in parts))


if __name__ == "__main__":
    unittest.main()
