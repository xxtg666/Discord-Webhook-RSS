#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration, logging, and network helpers for the RSS bot."""

import json
import logging
from typing import Dict


def load_config(config_file: str) -> Dict:
    """Load and validate the bot configuration file."""
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"配置文件 {config_file} 不存在") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件 {config_file} 格式错误") from exc

    required_keys = ["rss_url", "discord_webhook_url"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"配置文件缺少必要项: {key}")

    return config


def setup_logging(config: Dict) -> logging.Logger:
    """Create the shared application logger."""
    log_level_name = config.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("RSSDiscordBot")
    logger.setLevel(log_level)
    logger.propagate = False

    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def build_proxies(config: Dict, logger: logging.Logger) -> Dict:
    """Build a requests-compatible proxy dictionary from config."""
    proxy_config = config.get("proxy", {})
    if not proxy_config.get("enabled", False):
        return {}

    proxies = {}
    if proxy_config.get("http"):
        proxies["http"] = proxy_config["http"]
    if proxy_config.get("https"):
        proxies["https"] = proxy_config["https"]

    auth_config = proxy_config.get("auth", {})
    username = auth_config.get("username", "")
    password = auth_config.get("password", "")
    if auth_config.get("enabled", False) and username and password:
        for protocol, proxy_url in list(proxies.items()):
            if "://" not in proxy_url:
                continue
            scheme, rest = proxy_url.split("://", 1)
            proxies[protocol] = f"{scheme}://{username}:{password}@{rest}"

    if proxies:
        logger.info(f"代理已启用: {', '.join(proxies.keys())}")

    return proxies


def describe_proxies(proxies: Dict) -> str:
    """Return a log-safe proxy summary with credentials hidden."""
    if not proxies:
        return "网络代理已禁用"

    proxy_info = []
    for protocol, url in proxies.items():
        display_url = url
        if "@" in url:
            scheme_auth, host_part = url.split("@", 1)
            if "://" in scheme_auth:
                scheme = scheme_auth.split("://", 1)[0]
                display_url = f"{scheme}://***:***@{host_part}"
        proxy_info.append(f"{protocol.upper()}: {display_url}")

    return f"网络代理已启用 - {', '.join(proxy_info)}"
