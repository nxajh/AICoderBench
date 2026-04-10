"""
模型 API 接入层
统一接口，支持 tool calling 和文本生成两种模式
"""
import json
import re
import logging
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# ---- 工具定义（tool calling） ----

WRITE_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "将代码写入指定文件路径",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径，如 solution.c"
                },
                "content": {
                    "type": "string",
                    "description": "文件完整内容"
                }
            },
            "required": ["path", "content"]
        }
    }
}

TOOLS = [WRITE_FILE_TOOL]


@dataclass
class GeneratedFile:
    path: str
    content: str


@dataclass
class GenerationResult:
    files: list[GeneratedFile]
    raw_output: str  # 原始输出，用于保存
    used_tool_call: bool  # 是否通过 tool calling 获取
    token_usage: dict = field(default_factory=dict)  # {"prompt_tokens": x, "completion_tokens": y, "total_tokens": z}


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
        """原始 chat 调用，返回 API 原始响应"""
        ...

    async def generate(self, prompt: str) -> GenerationResult:
        """
        生成代码，优先 tool calling，兜底文本解析
        """
        messages = [{"role": "user", "content": prompt}]

        # 尝试 tool calling
        try:
            resp = await self._chat(messages, tools=TOOLS, temperature=0, max_tokens=65536)
            files = self._extract_tool_call_files(resp)
            usage = resp.get("usage", {})
            if files:
                raw = json.dumps(resp, ensure_ascii=False)
                return GenerationResult(files=files, raw_output=raw, used_tool_call=True, token_usage=usage)
        except Exception as e:
            # 脱敏：从错误信息中移除 API key
            safe_msg = repr(e)
            if self.api_key:
                safe_msg = safe_msg.replace(self.api_key, "***")
            logger.warning(f"[{self.provider_id}] tool calling failed: {type(e).__name__}: {safe_msg}")

        # 兜底：纯文本生成 + 正则提取
        resp = await self._chat(messages, temperature=0, max_tokens=65536)
        usage = resp.get("usage", {})
        text = self._extract_text(resp)
        files = self._extract_code_blocks(text)

        # 如果没提取到代码块，尝试找 C 代码特征
        if not files:
            lines = text.split('\n')
            code_start = -1
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('#include') or stripped.startswith('typedef') or stripped.startswith('struct'):
                    code_start = i
                    break
            if code_start >= 0:
                code = '\n'.join(lines[code_start:])
                files = [GeneratedFile(path="solution.c", content=code.strip())]
            else:
                logger.warning(f"[{self.provider_id}] no C code found in output")
                files = []

        raw = text
        return GenerationResult(files=files, raw_output=raw, used_tool_call=False, token_usage=usage)

    def _extract_tool_call_files(self, resp: dict) -> list[GeneratedFile]:
        """从 tool call 响应中提取文件"""
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
                    files.append(GeneratedFile(
                        path=args["path"],
                        content=args["content"]
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue
        return files

    def _extract_text(self, resp: dict) -> str:
        """从普通响应中提取文本"""
        choices = resp.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""

    def _extract_code_blocks(self, text: str) -> list[GeneratedFile]:
        """从文本中提取 ```c ... ``` 代码块"""
        files = []
        import re as _re
        clean_text = _re.sub(r'(?:◀|<)think(?:▶|>).*?(?:◀|</)think(?:▶|>)', '', text, flags=_re.DOTALL)
        pattern = r"```(?:c|C|h|cpp)?\s*\n(.*?)```"
        matches = re.findall(pattern, clean_text, re.DOTALL)
        if len(matches) == 1:
            files.append(GeneratedFile(path="solution.c", content=matches[0].strip()))
        elif len(matches) > 1:
            best = max(matches, key=len)
            files.append(GeneratedFile(path="solution.c", content=best.strip()))
        return files


class GLMProvider(ModelProvider):
    @property
    def provider_id(self) -> str:
        return "glm-thinking" if self.thinking else "glm"

    def __init__(self, api_key: str, model: str, base_url: str, thinking: bool = False, max_tokens: int = 65536):
        super().__init__(api_key, model, base_url, max_tokens)
        self.thinking = thinking

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
            "thinking": {"type": "enabled", "clear_thinking": False} if self.thinking else {"type": "disabled"},
        }
        if tools:
            body["tools"] = tools
        client = await self._get_client()
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


class KimiProvider(ModelProvider):
    provider_id = "kimi"

    async def _chat(self, messages, tools=None, temperature=0, max_tokens=65535):
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
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


class OpenRouterProvider(ModelProvider):
    provider_id = "openrouter"

    async def _chat(self, messages, tools=None, temperature=0, max_tokens=65536):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/openai/openai-python",
            "X-Title": "AICoderBench",
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
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


class MiniMaxProvider(ModelProvider):
    provider_id = "minimax"

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
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

class OpenAIProvider(ModelProvider):
    """通用 OpenAI-compatible provider，适用于 DeepSeek、Qwen、Doubao 等标准接口。"""
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
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


# Provider 类型映射
PROVIDER_CLASS_MAP = {
    "glm": GLMProvider,
    "kimi": KimiProvider,
    "minimax": MiniMaxProvider,
    "openrouter": OpenRouterProvider,
    "openai": OpenAIProvider,
}


async def create_providers_from_db() -> dict[str, ModelProvider]:
    """从数据库创建已启用的模型 provider（所有配置从数据库读取）"""
    from ..database import list_model_configs, get_model_config
    providers = {}
    configs = await list_model_configs()

    for cfg in configs:
        if not cfg.get("enabled", True):
            continue
        full = await get_model_config(cfg["uuid"])
        if not full:
            continue

        ptype = full.get("provider_type", cfg.get("provider", ""))
        api_key = full.get("api_key", "")
        if not api_key:
            logger.warning(f"Skipping model uuid={cfg['uuid']}: no api_key configured")
            continue

        base_url = full.get("base_url", "")
        if not base_url:
            logger.warning(f"Skipping model uuid={cfg['uuid']}: no base_url configured")
            continue

        cls = PROVIDER_CLASS_MAP.get(ptype, OpenAIProvider)
        if not cls:
            continue

        try:
            kwargs = dict(api_key=api_key, model=full["model"], base_url=base_url,
                          max_tokens=int(full.get("max_tokens") or 65536))
            if cls == GLMProvider:
                kwargs["thinking"] = full.get("thinking", False)
            providers[cfg["uuid"]] = cls(**kwargs)
        except Exception as e:
            # 只记录异常类型，不记录异常消息（可能含 api_key）
            logger.warning(f"Failed to create provider uuid={cfg['uuid']}: {type(e).__name__}")
    return providers


def create_providers() -> dict[str, ModelProvider]:
    """已废弃：保留空实现避免 import 报错，请使用 create_providers_from_db()"""
    return {}
