#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
URL Shortener Service
短链接服务器，提供链接缩短和重定向功能
"""

import json
import logging
import os
import random
import string
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


class URLShortener:
    """短链接管理器"""
    
    def __init__(self, storage_file='url_mappings.json'):
        self.storage_file = storage_file
        self.url_mappings = self.load_mappings()
        self.reverse_mappings = {v: k for k, v in self.url_mappings.items()}
        self.lock = threading.Lock()
        
    def load_mappings(self):
        """加载已存储的URL映射"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"加载URL映射失败: {e}")
        return {}
    
    def save_mappings(self):
        """保存URL映射到文件"""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.url_mappings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存URL映射失败: {e}")
    
    def generate_short_code(self, length=4):
        """生成短链接代码"""
        characters = string.ascii_letters + string.digits
        while True:
            code = ''.join(random.choice(characters) for _ in range(length))
            if code not in self.url_mappings:
                return code
    
    def shorten_url(self, long_url):
        """缩短URL"""
        with self.lock:
            # 检查是否已经存在
            if long_url in self.reverse_mappings:
                return self.reverse_mappings[long_url]
            
            # 生成新的短代码
            short_code = self.generate_short_code()
            self.url_mappings[short_code] = long_url
            self.reverse_mappings[long_url] = short_code
            
            # 保存到文件
            self.save_mappings()
            
            return short_code
    
    def get_long_url(self, short_code):
        """获取原始URL"""
        return self.url_mappings.get(short_code)


class ShortenerHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器"""
    
    def __init__(self, *args, shortener=None, **kwargs):
        self.shortener = shortener
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """处理GET请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path.strip('/)')
        
        if not path:
            # 根路径，显示服务状态
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            response = ""
            self.wfile.write(response.encode('utf-8'))
            return
        
        # 查找短链接
        long_url = self.shortener.get_long_url(path)
        if long_url:
            # 重定向到原始URL
            self.send_response(302)
            self.send_header('Location', long_url)
            self.end_headers()
            logging.info(f"重定向: {path} -> {long_url}")
        else:
            # 短链接不存在
            self.send_response(404)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'<h1>404 - Short URL Not Found</h1>')
    
    def do_POST(self):
        """处理POST请求"""
        if self.path == '/shorten':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                long_url = data.get('url')
                if not long_url:
                    self.send_error(400, 'Missing URL parameter')
                    return
                
                short_code = self.shortener.shorten_url(long_url)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                
                response = {
                    'short_code': short_code,
                    'original_url': long_url
                }
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
                logging.info(f"创建短链接: {long_url} -> {short_code}")
                
            except Exception as e:
                logging.error(f"处理POST请求失败: {e}")
                self.send_error(500, str(e))
        else:
            self.send_error(404, 'Endpoint not found')
    
    def log_message(self, format, *args):
        """重写日志方法，避免默认日志输出"""
        pass


class URLShortenerServer:
    """短链接服务器"""
    
    def __init__(self, host='localhost', port=8080):
        self.host = host
        self.port = port
        self.shortener = URLShortener()
        self.server = None
        self.server_thread = None
        
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
    
    def create_handler(self, *args, **kwargs):
        """创建请求处理器"""
        return ShortenerHandler(*args, shortener=self.shortener, **kwargs)
    
    def start(self):
        """启动服务器"""
        try:
            self.server = HTTPServer((self.host, self.port), self.create_handler)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            logging.info(f"短链接服务器启动成功: http://{self.host}:{self.port}")
            return True
        except Exception as e:
            logging.error(f"启动服务器失败: {e}")
            return False
    
    def stop(self):
        """停止服务器"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logging.info("短链接服务器已停止")
    
    def shorten_url(self, long_url):
        """缩短URL（外部接口）"""
        return self.shortener.shorten_url(long_url)


if __name__ == '__main__':
    # 独立运行服务器
    import argparse
    
    parser = argparse.ArgumentParser(description='URL Shortener Server')
    parser.add_argument('--host', default='localhost', help='服务器主机')
    parser.add_argument('--port', type=int, default=8080, help='服务器端口')
    
    args = parser.parse_args()
    
    server = URLShortenerServer(args.host, args.port)
    
    if server.start():
        try:
            print(f"短链接服务器运行在 http://{args.host}:{args.port}")
            print("按 Ctrl+C 停止服务器")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n正在停止服务器...")
            server.stop()
    else:
        print("服务器启动失败")