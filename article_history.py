#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recent pushed article history for AI preprocessing context."""

import json
import os
import time
from typing import Dict, List


class ArticleHistoryStore:
    """JSON-backed cache of recently pushed articles."""

    def __init__(self, filename: str = "article_history.json", max_items: int = 80):
        self.filename = filename
        self.max_items = max_items
        self.items = self._load()

    def _load(self) -> List[Dict]:
        if not os.path.exists(self.filename):
            return []

        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data.get("articles", [])
            if isinstance(data, list):
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        return []

    def recent(self, limit: int = 12) -> List[Dict]:
        return self.items[-limit:]

    def add(self, item: Dict, processed_summary: str) -> None:
        article = {
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "summary": processed_summary,
            "timestamp": time.time(),
        }

        self.items = [
            existing
            for existing in self.items
            if existing.get("link") != article["link"] or not article["link"]
        ]
        self.items.append(article)
        self.items = self.items[-self.max_items :]

    def save(self) -> None:
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump({"articles": self.items, "updated_at": time.time()}, f, ensure_ascii=False, indent=2)
