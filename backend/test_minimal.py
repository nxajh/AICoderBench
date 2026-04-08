#!/usr/bin/env python3
"""最小化测试：思考模式 + tools vs 思考模式无 tools"""
import asyncio, json, os, sys, time, httpx
sys.stdout.reconfigure(line_buffering=True)
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

API_KEY = os.getenv("GLM_API_KEY")
MODEL = os.getenv("GLM_MODEL", "glm-5.1")
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"

TOOLS = [
    {"type": "function", "function": {
        "name": "write_file",
        "description": "写入文件",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}
    }},
]

SIMPLE_PROMPT = "请用C语言实现一个简单的 add(int a, int b) 函数，使用 write_file 工具写入 solution.c。"

# 用一个中等长度的 prompt (agent prompt)
from app.models.problem import load_problem, _find_problem_dir
from app.scheduler.agent_runner import _build_agent_prompt
problem = load_problem("03-interpreter")
problem_dir = _find_problem_dir(problem.id)
AGENT_PROMPT = _build_agent_prompt(problem, problem_dir)


async def test(label, prompt, use_tools, timeout=300):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    
    thinking_config = {"type": "enabled", "clear_thinking": False}
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 131072,
        "thinking": thinking_config,
    }
    if use_tools:
        body["tools"] = TOOLS

    print(f"  {label:30s} | prompt={len(prompt):5d} | tools={use_tools} | sending...")
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=body)
        elapsed = time.time() - start
        if resp.status_code != 200:
            print(f"  ❌ {resp.status_code}: {resp.text[:200]}")
            return
        data = resp.json()
        usage = data.get("usage", {})
        details = usage.get("completion_tokens_details", {})
        reasoning_tokens = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0
        choices = data.get("choices", [])
        msg = choices[0].get("message", {}) if choices else {}
        rc_len = len(msg.get("reasoning_content", ""))
        has_tc = bool(msg.get("tool_calls"))
        print(f"  ✅ {elapsed:6.1f}s | completion={usage.get('completion_tokens',0):6d} reasoning={reasoning_tokens:6d} | rc={rc_len:5d} | tools={has_tc}")
        return {"elapsed": elapsed, "reasoning_tokens": reasoning_tokens, "rc_chars": rc_len}
    except httpx.TimeoutException:
        print(f"  ⏰ TIMEOUT after {time.time()-start:.1f}s")
    except Exception as e:
        print(f"  ❌ {time.time()-start:.1f}s: {e}")


async def main():
    print(f"Model: {MODEL}\n" + "=" * 80)
    
    # 简单 prompt + tools
    await test("简单+tools", SIMPLE_PROMPT, True)
    
    # 简单 prompt 无 tools
    await test("简单-无tools", SIMPLE_PROMPT, False)
    
    # 大 prompt + tools
    await test("大prompt+tools", AGENT_PROMPT, True, timeout=600)
    
    # 大 prompt 无 tools
    await test("大prompt-无tools", AGENT_PROMPT, False, timeout=600)


if __name__ == "__main__":
    asyncio.run(main())
