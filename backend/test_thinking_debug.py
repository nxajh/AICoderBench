#!/usr/bin/env python3
"""最小化测试：GLM 思考模式单次调用超时诊断"""
import asyncio, json, os, sys, time
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

API_KEY = os.getenv("GLM_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.1"

SIMPLE_PROMPT = "请用C语言实现一个简单的加法函数 int add(int a, int b)。用 write_file 工具写入 solution.c。"

TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "写入文件",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    }
}

async def test_one(label, body, timeout_s=120):
    print(f"\n{'='*60}")
    print(f"🧪 {label}")
    print(f"   max_tokens={body.get('max_tokens')}, timeout={timeout_s}s")
    print(f"   thinking={body.get('thinking')}")
    print(f"   has_tools={'tools' in body}")
    print(f"{'='*60}")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    start = time.time()

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=body)

        elapsed = time.time() - start
        print(f"✅ Status: {resp.status_code} in {elapsed:.1f}s")

        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            print(f"   Usage: prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}, total={usage.get('total_tokens')}")
            details = usage.get("completion_tokens_details", {})
            if isinstance(details, dict):
                print(f"   Reasoning tokens: {details.get('reasoning_tokens', 'N/A')}")
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                print(f"   Finish reason: {choices[0].get('finish_reason')}")
                print(f"   Has tool_calls: {'tool_calls' in msg}")
                print(f"   Has reasoning_content: {'reasoning_content' in msg}")
                if "reasoning_content" in msg:
                    rc = msg["reasoning_content"]
                    print(f"   Reasoning content: {len(rc)} chars")
                    print(f"   Reasoning preview: {rc[:200]}")
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        fn = tc["function"]
                        print(f"   Tool: {fn['name']}, args_len={len(fn.get('arguments',''))}")
                elif msg.get("content"):
                    print(f"   Content: {len(msg['content'])} chars")
                # Save full response
                with open(f"/tmp/thinking_test_{label.replace(' ', '_')}.json", "w") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            print(f"❌ Error: {resp.text[:500]}")

    except httpx.TimeoutException as e:
        elapsed = time.time() - start
        print(f"⏰ TIMEOUT after {elapsed:.1f}s: {type(e).__name__}: {e}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Exception after {elapsed:.1f}s: {type(e).__name__}: {e}")


async def main():
    print(f"API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"Model: {MODEL}")

    # Test 1: 思考模式 + tool calling (和 agent_runner 一样)
    await test_one("thinking+tools", {
        "model": MODEL,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0,
        "max_tokens": 131072,
        "thinking": {"type": "enabled", "clear_thinking": False},
        "tools": [TOOL],
    }, timeout_s=300)

    # Test 2: 思考模式 + 无 tool calling
    await test_one("thinking+no_tools", {
        "model": MODEL,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0,
        "max_tokens": 131072,
        "thinking": {"type": "enabled", "clear_thinking": False},
    }, timeout_s=300)

    # Test 3: 非思考模式 + tool calling（对照组）
    await test_one("no_thinking+tools", {
        "model": MODEL,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0,
        "max_tokens": 131072,
        "thinking": {"type": "disabled"},
        "tools": [TOOL],
    }, timeout_s=300)

    # Test 4: 思考模式 + 低 max_tokens
    await test_one("thinking+tools+8k", {
        "model": MODEL,
        "messages": [{"role": "user", "content": SIMPLE_PROMPT}],
        "temperature": 0,
        "max_tokens": 8192,
        "thinking": {"type": "enabled", "clear_thinking": False},
        "tools": [TOOL],
    }, timeout_s=300)


if __name__ == "__main__":
    asyncio.run(main())
