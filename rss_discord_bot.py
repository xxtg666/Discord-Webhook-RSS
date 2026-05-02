#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RSS to Discord push bot."""

import time
from typing import Dict, List, Optional

import feedparser
import requests
import schedule

from ai_handler import AIHandler
from article_history import ArticleHistoryStore
from bot_config import build_proxies, describe_proxies, load_config, setup_logging
from discord_client import DiscordWebhookClient
from rss_processing import (
    MessageFormatter,
    extract_media_urls,
    generate_item_id,
    html_to_markdown,
    should_filter_item,
)
from sent_store import SentItemStore
from url_shortener import URLShortenerServer


class RSSDiscordBot:
    """Coordinate RSS fetching, filtering, formatting, and Discord delivery."""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = load_config(config_file)
        self.logger = setup_logging(self.config)

        self.sent_store = SentItemStore()
        self.article_history = ArticleHistoryStore()
        self.proxies = build_proxies(self.config, self.logger)
        self.ai_handler = AIHandler(config_file, proxies=self.proxies)
        self.url_shortener = self._create_url_shortener()

        self.message_formatter = MessageFormatter(
            self.config,
            self.url_shortener,
            self.logger,
        )
        self.discord_client = DiscordWebhookClient(
            webhook_url=self.config["discord_webhook_url"],
            timeout=self.config.get("timeout", 30),
            proxies=self.proxies,
            logger=self.logger,
        )

    def _create_url_shortener(self):
        shortener_config = self.config.get("url_shortener", {})
        if not shortener_config.get("enabled", False):
            self.logger.info("短链接服务已禁用")
            return None

        try:
            host = shortener_config.get("host", "localhost")
            port = shortener_config.get("port", 8080)
            admin_password = self.config.get("web_config", {}).get("admin_password", "admin")
            server = URLShortenerServer(
                host,
                port,
                ai_handler=self.ai_handler,
                admin_password=admin_password,
                webhook_url=self.config.get("discord_webhook_url"),
                proxies=self.proxies,
            )

            if server.start():
                self.logger.info(f"短链接服务器启动成功: http://{host}:{port}")
                return server

            self.logger.error("短链接服务器启动失败")
        except Exception as exc:
            self.logger.error(f"初始化短链接服务器失败: {exc}")

        return None

    def fetch_rss_feed(self) -> Optional[List[Dict]]:
        """Fetch and parse RSS feed entries."""
        try:
            rss_url = self.config["rss_url"]
            self.logger.info(f"正在获取RSS源: {rss_url}")

            response = requests.get(
                rss_url,
                headers={"User-Agent": self.config.get("user_agent", _default_user_agent())},
                timeout=self.config.get("timeout", 30),
                proxies=self.proxies,
            )
            response.raise_for_status()

            feed = feedparser.parse(response.content)
            if feed.bozo:
                self.logger.warning(f"RSS解析警告: {feed.bozo_exception}")

            entries = list(feed.entries or [])
            if not entries:
                self.logger.info("RSS源中没有找到文章")
                return []

            self.logger.info(f"成功获取到 {len(entries)} 篇文章")
            return entries
        except Exception as exc:
            self.logger.error(f"获取RSS源失败: {exc}")
            return None

    def process_new_items(self, items: List[Dict]) -> int:
        """Process new RSS items and return the count successfully pushed."""
        new_items_count = 0
        handled_items_count = 0

        for item in items:
            if self._is_already_handled(item):
                continue

            item_id = generate_item_id(item)
            if should_filter_item(item, self.config.get("filter_keywords", []), self.logger):
                self.sent_store.add(item_id)
                handled_items_count += 1
                continue

            prepared_item = self._prepare_item(item)
            if not self._passes_ai_audit(item, prepared_item["summary"]):
                self.sent_store.add(item_id)
                handled_items_count += 1
                continue

            message_data = self.message_formatter.format(
                item,
                prepared_item["summary"],
                prepared_item["media_urls"],
            )

            if self._send_with_retries(message_data):
                self.sent_store.add(item_id)
                self.article_history.add(item, prepared_item["summary"])
                self._save_article_history()
                handled_items_count += 1
                new_items_count += 1
                self.logger.info(f"新文章已推送: {item.get('title', '无标题')}")
                time.sleep(1)
            else:
                self.logger.error(f"文章推送失败: {item.get('title', '无标题')}")

        if handled_items_count > 0:
            self._save_sent_items()

        return new_items_count

    def _is_already_handled(self, item: Dict) -> bool:
        return self.sent_store.contains(generate_item_id(item))

    def _prepare_item(self, item: Dict) -> Dict:
        raw_summary = item.get("summary", "") or item.get("description", "")
        media_urls = extract_media_urls(raw_summary)
        markdown_summary = html_to_markdown(raw_summary)
        processed_summary = self.ai_handler.preprocess_article(
            item.get("title", ""),
            markdown_summary,
            recent_articles=self.article_history.recent(),
            raw_html=raw_summary,
            link=item.get("link", ""),
        )

        return {"summary": processed_summary, "media_urls": media_urls}

    def _passes_ai_audit(self, item: Dict, summary: str) -> bool:
        recommend, reason = self.ai_handler.check_article(item.get("title", ""), summary)
        if recommend:
            return True

        self.logger.info(f"文章被 AI 拦截: {item.get('title', '无标题')} - 原因: {reason}")
        return False

    def _send_with_retries(self, message_data: Dict) -> bool:
        max_retries = self.config.get("max_retries", 3)
        for attempt in range(max_retries):
            if self.discord_client.send(message_data):
                return True

            if attempt < max_retries - 1:
                self.logger.warning(f"发送失败，{attempt + 1}/{max_retries} 次重试...")
                time.sleep(2**attempt)

        return False

    def _save_sent_items(self) -> None:
        try:
            self.sent_store.save()
        except Exception as exc:
            self.logger.error(f"保存已发送项目记录失败: {exc}")

    def _save_article_history(self) -> None:
        try:
            self.article_history.save()
        except Exception as exc:
            self.logger.error(f"保存文章历史记录失败: {exc}")

    def check_and_send(self):
        """Check RSS and push new content."""
        self.logger.info("开始检查RSS更新...")

        items = self.fetch_rss_feed()
        if items is None:
            self.logger.error("获取RSS内容失败")
            return
        if not items:
            self.logger.info("没有找到新内容")
            return

        new_count = self.process_new_items(items)
        if new_count > 0:
            self.logger.info(f"成功推送 {new_count} 篇新文章")
        else:
            self.logger.info("没有新文章需要推送")

    def run(self):
        """Run the bot scheduler."""
        self._log_startup()

        check_interval = self.config.get("check_interval", 600)
        schedule.every(check_interval).seconds.do(self.check_and_send)
        schedule.every(12).hours.do(self.ai_handler.optimize_rules)

        self.check_and_send()

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("收到停止信号，正在关闭机器人...")
        except Exception as exc:
            self.logger.error(f"运行时错误: {exc}")
        finally:
            if self.url_shortener:
                self.url_shortener.stop()
            self.logger.info("RSS Discord推送机器人已停止")

    def _log_startup(self) -> None:
        self.logger.info("RSS Discord推送机器人启动")
        self.logger.info(f"RSS源: {self.config['rss_url']}")
        self.logger.info(f"检查间隔: {self.config.get('check_interval', 600)} 秒")

        filter_keywords = self.config.get("filter_keywords", [])
        if filter_keywords:
            self.logger.info(f"关键词过滤已启用，过滤词汇: {', '.join(filter_keywords)}")
        else:
            self.logger.info("关键词过滤已禁用")

        self.logger.info(describe_proxies(self.proxies))


def _default_user_agent() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )


def main():
    """CLI entry point."""
    try:
        bot = RSSDiscordBot()
        bot.run()
    except Exception as exc:
        print(f"启动失败: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
