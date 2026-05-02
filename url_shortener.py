#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URL Shortener & Feedback Service
短链接服务器，提供链接缩短、重定向、反馈收集和规则管理功能
"""

import json
import logging
import os
import random
import string
import threading
import time
import uuid
import re
import requests
from html import escape
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from ai_handler import AIHandler

# HTML 模板
FEEDBACK_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>反馈确认</title>
    <style>
        body {{ font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .card {{ border: 1px solid #ddd; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h2 {{ margin-top: 0; }}
        .summary {{ color: #666; line-height: 1.6; }}
        .btn {{ display: inline-block; padding: 10px 20px; background-color: #d9534f; color: white; text-decoration: none; border-radius: 4px; border: none; cursor: pointer; font-size: 16px; }}
        .btn:hover {{ background-color: #c9302c; }}
        .success {{ color: green; display: none; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>确认不感兴趣？</h2>
        <p>您将标记以下内容为"不感兴趣"，AI 将学习您的偏好。</p>
        <hr>
        <h3>{title}</h3>
        <p class="summary">{summary}</p>
        <form action="/submit_feedback" method="post">
            <input type="hidden" name="id" value="{id}">
            <button type="submit" class="btn">确认不感兴趣</button>
        </form>
    </div>
</body>
</html>
"""

SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>反馈成功</title>
    <style>
        body {{ font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; text-align: center; }}
        h2 {{ color: green; }}
    </style>
</head>
<body>
    <h2>✅ 反馈已记录</h2>
    <p>AI 将在下次规则优化时参考您的反馈。</p>
    <p><a href="javascript:window.close()">关闭页面</a></p>
</body>
</html>
"""

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>管理登录</title>
    <style>
        body {{ font-family: sans-serif; max-width: 400px; margin: 0 auto; padding: 50px 20px; }}
        form {{ border: 1px solid #ddd; padding: 20px; border-radius: 8px; }}
        input {{ width: 100%; padding: 8px; margin: 10px 0; box-sizing: border-box; }}
        button {{ width: 100%; padding: 10px; background-color: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        button:hover {{ background-color: #0056b3; }}
    </style>
</head>
<body>
    <form action="/admin/login" method="post">
        <h2>管理员登录</h2>
        <input type="password" name="password" placeholder="请输入密码" required>
        <button type="submit">登录</button>
    </form>
</body>
</html>
"""

