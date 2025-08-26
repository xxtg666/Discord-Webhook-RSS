#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS到Discord推送机器人
自动监控RSS源并将新内容推送到Discord频道
"""

import json
import logging
import os
import time
import hashlib
import re
import base64
from datetime import datetime
from typing import Dict, List, Optional, Set

import feedparser
import requests
import schedule
from url_shortener import URLShortenerServer


class RSSDiscordBot:
    """RSS到Discord推送机器人主类"""
    
    def __init__(self, config_file: str = "config.json"):
        """初始化机器人
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = self._load_config()
        self.sent_items_file = "sent_items.json"
        self.sent_items = self._load_sent_items()
        self._setup_logging()
        
        # 设置代理
        self.proxies = self._setup_proxy()
        
        # 初始化短链接服务器
        self.url_shortener = None
        self._setup_url_shortener()
        
    def _load_config(self) -> Dict:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 验证必要的配置项
            required_keys = ['rss_url', 'discord_webhook_url']
            for key in required_keys:
                if key not in config:
                    raise ValueError(f"配置文件缺少必要项: {key}")
                    
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件 {self.config_file} 不存在")
        except json.JSONDecodeError:
            raise ValueError(f"配置文件 {self.config_file} 格式错误")
    
    def _load_sent_items(self) -> Set[str]:
        """加载已发送项目记录"""
        try:
            if os.path.exists(self.sent_items_file):
                with open(self.sent_items_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('sent_items', []))
            return set()
        except (FileNotFoundError, json.JSONDecodeError):
            return set()
    
    def _save_sent_items(self):
        """保存已发送项目记录"""
        try:
            data = {
                'sent_items': list(self.sent_items),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.sent_items_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存已发送项目记录失败: {e}")
    
    def _setup_proxy(self) -> Dict:
        """设置代理配置
        
        Returns:
            代理字典，用于requests库
        """
        proxy_config = self.config.get('proxy', {})
        
        if not proxy_config.get('enabled', False):
            return {}
        
        proxies = {}
        
        # 基本代理设置
        if proxy_config.get('http'):
            proxies['http'] = proxy_config['http']
        if proxy_config.get('https'):
            proxies['https'] = proxy_config['https']
        
        # 处理代理认证
        auth_config = proxy_config.get('auth', {})
        if auth_config.get('enabled', False):
            username = auth_config.get('username', '')
            password = auth_config.get('password', '')
            
            if username and password:
                # 更新代理URL以包含认证信息
                for protocol in ['http', 'https']:
                    if protocol in proxies:
                        proxy_url = proxies[protocol]
                        if '://' in proxy_url:
                            scheme, rest = proxy_url.split('://', 1)
                            proxies[protocol] = f"{scheme}://{username}:{password}@{rest}"
        
        if proxies:
            self.logger.info(f"代理已启用: {', '.join(proxies.keys())}")
        
        return proxies
    
    def _setup_logging(self):
        """设置日志"""
        log_level = getattr(logging, self.config.get('log_level', 'INFO').upper())
        
        # 创建日志格式
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 设置控制台日志
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        
        # 配置logger
        self.logger = logging.getLogger('RSSDiscordBot')
        self.logger.setLevel(log_level)
        self.logger.addHandler(console_handler)
    
    def _setup_url_shortener(self):
        """设置短链接服务器"""
        shortener_config = self.config.get('url_shortener', {})
        
        if shortener_config.get('enabled', False):
            try:
                host = shortener_config.get('host', 'localhost')
                port = shortener_config.get('port', 8080)
                
                self.url_shortener = URLShortenerServer(host, port)
                
                if self.url_shortener.start():
                    self.logger.info(f"短链接服务器启动成功: http://{host}:{port}")
                else:
                    self.logger.error("短链接服务器启动失败")
                    self.url_shortener = None
                    
            except Exception as e:
                self.logger.error(f"初始化短链接服务器失败: {e}")
                self.url_shortener = None
        else:
            self.logger.info("短链接服务已禁用")
    
    def _shorten_urls_in_text(self, text: str) -> str:
        """缩短文本中的所有URL
        
        Args:
            text: 包含URL的文本
            
        Returns:
            缩短URL后的文本
        """
        if not self.url_shortener:
            return text
        
        shortener_config = self.config.get('url_shortener', {})
        domain = shortener_config.get('domain', 'http://localhost:8080')
        
        # URL正则表达式
        url_pattern = r'https?://[^\s\)\]\}>]+'
        
        def replace_url(match):
            original_url = match.group(0)
            try:
                short_code = self.url_shortener.shorten_url(original_url)
                short_url = f"{domain.rstrip('/')}/{short_code}"
                self.logger.debug(f"缩短链接: {original_url} -> {short_url}")
                return short_url
            except Exception as e:
                self.logger.warning(f"缩短链接失败 {original_url}: {e}")
                return original_url
        
        return re.sub(url_pattern, replace_url, text)
    
    def _generate_item_id(self, item: Dict) -> str:
        """生成文章唯一标识符
        
        Args:
            item: RSS文章项目
            
        Returns:
            文章的唯一标识符（基于链接的base64编码）
        """
        # 使用链接的base64编码作为唯一ID
        link = item.get('link', '')
        if not link:
            # 如果没有链接，回退到使用标题
            title = item.get('title', '')
            link = title
        
        # 将链接编码为base64
        link_bytes = link.encode('utf-8')
        base64_id = base64.b64encode(link_bytes).decode('ascii')
        
        return base64_id
    
    def _should_filter_item(self, item: Dict) -> bool:
        """检查文章是否应该被过滤
        
        Args:
            item: RSS文章项目
            
        Returns:
            如果应该过滤返回True，否则返回False
        """
        filter_keywords = self.config.get('filter_keywords', [])
        if not filter_keywords:
            return False
        
        title = item.get('title', '').lower()
        summary = item.get('summary', '').lower()
        description = item.get('description', '').lower()
        
        # 检查标题、摘要和描述中是否包含过滤关键词
        content_to_check = f"{title} {summary} {description}"
        
        for keyword in filter_keywords:
            if keyword.lower() in content_to_check:
                self.logger.info(f"文章被过滤 - 包含关键词 '{keyword}': {item.get('title', '无标题')}")
                return True
        
        return False
    
    def _extract_media_urls(self, html_content: str) -> List[str]:
        """从HTML内容中提取媒体文件URL
        
        Args:
            html_content: HTML内容
            
        Returns:
            媒体文件URL列表
        """
        import re
        media_urls = []
        
        # 提取图片URL
        img_pattern = r'<img[^>]+src=["\']([^"\'>]+)["\'][^>]*>'
        img_matches = re.findall(img_pattern, html_content, re.IGNORECASE)
        media_urls.extend(img_matches)
        
        # 提取视频URL
        video_pattern = r'<video[^>]+src=["\']([^"\'>]+)["\'][^>]*>'
        video_matches = re.findall(video_pattern, html_content, re.IGNORECASE)
        media_urls.extend(video_matches)
        
        # 提取视频poster图片
        poster_pattern = r'<video[^>]+poster=["\']([^"\'>]+)["\'][^>]*>'
        poster_matches = re.findall(poster_pattern, html_content, re.IGNORECASE)
        media_urls.extend(poster_matches)
        
        return media_urls
    
    def _html_to_markdown(self, html_content: str) -> str:
        """将HTML内容转换为Markdown格式
        
        Args:
            html_content: HTML内容
            
        Returns:
            Markdown格式的文本
        """
        import re
        
        # 先处理换行标签
        content = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)
        
        # 处理粗体标签
        content = re.sub(r'<b>(.*?)</b>', r'**\1**', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<strong>(.*?)</strong>', r'**\1**', content, flags=re.IGNORECASE | re.DOTALL)
        
        # 处理斜体标签
        content = re.sub(r'<i>(.*?)</i>', r'*\1*', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<em>(.*?)</em>', r'*\1*', content, flags=re.IGNORECASE | re.DOTALL)
        
        # 处理链接标签
        content = re.sub(r'<a[^>]+href=["\']([^"\'>]+)["\'][^>]*>(.*?)</a>', r'[\2](\1)', content, flags=re.IGNORECASE | re.DOTALL)
        
        # 处理代码标签
        content = re.sub(r'<code>(.*?)</code>', r'`\1`', content, flags=re.IGNORECASE | re.DOTALL)
        
        # 处理段落标签
        content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', content, flags=re.IGNORECASE | re.DOTALL)
        
        # 移除视频和图片标签（已经提取了URL）
        content = re.sub(r'<video[^>]*>.*?</video>', '', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<img[^>]*>', '', content, flags=re.IGNORECASE)
        
        # 移除其他HTML标签
        content = re.sub(r'<[^>]+>', '', content)
        
        # 清理多余的空行
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        content = content.strip()
        
        return content
    

    
    def fetch_rss_feed(self) -> Optional[List[Dict]]:
        """获取RSS源内容
        
        Returns:
            RSS文章列表，失败时返回None
        """
        try:
            self.logger.info(f"正在获取RSS源: {self.config['rss_url']}")
            
            # 设置请求超时
            timeout = self.config.get('timeout', 30)
            
            # 设置User-Agent来避免被阻止
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # 先获取RSS内容
            response = requests.get(
                self.config['rss_url'], 
                headers=headers, 
                timeout=timeout,
                proxies=self.proxies
            )
            response.raise_for_status()
            
            # 解析RSS
            feed = feedparser.parse(response.content)
            
            if feed.bozo:
                self.logger.warning(f"RSS解析警告: {feed.bozo_exception}")
            
            if not feed.entries:
                self.logger.info("RSS源中没有找到文章")
                return []
            
            self.logger.info(f"成功获取到 {len(feed.entries)} 篇文章")
            return feed.entries
            
        except Exception as e:
            self.logger.error(f"获取RSS源失败: {e}")
            return None
    
    def format_message(self, item: Dict) -> Dict:
        """格式化Discord消息
        
        Args:
            item: RSS文章项目
            
        Returns:
            包含消息文本和媒体文件的字典
        """
        title = item.get('title', '无标题')
        link = item.get('link', '')
        
        # 获取摘要或描述
        summary = ''
        if 'summary' in item:
            summary = item.summary
        elif 'description' in item:
            summary = item.description
        
        # 提取媒体文件
        media_urls = []
        if summary:
            media_urls = self._extract_media_urls(summary)
        
        # 转换HTML为Markdown
        if summary:
            summary = self._html_to_markdown(summary)
        
        # 格式化消息
        message = f"📰 "
        if summary:
            message += summary
        
        # 缩短消息中的所有链接
        message = self._shorten_urls_in_text(message)
        
        return {
            'content': message,
            'media_urls': media_urls
        }
    
    def _split_message(self, content: str) -> List[str]:
        """将长消息按段落分割
        
        Args:
            content: 要分割的消息内容
            
        Returns:
            分割后的消息列表
        """
        if len(content) <= 2000:
            return [content]
        
        messages = []
        current_message = ""
        
        # 按连续两个换行符分割段落
        paragraphs = content.split('\n\n')
        
        for i, paragraph in enumerate(paragraphs):
            # 如果单个段落就超过2000字符，需要强制分割
            if len(paragraph) > 2000:
                # 先保存当前消息（如果有内容）
                if current_message:
                    messages.append(current_message.strip())
                    current_message = ""
                
                # 按行分割长段落
                lines = paragraph.split('\n')
                temp_content = ""
                
                for line in lines:
                    if len(temp_content + line + '\n') > 2000:
                        if temp_content:
                            messages.append(temp_content.strip())
                            temp_content = line + '\n'
                        else:
                            # 单行就超过2000字符，强制截断
                            messages.append(line[:1997] + '...')
                    else:
                        temp_content += line + '\n'
                
                if temp_content:
                    current_message = temp_content
            else:
                # 检查添加这个段落是否会超过限制
                test_message = current_message + ('\n\n' if current_message else '') + paragraph
                
                if len(test_message) > 2000:
                    # 超过限制，保存当前消息并开始新消息
                    if current_message:
                        messages.append(current_message.strip())
                    current_message = paragraph
                else:
                    # 不超过限制，添加到当前消息
                    current_message = test_message
        
        # 添加最后一个消息
        if current_message:
            messages.append(current_message.strip())
        
        return messages
    
    def send_to_discord(self, message_data: Dict) -> bool:
        """发送消息到Discord，支持附件和长消息分割
        
        Args:
            message_data: 包含消息内容和媒体文件的字典
            
        Returns:
            发送是否成功
        """
        try:
            webhook_url = self.config['discord_webhook_url']
            
            if webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
                self.logger.error("请在config.json中设置正确的Discord Webhook URL")
                return False
            
            timeout = self.config.get('timeout', 30)
            
            # 分割消息
            message_parts = self._split_message(message_data['content'])
            
            # 准备媒体文件（只在第一条消息中发送）
            files = []
            media_urls = message_data.get('media_urls', [])
            if media_urls:
                for i, media_url in enumerate(media_urls[:5]):  # 限制最多5个附件
                    try:
                        media_response = requests.get(
                            media_url, 
                            timeout=10,
                            proxies=self.proxies
                        )
                        if media_response.status_code == 200:
                            # 从URL获取文件扩展名
                            file_ext = media_url.split('.')[-1].split('?')[0]
                            if file_ext.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'avi']:
                                filename = f"media_{i+1}.{file_ext}"
                                files.append(('file', (filename, media_response.content)))
                                self.logger.info(f"准备发送附件: {filename}")
                    except Exception as e:
                        self.logger.warning(f"下载媒体文件失败 {media_url}: {e}")
                        continue
            
            # 发送所有消息部分
            all_success = True
            for i, message_part in enumerate(message_parts):
                data = {
                    'content': message_part,
                    'username': 'ZaihuaNews'
                }
                
                # 只在第一条消息中包含附件
                current_files = files if i == 0 else []
                
                # 发送消息
                if current_files:
                    # 有附件时使用multipart/form-data
                    response = requests.post(
                        webhook_url, 
                        data=data, 
                        files=current_files, 
                        timeout=timeout,
                        proxies=self.proxies
                    )
                else:
                    # 无附件时使用JSON
                    response = requests.post(
                        webhook_url, 
                        json=data, 
                        timeout=timeout,
                        proxies=self.proxies
                    )
                
                if response.status_code == 204 or response.status_code == 200:
                    if i == 0:
                        self.logger.info(f"消息第{i+1}部分发送成功，包含 {len(current_files)} 个附件")
                    else:
                        self.logger.info(f"消息第{i+1}部分发送成功")
                else:
                    self.logger.error(f"发送消息第{i+1}部分失败: {response.status_code} - {response.text}")
                    self.logger.error(f"消息内容: \n{message_part}")
                    all_success = False
                
                # 添加发送间隔，避免触发速率限制
                if i < len(message_parts) - 1:
                    time.sleep(1)
            
            if all_success:
                if len(message_parts) > 1:
                    self.logger.info(f"长消息已分{len(message_parts)}条发送完成")
                return True
            else:
                return False
                
        except Exception as e:
            self.logger.error(f"发送消息到Discord失败: {e}")
            return False
    
    def process_new_items(self, items: List[Dict]) -> int:
        """处理新文章
        
        Args:
            items: RSS文章列表
            
        Returns:
            成功处理的新文章数量
        """
        new_items_count = 0
        max_retries = self.config.get('max_retries', 3)
        
        for item in items:
            item_id = self._generate_item_id(item)
            
            # 检查是否已经发送过
            if item_id in self.sent_items:
                continue
            
            # 检查是否包含过滤关键词
            if self._should_filter_item(item):
                # 即使被过滤，也要记录到已发送列表中，避免重复检查
                self.sent_items.add(item_id)
                continue
            
            # 格式化消息
            message_data = self.format_message(item)
            
            # 尝试发送消息
            success = False
            for attempt in range(max_retries):
                if self.send_to_discord(message_data):
                    success = True
                    break
                else:
                    if attempt < max_retries - 1:
                        self.logger.warning(f"发送失败，{attempt + 1}/{max_retries} 次重试...")
                        time.sleep(2 ** attempt)  # 指数退避
            
            if success:
                # 记录已发送
                self.sent_items.add(item_id)
                new_items_count += 1
                self.logger.info(f"新文章已推送: {item.get('title', '无标题')}")
                
                # 添加发送间隔，避免触发速率限制
                time.sleep(1)
            else:
                self.logger.error(f"文章推送失败: {item.get('title', '无标题')}")
        
        # 保存已发送记录
        if new_items_count > 0:
            self._save_sent_items()
        
        return new_items_count
    
    def check_and_send(self):
        """检查RSS并发送新内容"""
        self.logger.info("开始检查RSS更新...")
        
        # 获取RSS内容
        items = self.fetch_rss_feed()
        if items is None:
            self.logger.error("获取RSS内容失败")
            return
        
        if not items:
            self.logger.info("没有找到新内容")
            return
        
        # 处理新文章
        new_count = self.process_new_items(items)
        
        if new_count > 0:
            self.logger.info(f"成功推送 {new_count} 篇新文章")
        else:
            self.logger.info("没有新文章需要推送")
    
    def run(self):
        """运行机器人"""
        self.logger.info("RSS Discord推送机器人启动")
        self.logger.info(f"RSS源: {self.config['rss_url']}")
        self.logger.info(f"检查间隔: {self.config.get('check_interval', 600)} 秒")
        
        # 显示过滤关键词信息
        filter_keywords = self.config.get('filter_keywords', [])
        if filter_keywords:
            self.logger.info(f"关键词过滤已启用，过滤词汇: {', '.join(filter_keywords)}")
        else:
            self.logger.info("关键词过滤已禁用")
        
        # 显示代理状态信息
        if self.proxies:
            proxy_info = []
            for protocol, url in self.proxies.items():
                # 隐藏认证信息以保护隐私
                display_url = url
                if '@' in url:
                    parts = url.split('@')
                    if len(parts) == 2:
                        scheme_auth = parts[0]
                        host_part = parts[1]
                        if '://' in scheme_auth:
                            scheme = scheme_auth.split('://')[0]
                            display_url = f"{scheme}://***:***@{host_part}"
                proxy_info.append(f"{protocol.upper()}: {display_url}")
            self.logger.info(f"网络代理已启用 - {', '.join(proxy_info)}")
        else:
            self.logger.info("网络代理已禁用")
        
        # 设置定时任务
        check_interval = self.config.get('check_interval', 600)
        schedule.every(check_interval).seconds.do(self.check_and_send)
        
        # 立即执行一次检查
        self.check_and_send()
        
        # 主循环
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("收到停止信号，正在关闭机器人...")
        except Exception as e:
            self.logger.error(f"运行时错误: {e}")
        finally:
            # 停止短链接服务器
            if self.url_shortener:
                self.url_shortener.stop()
            self.logger.info("RSS Discord推送机器人已停止")


def main():
    """主函数"""
    try:
        bot = RSSDiscordBot()
        bot.run()
    except Exception as e:
        print(f"启动失败: {e}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())