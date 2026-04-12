"""
模型 API 接入层 — 支持 OpenAI-compatible 和 Anthropic 两种格式
"""
import json
import re
import logging
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ---- 工具定义（OpenAI tool calling 格式）----

WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "将代码写入指定文件路径",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径，如 solution.c"},
                "content": {"type": "string", "description": "文件完整内容"},
            },
            "required": ["path", "content"],
        },
    },
}

TOOLS = [WRITE_FILE_TOOL]

# Anthropic 格式的工具定义
ANTHROPIC_TOOLS = [
    {
        "name": "write_file",
        "description": "将代码写入指定文件路径",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径，如 solution.c"},
                "content": {"type": "string", "description": "文件完整内容"},
            },
            "required": ["path", "content"],
        },
    }
]


@dataclass
class GeneratedFile:
    path: str
    content: str


@dataclass
class GenerationResult:
    files: list[GeneratedFile]
    raw_output: str
    used_tool_call: bool
    token_usage: dict = field(default_factory=dict)


class ModelProvider(ABC):
    """模型接口基类"""

    _clients: dict[str, httpx.AsyncClient] = {}

    def __init__(self, api_key: str, model: str, base_url: str, max_tokens: int = 65536):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens

    async def _get_client(self) -> httpx.AsyncClient:
        key = f"{self.provider_id}:{self.base_url}"
        if key not in self._clients or self._clients[key].is_closed:
            self._clients[key] = httpx.AsyncClient(timeout=1800)
        return self._clients[key]

    @classmethod
    async def close_all(cls):
        for c in cls._clients.values():
            await c.aclose()
        cls._clients.clear()

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @abstractmethod
    async def _chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 8192,
    ) -> dict:
        """原始 chat 调用，返回标准化响应"""
        ...

    async def generate(self, prompt: str) -> GenerationResult:
        messages = [{"role": "user", "content": prompt}]
        try:
            resp = await self._chat(messages, tools=TOOLS, temperature=0, max_tokens=65536)
            files = self._extract_tool_call_files(resp)
            usage = resp.get("usage", {})
            if files:
                return GenerationResult(
                    files=files,
                    raw_output=json.dumps(resp, ensure_ascii=False),
                    used_tool_call=True,
                    token_usage=usage,
                )
        except Exception as e:
            safe_msg = repr(e)
            if self.api_key:
                safe_msg = safe_msg.replace(self.api_key, "***")
            logger.warning(f"[{self.provider_id}] tool calling failed: {type(e).__name__}: {safe_msg}")

        resp = await self._chat(messages, temperature=0, max_tokens=65536)
        usage = resp.get("usage", {})
        text = self._extract_text(resp)
        files = self._extract_code_blocks(text)

        if not files:
            lines = text.split("\n")
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#include") or stripped.startswith("typedef") or stripped.startswith("struct"):
                    code = "\n".join(lines[i:])
                    files = [GeneratedFile(path="solution.c", content=code.strip())]
                    break

        if not files:
            logger.warning(f"[{self.provider_id}] no C code found in output")

        return GenerationResult(files=files, raw_output=text, used_tool_call=False, token_usage=usage)

    def _extract_tool_call_files(self, resp: dict) -> list[GeneratedFile]:
        files = []
        choices = resp.get("choices", [])
        if not choices:
            return files
        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        for tc in tool_calls:
            fn = tc.get("function", {})
            if fn.get("name") == "write_file":
                try:
                    args = json.loads(fn["arguments"])
                    files.append(GeneratedFile(path=args["path"], content=args["content"]))
                except (json.JSONDecodeError, KeyError):
                    continue
        return files

    def _extract_text(self, resp: dict) -> str:
        choices = resp.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""

    def _extract_code_blocks(self, text: str) -> list[GeneratedFile]:
        clean_text = re.sub(r"(?:◀|<)think(?:▶|>).*?(?:◀|</)think(?:▶|>)", "", text, flags=re.DOTALL)
        pattern = r"```(?:c|C|h|cpp)?\s*\n(.*?)```"
        matches = re.findall(pattern, clean_text, re.DOTALL)
        if len(matches) == 1:
            return [GeneratedFile(path="solution.c", content=matches[0].strip())]
        elif len(matches) > 1:
            best = max(matches, key=len)
            return [GeneratedFile(path="solution.c", content=best.strip())]
        return []


class OpenAIProvider(ModelProvider):
    """标准 OpenAI-compatible provider（DeepSeek、Qwen、Kimi、GLM 等均可用此）"""
    provider_id = "openai"

    async def _chat(self, messages, tools=None, temperature=0, max_tokens=65536):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
        client = await self._get_client()
        resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()


