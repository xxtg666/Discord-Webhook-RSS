#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RSS item parsing, filtering, and message formatting helpers."""

import base64
import html
import re
from typing import Dict, List, Optional


URL_PATTERN = r"https?://[^\s\)\]\}>]+"


def generate_item_id(item: Dict) -> str:
    """Generate a stable id from the RSS link, falling back to title."""
    source = item.get("link") or item.get("title", "")
    return base64.b64encode(source.encode("utf-8")).decode("ascii")


def should_filter_item(item: Dict, filter_keywords: List[str], logger) -> bool:
    """Return True when an item matches one of the configured keywords."""
    if not filter_keywords:
        return False

    content = " ".join(
        [
            item.get("title", ""),
            item.get("summary", ""),
            item.get("description", ""),
        ]
    ).lower()

    for keyword in filter_keywords:
        if keyword.lower() in content:
            title = item.get("title", "无标题")
            logger.info(f"文章被过滤 - 包含关键词 '{keyword}': {title}")
            return True

    return False


def extract_media_urls(html_content: str) -> List[str]:
    """Extract image/video URLs from RSS HTML content."""
    if not html_content:
        return []

    media_urls = []
    patterns = [
        r'<img[^>]+src=["\']([^"\'>]+)["\'][^>]*>',
        r'<video[^>]+src=["\']([^"\'>]+)["\'][^>]*>',
        r'<video[^>]+poster=["\']([^"\'>]+)["\'][^>]*>',
    ]
    for pattern in patterns:
        media_urls.extend(re.findall(pattern, html_content, re.IGNORECASE))

    return media_urls


def html_to_markdown(html_content: str) -> str:
    """Convert the small subset of HTML emitted by RSS feeds to Markdown."""
    if not html_content:
        return ""

    content = html.unescape(html_content)
    content = re.sub(
        r'<div[^>]*class=["\'][^"\']*rsshub-quote[^"\']*["\'][^>]*>\s*<blockquote[^>]*>(.*?)</blockquote>\s*</div>',
        lambda match: _format_quote_block(match.group(1), "前文引用"),
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content = re.sub(
        r"<blockquote[^>]*>(.*?)</blockquote>",
        lambda match: _format_quote_block(match.group(1), "引用"),
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content = _html_fragment_to_markdown(content)
    content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)

    return content.strip()


def _format_quote_block(html_content: str, label: str) -> str:
    quote_text = _html_fragment_to_markdown(html_content)
    quote_lines = []
    for line in quote_text.splitlines():
        quote_lines.append(f"> {line}" if line.strip() else ">")

    return f"\n\n[{label}]\n" + "\n".join(quote_lines).strip() + f"\n[/{label}]\n\n"


def _html_fragment_to_markdown(html_content: str) -> str:
    content = re.sub(r"<br\s*/?>", "\n", html_content, flags=re.IGNORECASE)
    content = re.sub(r"<b>(.*?)</b>", r"**\1**", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<strong>(.*?)</strong>", r"**\1**", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<i>(.*?)</i>", r"*\1*", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<em>(.*?)</em>", r"*\1*", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(
        r'<a[^>]+href=["\']([^"\'>]+)["\'][^>]*>(.*?)</a>',
        r"[\2](\1)",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content = re.sub(r"<code>(.*?)</code>", r"`\1`", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<video[^>]*>.*?</video>", "", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<img[^>]*>", "", content, flags=re.IGNORECASE)
    content = re.sub(r"</div\s*>", "\n\n", content, flags=re.IGNORECASE)
    content = re.sub(r"<[^>]+>", "", content)
    content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)

    return content.strip()


def shorten_urls_in_text(text: str, url_shortener, domain: str, logger) -> str:
    """Replace URLs in text with short links when the shortener is available."""
    if not url_shortener:
        return text

    def replace_url(match):
        original_url = match.group(0)
        try:
            short_code = url_shortener.shorten_url(original_url)
            short_url = f"{domain.rstrip('/')}/{short_code}"
            logger.debug(f"缩短链接: {original_url} -> {short_url}")
            return short_url
        except Exception as exc:
            logger.warning(f"缩短链接失败 {original_url}: {exc}")
            return original_url

    return re.sub(URL_PATTERN, replace_url, text)


class MessageFormatter:
    """Build Discord message payloads from processed RSS items."""

    def __init__(self, config: Dict, url_shortener, logger):
        self.config = config
        self.url_shortener = url_shortener
        self.logger = logger

    @property
    def shortener_domain(self) -> str:
        shortener_config = self.config.get("url_shortener", {})
        return shortener_config.get("domain", "http://localhost:8080").rstrip("/")

    def format(self, item: Dict, processed_summary: str, media_urls: List[str]) -> Dict:
        message = "📰 "
        if processed_summary:
            message += processed_summary

        message = shorten_urls_in_text(
            message,
            self.url_shortener,
            self.shortener_domain,
            self.logger,
        )

        feedback_url = self._build_feedback_url(item)
        if feedback_url:
            message += f"\n\n[🚫 不感兴趣]({feedback_url})"

        return {"content": message, "media_urls": media_urls}

    def _build_feedback_url(self, item: Dict) -> Optional[str]:
        if not self.url_shortener:
            return None

        try:
            item_id = self.url_shortener.cache_item(item)
            return f"{self.shortener_domain}/f?id={item_id}"
        except Exception as exc:
            self.logger.error(f"生成反馈链接失败: {exc}")
            return None
