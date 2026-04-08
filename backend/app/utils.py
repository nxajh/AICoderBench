"""
公共工具函数
"""
import re


def clean_thinking(text: str) -> str:
    """去除思考内容的标记标签（兼容多种模型格式）"""
    text = text.lstrip()
    text = re.sub(r'^[\u200b\u200c\u200d]*', '', text)
    text = re.sub(r'^\u200b\s*', '', text)
    text = re.sub(r'^◀think▶\s*', '', text)
    text = re.sub(r'^<think[^>]*>\s*', '', text)
    text = re.sub(r'\s*◀/think▶\s*$', '', text)
    text = re.sub(r'\s*</think\s*>\s*$', '', text)
    return text.strip()
