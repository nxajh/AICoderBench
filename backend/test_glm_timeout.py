"""
测试 GLM-5.1 在 interpreter 题目上的完整输出
记录请求/响应/耗时，分析超时原因
"""
import asyncio
import json
import time
import os
import sys

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# 读题
problem_dir = Path(__file__).parent.parent / "problems" / "03-interpreter"
problem_md = (problem_dir / "problem.md").read_text()
solution_h = (problem_dir / "solution.h").read_text()
test_c = (problem_dir / "test.c").read_text()

prompt = f"""你是一个C语言编程专家。请根据以下题目要求实现 solution.c。

## 题目描述
{problem_md}

## 头文件（solution.h）
```c
{solution_h}
```

## 测试代码（参考，不要修改）
```c
{test_c}
```

请使用 write_file 工具将你的实现写入 solution.c 文件。只写 C 代码，不需要解释。"""

TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "将代码写入指定文件路径",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件完整内容"}
            },
            "required": ["path", "content"]
        }
    }
}

async def test_glm():
    import httpx

    api_key = os.getenv("GLM_API_KEY")
    model = os.getenv("GLM_MODEL", "glm-5.1")
    base_url = "https://open.bigmodel.cn/api/coding/paas/v4"

    print(f"Model: {model}")
    print(f"Base URL: {base_url}")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"Prompt length: {len(prompt)} chars")
    print("=" * 80)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Test 1: tool calling mode
    print("\n### TEST 1: Tool Calling Mode (max_tokens=65535) ###\n")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 65535,
        "tools": [TOOL],
    }

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=1800) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=body,
            )
        elapsed = time.time() - start
        print(f"Status: {resp.status_code}")
        print(f"Elapsed: {elapsed:.2f}s")

        if resp.status_code == 200:
            data = resp.json()
            print(f"Response keys: {list(data.keys())}")
            print(f"Usage: {data.get('usage', {})}")

            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                print(f"Finish reason: {choices[0].get('finish_reason')}")
                print(f"Has tool_calls: {'tool_calls' in msg}")
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        print(f"Tool: {fn.get('name')}")
                        args = fn.get("arguments", "")
                        print(f"Arguments length: {len(args)} chars")
                        # Save full response
                        with open("/tmp/glm_tool_call_response.json", "w") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        print("Full response saved to /tmp/glm_tool_call_response.json")
                else:
                    content = msg.get("content", "")
                    print(f"Content length: {len(content)} chars")
                    print(f"Content preview:\n{content[:2000]}")
                    with open("/tmp/glm_tool_call_response.json", "w") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            print(f"Error response: {resp.text[:2000]}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"Exception after {elapsed:.2f}s: {type(e).__name__}: {e}")

    # Test 2: plain text mode (no tools)
    print("\n\n### TEST 2: Plain Text Mode (max_tokens=65535, no tools) ###\n")
    body2 = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 65535,
    }

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=1800) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=body2,
            )
        elapsed = time.time() - start
        print(f"Status: {resp.status_code}")
        print(f"Elapsed: {elapsed:.2f}s")

        if resp.status_code == 200:
            data = resp.json()
            print(f"Usage: {data.get('usage', {})}")
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "")
                print(f"Content length: {len(content)} chars")
                print(f"Finish reason: {choices[0].get('finish_reason')}")
                with open("/tmp/glm_plain_response.txt", "w") as f:
                    f.write(content)
                print("Full content saved to /tmp/glm_plain_response.txt")
                print(f"Content preview:\n{content[:3000]}")
        else:
            print(f"Error: {resp.text[:2000]}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"Exception after {elapsed:.2f}s: {type(e).__name__}: {e}")

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    asyncio.run(test_glm())
