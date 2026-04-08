#!/usr/bin/env python3
"""测试 Agent 模式下 GLM 思考模式超时问题"""
import asyncio, json, os, sys, time
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

API_KEY = os.getenv("GLM_API_KEY")
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
MODEL = "glm-5.1"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "将代码写入指定文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件完整内容"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compile",
            "description": "编译 solution.c",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit",
            "description": "提交最终代码",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]

# 用实际 agent prompt
from app.models.problem import load_problem, _find_problem_dir
from app.scheduler.agent_runner import _build_agent_prompt

problem = load_problem("03-interpreter")
problem_dir = _find_problem_dir("03-interpreter")
AGENT_PROMPT = _build_agent_prompt(problem, problem_dir)

print(f"Prompt length: {len(AGENT_PROMPT)} chars, ~{len(AGENT_PROMPT)//4} tokens")

async def test_chat(label, messages, thinking=True, max_tokens=131072, timeout_s=600):
    print(f"\n{'='*60}")
    print(f"🧪 {label}")
    print(f"   messages={len(messages)}, thinking={thinking}, max_tokens={max_tokens}")
    print(f"   timeout={timeout_s}s")
    print(f"{'='*60}")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "tools": TOOLS,
    }
    if thinking:
        body["thinking"] = {"type": "enabled", "clear_thinking": False}
    else:
        body["thinking"] = {"type": "disabled"}

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=body)

        elapsed = time.time() - start
        print(f"✅ {resp.status_code} in {elapsed:.1f}s")
        if resp.status_code == 200:
            data = resp.json()
            usage = data.get("usage", {})
            print(f"   Usage: prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}")
            details = usage.get("completion_tokens_details", {})
            if isinstance(details, dict):
                print(f"   Reasoning: {details.get('reasoning_tokens', 'N/A')}")
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                print(f"   Finish: {choices[0].get('finish_reason')}")
                print(f"   Has tool_calls: {'tool_calls' in msg}")
                if "reasoning_content" in msg:
                    print(f"   Reasoning content: {len(msg['reasoning_content'])} chars")

                # Simulate adding to messages history (like agent_runner does)
                messages_out = messages + [msg]
                total_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages_out)
                print(f"   Total messages size after: {total_chars} chars")

                return msg
        else:
            print(f"❌ {resp.text[:500]}")
    except httpx.TimeoutException as e:
        elapsed = time.time() - start
        print(f"⏰ TIMEOUT after {elapsed:.1f}s: {type(e).__name__}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ {elapsed:.1f}s: {type(e).__name__}: {e}")
    return None


async def main():
    # Test 1: Round 1 — thinking mode, simple
    msg1 = await test_chat(
        "Round 1: thinking",
        [{"role": "user", "content": AGENT_PROMPT}],
        thinking=True,
    )

    if not msg1:
        print("Round 1 failed, stopping")
        return

    # Simulate tool response
    tool_call_id = msg1.get("tool_calls", [{}])[0].get("id", "call_1") if msg1.get("tool_calls") else "call_1"
    messages_2 = [
        {"role": "user", "content": AGENT_PROMPT},
        msg1,
        {"role": "tool", "tool_call_id": tool_call_id, "content": "File solution.c written (500 bytes)"},
    ]

    # Test 2: Round 2 — thinking mode with history
    msg2 = await test_chat(
        "Round 2: thinking + history",
        messages_2,
        thinking=True,
    )

    if not msg2:
        print("Round 2 failed, stopping")
        return

    # Build round 3 with more history
    messages_3 = messages_2 + [msg2]
    if msg2.get("tool_calls"):
        tc_id = msg2["tool_calls"][0].get("id", "call_2")
        messages_3.append({"role": "tool", "tool_call_id": tc_id, "content": json.dumps({"success": True, "errors": "", "warnings": ""})})
    else:
        messages_3.append({"role": "user", "content": "请继续"})

    msg3 = await test_chat(
        "Round 3: thinking + more history",
        messages_3,
        thinking=True,
    )

    # Control: Round 1 non-thinking
    await test_chat(
        "Round 1: NO thinking (control)",
        [{"role": "user", "content": AGENT_PROMPT}],
        thinking=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
