#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Persistence for sent RSS item ids."""

import json
import os
from datetime import datetime
from typing import Set


class SentItemStore:
    """Small JSON-backed store used for RSS de-duplication."""

    def __init__(self, filename: str = "sent_items.json"):
        self.filename = filename
        self.items = self._load()

    def _load(self) -> Set[str]:
        if not os.path.exists(self.filename):
            return set()

        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("sent_items", []))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

    def contains(self, item_id: str) -> bool:
        return item_id in self.items

    def add(self, item_id: str) -> None:
        self.items.add(item_id)

    def save(self) -> None:
        data = {
            "sent_items": list(self.items),
            "last_updated": datetime.now().isoformat(),
        }
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
