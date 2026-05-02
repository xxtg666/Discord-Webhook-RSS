#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discord webhook delivery."""

import time
from typing import Dict, List

import requests


class DiscordWebhookClient:
    """Send formatted RSS messages to Discord webhooks."""

    def __init__(self, webhook_url: str, timeout: int, proxies: Dict, logger, username: str = "ZaihuaNews"):
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.proxies = proxies
        self.logger = logger
        self.username = username

    def send(self, message_data: Dict) -> bool:
        """Send message content and optional media attachments."""
        if self.webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
            self.logger.error("请在config.json中设置正确的Discord Webhook URL")
            return False

        try:
            message_parts = split_message(message_data["content"])
            files = self._download_media(message_data.get("media_urls", []))
            return self._send_parts(message_parts, files)
        except Exception as exc:
            self.logger.error(f"发送消息到Discord失败: {exc}")
            return False

    def _download_media(self, media_urls: List[str]) -> List:
        files = []
        for index, media_url in enumerate(media_urls[:5]):
            try:
                response = requests.get(media_url, timeout=10, proxies=self.proxies)
                if response.status_code != 200:
                    continue

                file_ext = media_url.split(".")[-1].split("?")[0]
                if file_ext.lower() not in ["jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "avi"]:
                    continue

                filename = f"media_{index + 1}.{file_ext}"
                files.append(("file", (filename, response.content)))
                self.logger.info(f"准备发送附件: {filename}")
            except Exception as exc:
                self.logger.warning(f"下载媒体文件失败 {media_url}: {exc}")

        return files

    def _send_parts(self, message_parts: List[str], files: List) -> bool:
        all_success = True

        for index, message_part in enumerate(message_parts):
            data = {"content": message_part, "username": self.username}
            current_files = files if index == 0 else []

            if current_files:
                response = requests.post(
                    self.webhook_url,
                    data=data,
                    files=current_files,
                    timeout=self.timeout,
                    proxies=self.proxies,
                )
            else:
                response = requests.post(
                    self.webhook_url,
                    json=data,
                    timeout=self.timeout,
                    proxies=self.proxies,
                )

            if response.status_code in (200, 204):
                suffix = f"，包含 {len(current_files)} 个附件" if index == 0 else ""
                self.logger.info(f"消息第{index + 1}部分发送成功{suffix}")
            else:
                self.logger.error(f"发送消息第{index + 1}部分失败: {response.status_code} - {response.text}")
                self.logger.error(f"消息内容: \n{message_part}")
                all_success = False

            if index < len(message_parts) - 1:
                time.sleep(1)

        if all_success and len(message_parts) > 1:
            self.logger.info(f"长消息已分{len(message_parts)}条发送完成")

        return all_success


def split_message(content: str, limit: int = 2000) -> List[str]:
    """Split a Discord message while preserving paragraphs when possible."""
    if len(content) <= limit:
        return [content]

    messages = []
    current_message = ""

    for paragraph in content.split("\n\n"):
        if len(paragraph) > limit:
            if current_message:
                messages.append(current_message.strip())
                current_message = ""

            messages.extend(_split_long_paragraph(paragraph, limit))
            continue

        test_message = current_message + ("\n\n" if current_message else "") + paragraph
        if len(test_message) > limit:
            if current_message:
                messages.append(current_message.strip())
            current_message = paragraph
        else:
            current_message = test_message

    if current_message:
        messages.append(current_message.strip())

    return messages


def _split_long_paragraph(paragraph: str, limit: int) -> List[str]:
    chunks = []
    temp_content = ""

    for line in paragraph.split("\n"):
        if len(temp_content + line + "\n") > limit:
            if temp_content:
                chunks.append(temp_content.strip())
                temp_content = line + "\n"
            else:
                chunks.append(line[: limit - 3] + "...")
        else:
            temp_content += line + "\n"

    if temp_content:
        chunks.append(temp_content.strip())

    return chunks
