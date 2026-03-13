# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Discord Webhook RSS — a Python bot that monitors RSS feeds and pushes new articles to Discord via webhooks. Features AI-powered content filtering with user feedback learning, a built-in URL shortener, and a web admin interface. Written in Chinese (UI, logs, comments).

## Commands

```bash
pip install -r requirements.txt   # Install dependencies
python rss_discord_bot.py         # Run the bot (Ctrl+C to stop)
```

No test framework or build step exists. The web admin interface runs at `http://localhost:8080/admin/login`.

## Architecture

Three main modules, all plain Python with no frameworks:

- **`rss_discord_bot.py`** — Main entry point. `RSSDiscordBot` class handles the full lifecycle: fetch RSS → deduplicate → keyword filter → AI filter → format message → send to Discord. Uses `schedule` for periodic checks (default 10 min) and rule optimization (every 12h). Main loop: `while True: schedule.run_pending()`.

- **`ai_handler.py`** — `AIHandler` class wraps OpenAI-compatible LLM APIs. Three AI stages: preprocessing (clean noise from Markdown content), audit (check against rules), and rule optimization (analyze user feedback to generate new filter rules). Supports separate model config per stage (`audit_model`, `optimization_model`, `preprocessing_model`).

- **`url_shortener.py`** — `URLShortenerServer` runs a stdlib `http.server` in a background thread. Handles short URL redirects, feedback forms (user marks articles as "not interested"), and an admin dashboard for managing AI filter rules. Session-based auth with 24h expiry.

## Data Flow

```
RSS Feed → fetch_rss_feed() → feedparser
  → process_new_items():
      1. Dedup check (sent_items.json, base64 of link as ID)
      2. Keyword filter (config.filter_keywords)
      3. Extract media URLs from raw HTML (<img>, <video>)
      4. HTML → Markdown conversion
      5. Regex strip Telegram promo footer (t.me links at end of text)
      6. AI preprocess (clean noise from Markdown)
      7. AI audit (check against ai_rules.json)
      8. format_message() (URL shortening, feedback link)
      9. send_to_discord() (with retry)
  → User clicks [🚫 不感兴趣] feedback link
  → Feedback stored in pending_feedback.json
  → Every 12h: AI optimizes rules from feedback → ai_rules.json
```

## Auto-Generated Data Files

These JSON files are created at runtime and should not be manually edited or committed:

- `sent_items.json` — Sent article IDs (dedup tracking)
- `url_mappings.json` — Short code → URL mappings
- `item_cache.json` — Article metadata cache for feedback
- `ai_rules.json` — Current AI filter rules
- `pending_feedback.json` — User feedback awaiting optimization
- `feedback_history.json` — Historical feedback titles

## Key Implementation Details

- Discord messages are split at 2000 chars (Discord limit). Media files (images/videos) are extracted from raw HTML before any processing and sent as attachments.
- Content pipeline: raw HTML → extract media → HTML-to-Markdown → regex strip Telegram promo footer → AI preprocess (Markdown in/out) → AI audit → format message. The AI never sees raw HTML.
- Telegram promo links (`_strip_telegram_promo`) are removed by regex anchored to end-of-text only; mid-article t.me links are preserved.
- All HTTP requests go through a shared `requests.Session` with configurable proxy support (HTTP/HTTPS with optional auth).
- LLM calls use `_call_llm()` in `ai_handler.py` which targets any OpenAI-compatible API (configurable `base_url`).
- Item IDs are base64-encoded article links; fallback to UUID if no link exists.
- The URL shortener generates 4-character codes and persists mappings to disk.
- Config is loaded from `config.json` at startup — all settings are there (no env vars).

## Dependencies

Only three external packages: `requests`, `feedparser`, `schedule`. Everything else uses Python stdlib (`http.server`, `json`, `logging`, `threading`).