class AnthropicProvider(ModelProvider):
    """Anthropic Messages API（支持 extended thinking，适用于 Claude 及兼容 Anthropic 格式的厂商）"""
    provider_id = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str,
                 thinking: bool = False, thinking_budget: int = 10000, max_tokens: int = 65536):
        super().__init__(api_key, model, base_url, max_tokens)
        self.thinking = thinking
        self.thinking_budget = thinking_budget

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """将 OpenAI function calling 格式转为 Anthropic tool 格式"""
        result = []
        for t in tools:
            if t.get("type") == "function":
                # OpenAI 格式: {"type": "function", "function": {"name": ..., "parameters": ...}}
                fn = t["function"]
                result.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            elif "name" in t and "input_schema" in t:
                # 已经是 Anthropic 格式，原样保留
                result.append(t)
            else:
                result.append(t)
        return result

    @staticmethod
    def _convert_messages(messages: list[dict]) -> list[dict]:
        """将 OpenAI 格式的 messages 列表转为 Anthropic Messages API 格式"""
        result = []
        i = 0
        while i < len(messages):
            m = messages[i]
            role = m.get("role", "")

            if role == "user":
                content = m.get("content", "")
                result.append({"role": "user", "content": content})
                i += 1

            elif role == "assistant":
                tool_calls = m.get("tool_calls", [])
                text = m.get("content") or ""
                content_blocks: list[dict] = []
                # thinking blocks 必须在 text/tool_use 之前（Anthropic 要求）
                # 优先使用保留了 signature 的原始 blocks，回退到纯文本重建
                raw_thinking_blocks = m.get("thinking_blocks")
                if raw_thinking_blocks:
                    content_blocks.extend(raw_thinking_blocks)
                elif m.get("reasoning_content"):
                    content_blocks.append({"type": "thinking", "thinking": m["reasoning_content"]})
                if text:
                    content_blocks.append({"type": "text", "text": text})
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    args_str = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args,
                    })
                result.append({
                    "role": "assistant",
                    "content": content_blocks if content_blocks else [{"type": "text", "text": ""}],
                })
                i += 1

            elif role == "tool":
                # 收集连续的 tool 消息，合并为一条 user 消息中的 tool_result 块
                tool_results = []
                while i < len(messages) and messages[i].get("role") == "tool":
                    tr = messages[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tr.get("tool_call_id", ""),
                        "content": tr.get("content", ""),
                    })
                    i += 1
                result.append({"role": "user", "content": tool_results})

            else:
                i += 1

        return result

    async def _chat(self, messages, tools=None, temperature=0, max_tokens=65536):
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        # 将 system 消息从 messages 中分离，其余转为 Anthropic 格式
        system = ""
        non_system = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                non_system.append(m)
        filtered_messages = self._convert_messages(non_system)

        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": filtered_messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = self._convert_tools(tools)  # 自动转换 OpenAI 格式 → Anthropic 格式
        if self.thinking:
            # 开启 extended thinking 时不能设置 temperature
            body["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
        else:
            body["temperature"] = temperature

        client = await self._get_client()
        base = self.base_url or "https://api.anthropic.com"
        resp = await client.post(f"{base}/v1/messages", headers=headers, json=body)
        resp.raise_for_status()
        raw = resp.json()
        # 将 Anthropic 响应格式转为内部统一格式
        return self._normalize_response(raw)

    def _normalize_response(self, raw: dict) -> dict:
        """将 Anthropic 响应转为与 OpenAI 兼容的内部格式"""
        content_blocks = raw.get("content", [])
        text_parts = []
        thinking_blocks: list[dict] = []   # 保留完整 block（含 signature）
        tool_calls = []

        for block in content_blocks:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "thinking":
                # 保留完整 block，包括 Anthropic 要求在多轮对话中回传的 signature
                thinking_blocks.append({
                    "type": "thinking",
                    "thinking": block.get("thinking", ""),
                    "signature": block.get("signature", ""),
                })
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        message: dict = {"role": "assistant", "content": "\n".join(text_parts)}
        if tool_calls:
            message["tool_calls"] = tool_calls
        if thinking_blocks:
            # thinking_blocks 用于多轮回传（含 signature）
            # reasoning_content 仅供 agent_runner 提取可读文本用于 history 记录
            message["thinking_blocks"] = thinking_blocks
            message["reasoning_content"] = "\n".join(b["thinking"] for b in thinking_blocks)

        usage = raw.get("usage", {})
        return {
            "choices": [{"message": message, "finish_reason": raw.get("stop_reason", "")}],
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
        }


# ---- Provider 工厂 ----

async def create_providers_from_db() -> dict[str, ModelProvider]:
    """从数据库创建已启用模型的 provider 实例，key = model.uuid"""
    from ..database import list_model_configs, get_model_config
    providers = {}
    configs = await list_model_configs()

    for cfg in configs:
        if not cfg.get("enabled", True):
            continue
        full = await get_model_config(cfg["uuid"])
        if not full:
            continue

        api_key = full.get("api_key", "")
        base_url = full.get("base_url", "")
        api_format = full.get("api_format", "openai")
        model_id = full.get("model_id", "")
        max_tokens = int(full.get("max_tokens") or 65536)

        if not api_key:
            logger.warning(f"Skipping model {cfg['uuid']}: no api_key")
            continue
        if not model_id:
            logger.warning(f"Skipping model {cfg['uuid']}: no model_id")
            continue

        try:
            if api_format == "anthropic":
                providers[cfg["uuid"]] = AnthropicProvider(
                    api_key=api_key,
                    model=model_id,
                    base_url=base_url,
                    thinking=full.get("thinking", False),
                    thinking_budget=int(full.get("thinking_budget") or 10000),
                    max_tokens=max_tokens,
                )
            else:
                providers[cfg["uuid"]] = OpenAIProvider(
                    api_key=api_key,
                    model=model_id,
                    base_url=base_url,
                    max_tokens=max_tokens,
                )
        except Exception as e:
            logger.warning(f"Failed to create provider for model {cfg['uuid']}: {type(e).__name__}")

    return providers


def create_providers() -> dict[str, ModelProvider]:
    """已废弃：保留空实现避免 import 报错"""
    return {}