RULES_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>规则管理</title>
    <style>
        body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ background: #f9f9f9; margin: 10px 0; padding: 15px; border-radius: 4px; display: flex; justify-content: space-between; align-items: center; }}
        .delete-btn {{ background-color: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; }}
        .add-form {{ margin-top: 20px; padding: 20px; background: #eee; border-radius: 4px; }}
        input[type="text"] {{ width: 70%; padding: 8px; }}
        .add-btn {{ background-color: #28a745; color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; }}
        .optimize-btn {{ background-color: #17a2b8; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 16px; margin-bottom: 20px; }}
        .feedback-list {{ margin-top: 30px; border-top: 1px solid #ddd; padding-top: 20px; }}
        .feedback-item {{ background: #fff3cd; margin: 5px 0; padding: 10px; border-radius: 4px; }}
    </style>
</head>
<body>
    <h2>AI 过滤规则管理</h2>
    
    <form action="/admin/rules/optimize" method="post" style="margin-bottom: 20px;">
        <button type="submit" class="optimize-btn">⚡ 立即根据反馈优化规则</button>
    </form>

    <h3>当前规则 ({count} 条)</h3>
    <ul>
        {rules_list}
    </ul>
    
    <div class="add-form">
        <h3>添加新规则</h3>
        <form action="/admin/rules/add" method="post">
            <input type="text" name="rule" placeholder="输入新规则..." required>
            <button type="submit" class="add-btn">添加</button>
        </form>
    </div>

    <div class="feedback-list">
        <h3>待处理反馈 ({feedback_count} 条)</h3>
        <p style="color: #666; font-size: 0.9em;">这些文章已被标记为"不感兴趣"，将在下次优化时被 AI 分析。</p>
        {feedback_list}
    </div>

    <p><a href="/admin/logout">退出登录</a></p>
</body>
</html>
"""

class URLShortener:
    """短链接和缓存管理器"""
    
    def __init__(self, storage_file='url_mappings.json', cache_file='item_cache.json'):
        self.storage_file = storage_file
        self.cache_file = cache_file
        self.url_mappings = self.load_json(self.storage_file)
        self.item_cache = self.load_json(self.cache_file)
        self.reverse_mappings = {v: k for k, v in self.url_mappings.items()}
        self.lock = threading.Lock()
        
    def load_json(self, filename):
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"加载 {filename} 失败: {e}")
        return {}
    
    def save_json(self, filename, data):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存 {filename} 失败: {e}")
    
    def generate_short_code(self, length=4):
        characters = string.ascii_letters + string.digits
        while True:
            code = ''.join(random.choice(characters) for _ in range(length))
            if code not in self.url_mappings:
                return code
    
    def shorten_url(self, long_url):
        with self.lock:
            if long_url in self.reverse_mappings:
                return self.reverse_mappings[long_url]
            
            short_code = self.generate_short_code()
            self.url_mappings[short_code] = long_url
            self.reverse_mappings[long_url] = short_code
            self.save_json(self.storage_file, self.url_mappings)
            return short_code
    
    def get_long_url(self, short_code):
        return self.url_mappings.get(short_code)

    def cache_item(self, item_data):
        """缓存文章信息，返回ID"""
        with self.lock:
            # 生成短ID (6位随机字符)
            # 为了避免冲突，尝试生成直到唯一
            for _ in range(10):
                item_id = self.generate_short_code(length=6)
                if item_id not in self.item_cache:
                    break
            else:
                # 如果实在找不到（极低概率），回退到 UUID
                item_id = uuid.uuid4().hex[:8]
            
            self.item_cache[item_id] = {
                'title': item_data.get('title', ''),
                'summary': item_data.get('summary', ''),
                'link': item_data.get('link', ''),
                'timestamp': time.time()
            }
            
            # 简单的清理逻辑：如果超过100条，删除旧的
            if len(self.item_cache) > 100:
                sorted_items = sorted(self.item_cache.items(), key=lambda x: x[1]['timestamp'])
                self.item_cache = dict(sorted_items[-80:]) # 保留最新的80条
            
            self.save_json(self.cache_file, self.item_cache)
            return item_id

    def get_cached_item(self, item_id):
        return self.item_cache.get(item_id)


class WebHandler(BaseHTTPRequestHandler):
    """Web请求处理器"""
    
    SESSIONS = {}  # 简单的内存Session存储
    
    def __init__(self, *args, shortener=None, ai_handler=None, admin_password=None, webhook_url=None, proxies=None, **kwargs):
        self.shortener = shortener
        self.ai_handler = ai_handler
        self.admin_password = admin_password
        self.webhook_url = webhook_url
        self.proxies = proxies
        super().__init__(*args, **kwargs)
    
    def _clean_id(self, raw_id):
        """清理ID，移除非字母数字字符"""
        if not raw_id:
            return ""
        return re.sub(r'[^a-zA-Z0-9]', '', raw_id)
    
    def _send_html(self, content, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def _redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def _check_auth(self):
        """检查Cookie验证"""
        if 'Cookie' in self.headers:
            c = cookies.SimpleCookie(self.headers['Cookie'])
            if 'session_id' in c:
                session_id = c['session_id'].value
                if session_id in self.SESSIONS:
                    # 检查过期 (24小时)
                    if time.time() - self.SESSIONS[session_id] < 86400:
                        return True
        return False

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path.strip('/')
        query = parse_qs(parsed_path.query)
        
        if path == 'feedback' or path == 'f':
            item_id = self._clean_id(query.get('id', [''])[0])
            item = self.shortener.get_cached_item(item_id)
            if item:
                html = FEEDBACK_TEMPLATE.format(
                    title=escape(item['title']),
                    summary=escape(item['summary'] + '...'),
                    id=item_id
                )
                self._send_html(html)
            else:
                self._send_html("<h1>文章已过期或不存在</h1>", 404)
                
        elif path == 'admin/login':
            self._send_html(LOGIN_TEMPLATE)
            
        elif path == 'admin/logout':
            # 清除 session (这里简单处理，不清除 cookie，只是让 session 失效)
            self._redirect('/admin/login')

        elif path == 'admin/rules':
            if not self._check_auth():
                self._redirect('/admin/login')
                return
            
            rules = self.ai_handler.rules
            rules_html = ""
            for i, rule in enumerate(rules):
                escaped_rule = escape(rule)
                rules_html += f"""
                <li>
                    <span>{i+1}. {escaped_rule}</span>
                    <form action="/admin/rules/delete" method="post" style="display:inline; margin:0;">
                        <input type="hidden" name="index" value="{i}">
                        <button type="submit" class="delete-btn">删除</button>
                    </form>
                </li>
                """
            
            # 获取待处理反馈
            pending_feedback = self.ai_handler.get_pending_feedback()
            feedback_html = ""
            if pending_feedback:
                for item in pending_feedback:
                    title = escape(item.get('title', '无标题'))
                    link = escape(item.get('link', ''))
                    feedback_html += f"""
                    <div class="feedback-item">
                        <strong>{title}</strong><br>
                        <span style="font-size: 0.8em; color: #666;">{link}</span>
                    </div>
                    """
            else:
                feedback_html = "<p>暂无待处理反馈</p>"
            
            html = RULES_TEMPLATE.format(
                count=len(rules), 
                rules_list=rules_html,
                feedback_count=len(pending_feedback),
                feedback_list=feedback_html
            )
            self._send_html(html)
            
        elif not path:
            self._send_html("<h1>RSS Bot Service Running</h1>")
            
        else:
            # 尝试作为短链接处理
            clean_path = self._clean_id(path)
            long_url = self.shortener.get_long_url(clean_path)
            if long_url:
                self._redirect(long_url)
            else:
                self._send_html("<h1>404 - Not Found</h1>", 404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        if self.path == '/shorten':
            # API 接口
            try:
                data = json.loads(post_data.decode('utf-8'))
                long_url = data.get('url')
                if not long_url:
                    self.send_error(400, 'Missing URL')
                    return
                short_code = self.shortener.shorten_url(long_url)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'short_code': short_code, 'original_url': long_url}).encode('utf-8'))
            except Exception as e:
                self.send_error(500, str(e))
                
        elif self.path == '/submit_feedback':
            # 表单提交
            data = parse_qs(post_data.decode('utf-8'))
            item_id = self._clean_id(data.get('id', [''])[0])
            item = self.shortener.get_cached_item(item_id)
            if item:
                self.ai_handler.record_feedback(item)
                
                # 发送通知
                if self.webhook_url:
                    def send_notify():
                        try:
                            payload = {"content": f"🚫 已标记不感兴趣：{item.get('title', '无标题')}"}
                            requests.post(self.webhook_url, json=payload, proxies=self.proxies, timeout=10)
                        except Exception as e:
                            logging.error(f"发送反馈通知失败: {e}")
                    threading.Thread(target=send_notify).start()
                    
                self._send_html(SUCCESS_TEMPLATE)
            else:
                self._send_html("<h1>Error: Item not found</h1>", 404)
                
        elif self.path == '/admin/login':
            data = parse_qs(post_data.decode('utf-8'))
            password = data.get('password', [''])[0]
            
            if password == self.admin_password:
                session_id = str(uuid.uuid4())
                self.SESSIONS[session_id] = time.time()
                
                self.send_response(302)
                self.send_header('Location', '/admin/rules')
                self.send_header('Set-Cookie', f'session_id={session_id}; Path=/; HttpOnly')
                self.end_headers()
            else:
                self._send_html("<h1>密码错误</h1><a href='/admin/login'>重试</a>", 401)
                
        elif self.path == '/admin/rules/add':
            if not self._check_auth():
                self._redirect('/admin/login')
                return
            data = parse_qs(post_data.decode('utf-8'))
            rule = data.get('rule', [''])[0].strip()
            if rule:
                self.ai_handler.rules.append(rule)
                self.ai_handler.save_rules(self.ai_handler.rules)
            self._redirect('/admin/rules')
            
        elif self.path == '/admin/rules/delete':
            if not self._check_auth():
                self._redirect('/admin/login')
                return
            data = parse_qs(post_data.decode('utf-8'))
            try:
                index = int(data.get('index', ['-1'])[0])
                if 0 <= index < len(self.ai_handler.rules):
                    self.ai_handler.rules.pop(index)
                    self.ai_handler.save_rules(self.ai_handler.rules)
            except:
                pass
            self._redirect('/admin/rules')
            
        elif self.path == '/admin/rules/optimize':
            if not self._check_auth():
                self._redirect('/admin/login')
                return
            # 触发规则优化
            threading.Thread(target=self.ai_handler.optimize_rules).start()
            # 稍微等待一下，或者直接重定向，让用户刷新查看结果
            # 这里直接重定向，优化是异步的，可能还没完成，但UI会显示正在处理（如果加状态的话）
            # 简单起见，直接重定向
            self._redirect('/admin/rules')
            
        else:
            self.send_error(404)
            
    def log_message(self, format, *args):
        pass


class URLShortenerServer:
    """短链接服务器"""
    
    def __init__(self, host='localhost', port=8080, ai_handler=None, admin_password="admin", webhook_url=None, proxies=None):
        self.host = host
        self.port = port
        self.shortener = URLShortener()
        self.ai_handler = ai_handler
        self.admin_password = admin_password
        self.webhook_url = webhook_url
        self.proxies = proxies
        self.server = None
        self.server_thread = None
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
    
    def create_handler(self, *args, **kwargs):
        return WebHandler(*args, shortener=self.shortener, ai_handler=self.ai_handler, admin_password=self.admin_password, webhook_url=self.webhook_url, proxies=self.proxies, **kwargs)
    
    def start(self):
        try:
            self.server = HTTPServer((self.host, self.port), self.create_handler)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            logging.info(f"Web服务器启动成功: http://{self.host}:{self.port}")
            return True
        except Exception as e:
            logging.error(f"启动服务器失败: {e}")
            return False
    
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logging.info("Web服务器已停止")
    
    def shorten_url(self, long_url):
        return self.shortener.shorten_url(long_url)
    
    def cache_item(self, item_data):
        return self.shortener.cache_item(item_data)

if __name__ == '__main__':
    # 简单的测试运行
    server = URLShortenerServer()
    server.start()
    while True:
        time.sleep(1)
