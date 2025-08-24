> [!NOTE]
> 本项目由 Claude 4 Sonnet 编写。

# Discord Webhook RSS

一个自动化工具，定期检查RSS源并将新内容推送到Discord频道。

## 功能特性

- 🔄 每10分钟自动检查RSS更新
- 📰 将RSS内容格式化为Markdown消息推送到Discord
- 🖼️ 支持图片和视频附件自动下载和发送
- 🔗 内置短链接服务，自动缩短消息中的长链接
- 🚫 避免重复推送已发送的内容
- 📝 详细的日志记录和错误处理
- ⚙️ 可配置的检查间隔和重试机制

## 安装和配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置Discord Webhook

1. 在Discord服务器中创建一个频道
2. 右键点击频道 → 编辑频道 → 整合 → Webhook
3. 创建新的Webhook并复制URL
4. 编辑 `config.json` 文件，将 `YOUR_DISCORD_WEBHOOK_URL_HERE` 替换为实际的Webhook URL

### 3. 配置文件说明

编辑 `config.json` 文件：

```json
{
    "rss_url": "https://rss.ovh/telegram/channel/ZaihuaNews",
    "discord_webhook_url": "YOUR_DISCORD_WEBHOOK_URL_HERE",
    "check_interval": 600,
    "log_level": "INFO",
    "max_retries": 3,
    "timeout": 30,
    "url_shortener": {
        "enabled": true,
        "domain": "http://localhost:8080",
        "host": "localhost",
        "port": 8080
    }
}
```

配置项说明：
- `rss_url`: RSS源地址
- `discord_webhook_url`: Discord Webhook URL（必须配置）
- `check_interval`: 检查间隔（秒），默认600秒（10分钟）
- `log_level`: 日志级别（DEBUG, INFO, WARNING, ERROR）
- `max_retries`: 发送失败时的最大重试次数
- `timeout`: 网络请求超时时间（秒）
- `url_shortener`: 短链接服务配置
  - `enabled`: 是否启用短链接服务
  - `domain`: 短链接域名（可配置为公网域名）
  - `host`: 短链接服务器监听地址
  - `port`: 短链接服务器端口

## 运行

```bash
python rss_discord_bot.py
```

## 文件说明

- `rss_discord_bot.py`: 主程序文件
- `url_shortener.py`: 短链接服务器
- `config.json`: 配置文件
- `requirements.txt`: Python依赖列表
- `sent_items.json`: 已发送文章记录（自动生成）
- `url_mappings.json`: 短链接映射记录（自动生成）
- `rss_discord_bot.log`: RSS机器人运行日志（自动生成）
- `url_shortener.log`: 短链接服务器日志（自动生成）

## 日志

程序会在控制台和 `rss_discord_bot.log` 文件中记录运行日志，包括：
- RSS检查状态
- 新文章推送情况
- 错误信息和重试记录
- 程序启动和停止信息

## 停止程序

按 `Ctrl+C` 停止程序运行。

## 注意事项

1. 确保Discord Webhook URL配置正确
2. 程序会自动避免重复推送相同的文章
3. 网络异常时程序会自动重试
4. 建议在服务器上使用进程管理工具（如systemd、supervisor）来保持程序持续运行

## 故障排除

### 常见问题

1. **配置文件错误**
   - 检查 `config.json` 格式是否正确
   - 确保Discord Webhook URL已正确配置

2. **网络连接问题**
   - 检查RSS源是否可访问
   - 确认网络连接正常
   - 某些RSS源可能有访问限制，程序已添加User-Agent头来模拟浏览器访问

3. **RSS源访问被拒绝（403错误）**
   - 某些RSS服务（如RSSHub）可能对访问频率有限制
   - 可以尝试使用其他RSS源进行测试

4. **Discord推送失败**
   - 验证Webhook URL是否有效
   - 检查Discord服务器权限设置

## 技术架构

- **RSS解析**: 使用 `feedparser` 库解析RSS XML
- **HTML处理**: 自动将HTML内容转换为Markdown格式
- **媒体处理**: 自动提取并下载图片/视频作为Discord附件
- **短链接服务**: 内置HTTP服务器提供4字符短链接生成和重定向
- **HTTP请求**: 使用 `requests` 库发送Discord Webhook请求
- **定时任务**: 使用 `schedule` 库实现定时检查
- **数据存储**: 使用JSON文件存储已发送文章记录和短链接映射
- **日志记录**: 使用Python标准库 `logging` 模块

## 短链接服务

短链接服务是一个内置的HTTP服务器，提供以下功能：

### 特性
- 🔗 自动缩短消息中的所有长链接
- 📏 生成4字符的短链接代码
- 🔄 支持重定向到原始URL
- 💾 持久化存储链接映射
- 🌐 可配置域名（支持公网域名）
- 📊 提供服务状态页面

### API接口

**缩短链接**
```bash
POST http://localhost:8080/shorten
Content-Type: application/json

{
  "url": "https://example.com/very/long/url"
}
```

**访问短链接**
```bash
GET http://localhost:8080/{short_code}
# 自动重定向到原始URL
```

**服务状态**
```bash
GET http://localhost:8080/
# 显示服务状态和统计信息
```

### 配置说明

短链接服务可以通过配置文件进行自定义：

- `enabled`: 启用/禁用短链接服务
- `domain`: 短链接域名（可配置为公网域名，如 `https://yourdomain.com`）
- `host`: 服务器监听地址（通常为 `localhost` 或 `0.0.0.0`）
- `port`: 服务器端口

### 公网部署

如果需要在公网使用短链接服务：

1. 将 `host` 设置为 `0.0.0.0`
2. 配置防火墙开放对应端口
3. 将 `domain` 设置为你的公网域名
4. 可选：配置反向代理（如Nginx）提供HTTPS支持