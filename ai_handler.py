#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Handler Module
负责调用 LLM 进行文章审核、规则提取和优化
"""

import json
import logging
import os
import time
import requests
from typing import Dict, List, Optional, Tuple

class AIHandler:
    """AI 处理器"""
    
    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.rules_file = "ai_rules.json"
        self.pending_feedback_file = "pending_feedback.json"
        self.feedback_history_file = "feedback_history.json"
        self.logger = logging.getLogger('RSSDiscordBot')
        
        self.config = self._load_config()
        self.rules = self._load_rules()
        
    def _load_config(self) -> Dict:
        """加载配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
                return full_config.get('ai_config', {})
        except Exception as e:
            self.logger.error(f"加载AI配置失败: {e}")
            return {}

    def _load_rules(self) -> List[str]:
        """加载规则"""
        if os.path.exists(self.rules_file):
            try:
                with open(self.rules_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('rules', [])
            except Exception as e:
                self.logger.error(f"加载规则失败: {e}")
        return []

    def save_rules(self, rules: List[str]):
        """保存规则"""
        try:
            self.rules = rules
            with open(self.rules_file, 'w', encoding='utf-8') as f:
                json.dump({'rules': rules, 'updated_at': time.time()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存规则失败: {e}")

    def _call_llm(self, messages: List[Dict], json_mode: bool = True, model_override: str = None) -> Optional[Dict]:
        """调用 LLM API"""
        if not self.config.get('enabled', False):
            return None

        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url', 'https://api.openai.com/v1')
        model = model_override or self.config.get('model', 'gpt-3.5-turbo')
        
        if not api_key:
            self.logger.error("未配置 AI API Key")
            return None

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3
        }
        
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            # 获取代理配置
            # 这里我们需要重新读取主配置文件来获取代理设置，或者让 RSSDiscordBot 传递进来
            # 为了简单，这里先尝试读取主配置文件中的代理
            proxies = {}
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    full_config = json.load(f)
                    proxy_config = full_config.get('proxy', {})
                    if proxy_config.get('enabled', False):
                        if proxy_config.get('http'): proxies['http'] = proxy_config['http']
                        if proxy_config.get('https'): proxies['https'] = proxy_config['https']
                        # 处理认证... (简化处理，假设 URL 已包含认证或无认证)
            except:
                pass

            response = requests.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            if json_mode:
                return json.loads(content)
            return content
            
        except Exception as e:
            self.logger.error(f"调用 LLM 失败: {e}")
            return None

    def check_article(self, title: str, summary: str) -> Tuple[bool, str]:
        """
        审核文章
        Returns: (是否推荐, 原因)
        """
        if not self.config.get('enabled', False):
            return True, "AI审核未启用"
            
        if not self.rules:
            return True, "无过滤规则"

        rules_text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(self.rules)])
        
        system_prompt = """你是一个严格的内容审核助手。你的任务是根据给定的规则判断一篇文章是否应该被推荐给用户。
请严格基于规则判断，不要加入个人的主观喜好。
如果文章违反了任何一条规则，请拒绝推荐。
请以 JSON 格式回答：
{
    "recommend": true/false,
    "reason": "如果不推荐，请简短说明违反了哪条规则；如果推荐，请填'符合规则'"
}"""

        user_prompt = f"""
当前过滤规则：
{rules_text}

待审核文章：
标题：{title}
摘要：{summary}
"""
        
        audit_model = self.config.get('audit_model')

        result = self._call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], model_override=audit_model)

        if result:
            return result.get('recommend', True), result.get('reason', '未知原因')
        
        return True, "AI调用失败，默认通过"

    def preprocess_article(self, title: str, summary: str) -> str:
        """
        预处理文章（总结、翻译等）
        Returns: 处理后的摘要
        """
        preprocessing_config = self.config.get('preprocessing', {})
        if not self.config.get('enabled', False) or not preprocessing_config.get('enabled', False):
            return summary

        custom_prompt = preprocessing_config.get('prompt', '请总结这篇文章的内容。')
        preprocessing_model = self.config.get('preprocessing_model')

        system_prompt = f"""你是一个文章处理助手。输入内容为 Markdown 格式，请以 Markdown 格式输出处理结果。
用户要求：{custom_prompt}

请直接返回处理后的文本内容，不要包含 JSON 格式或其他无关内容。"""

        user_prompt = f"""
文章标题：{title}
文章摘要：{summary}
"""

        result = self._call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], json_mode=False, model_override=preprocessing_model)

        if result:
            return result.strip()
        
        return summary

    def record_feedback(self, article_data: Dict):
        """记录用户反馈（不感兴趣的文章）"""
        pending = []
        if os.path.exists(self.pending_feedback_file):
            try:
                with open(self.pending_feedback_file, 'r', encoding='utf-8') as f:
                    pending = json.load(f)
            except:
                pass
        
        # 避免重复
        for item in pending:
            if item.get('link') == article_data.get('link'):
                return

        pending.append({
            'title': article_data.get('title', ''),
            'summary': article_data.get('summary', ''),
            'link': article_data.get('link', ''),
            'timestamp': time.time()
        })
        
        with open(self.pending_feedback_file, 'w', encoding='utf-8') as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"已记录用户反馈: {article_data.get('title')}")

    def get_pending_feedback(self) -> List[Dict]:
        """获取待处理的反馈"""
        if os.path.exists(self.pending_feedback_file):
            try:
                with open(self.pending_feedback_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []

    def optimize_rules(self):
        """优化规则（每12小时运行）"""
        if not self.config.get('enabled', False):
            return

        pending = []
        if os.path.exists(self.pending_feedback_file):
            try:
                with open(self.pending_feedback_file, 'r', encoding='utf-8') as f:
                    pending = json.load(f)
            except:
                pass
        
        if not pending:
            self.logger.info("没有新的反馈数据，跳过规则优化")
            return

        # 加载历史反馈标题
        history_titles = []
        if os.path.exists(self.feedback_history_file):
            try:
                with open(self.feedback_history_file, 'r', encoding='utf-8') as f:
                    history_titles = json.load(f)
            except:
                pass

        self.logger.info(f"开始分析 {len(pending)} 条新反馈并优化规则...")

        current_rules_text = "\n".join([f"- {r}" for i, r in enumerate(self.rules)]) if self.rules else "无"
        
        # 构建历史标题列表文本
        history_text = "\n".join([f"- {t}" for t in history_titles[-50:]]) # 只取最近50条历史，避免token过长
        if not history_text:
            history_text = "无"

        # 构建本次详细反馈文本
        feedback_text = ""
        for i, item in enumerate(pending):
            feedback_text += f"{i+1}. 标题：{item['title']}\n   摘要：{item['summary']}\n"

        system_prompt = """你是一个专业的新闻内容偏好分析师。用户会提供一系列他标记为“不感兴趣”的新闻文章。
你的任务是分析这些文章在**内容主题**上的共性，并生成一份过滤规则列表。

**核心原则**：
1. **只关注内容主题**：规则必须描述用户不感兴趣的**话题、领域、事件类型**（例如：“拒绝加密货币行情”、“拒绝娱乐明星八卦”、“拒绝苹果公司产品发布传闻”）。
2. **忽略形式与元数据**：**绝对不要**生成关于文章格式、排版、来源（如Telegram/Twitter）、表情符号、HTML标签、推广尾巴、链接形式等非内容属性的规则。即使这些文章有共同的格式特征，也请忽略，只关注它们讲了什么事情。
3. **规则具体化**：避免笼统的“拒绝垃圾信息”，而要具体到“拒绝博彩广告”或“拒绝无实质内容的社交媒体动态”。
4. **规则数量**：控制在 10-15 条以内，合并相似规则。

请基于提供的“历史不感兴趣标题”和“近期不感兴趣文章详情（含摘要）”，更新当前的过滤规则。

请以 JSON 格式回答：
{
    "rules": [
        "规则1",
        "规则2",
        ...
    ],
    "analysis": "简短的分析说明，解释为什么生成这些规则"
}"""

        user_prompt = f"""
当前已有规则：
{current_rules_text}

历史标记为“不感兴趣”的文章标题（仅供参考共性）：
{history_text}

近期新标记为“不感兴趣”的文章详情（重点分析）：
{feedback_text}

请生成优化后的规则列表。
"""
        
        optimization_model = self.config.get('optimization_model')

        result = self._call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ], model_override=optimization_model)

        if result and 'rules' in result:
            new_rules = result['rules']
            self.save_rules(new_rules)
            self.logger.info(f"规则优化完成，当前规则数: {len(new_rules)}")
            self.logger.info(f"分析报告: {result.get('analysis', '无')}")
            
            # 更新历史记录
            new_titles = [item['title'] for item in pending]
            # 去重合并
            updated_history = list(set(history_titles + new_titles))
            
            try:
                with open(self.feedback_history_file, 'w', encoding='utf-8') as f:
                    json.dump(updated_history, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.logger.error(f"保存历史反馈失败: {e}")
            
            # 清空已处理的反馈
            with open(self.pending_feedback_file, 'w', encoding='utf-8') as f:
                json.dump([], f)
        else:
            self.logger.error("规则优化失败: AI 未返回有效规则")
