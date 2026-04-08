#!/usr/bin/env python3
"""对比交错式 vs 保留式思考模式的响应时间"""
import asyncio, json, os, sys, time
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import httpx

API_KEY = os.getenv("GLM_API_KEY")
MODEL = os.getenv("GLM_MODEL", "glm-5.1")
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"

# 用 agent 的完整 prompt（大输入）
from app.models.problem import load_problem, _find_problem_dir
from app.scheduler.agent_runner import _build_agent_prompt

problem = load_problem("03-interpreter")
problem_dir = _find_problem_dir(problem.id)
AGENT_PROMPT = _build_agent_prompt(problem, problem_dir)

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
]


async def chat(messages, thinking_mode, timeout=600):
    """
    thinking_mode:
      - "interleaved": thinking=enabled, no clear_thinking field
      - "preserved": thinking=enabled, clear_thinking=False
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    thinking_config = {"type": "enabled"}
    if thinking_mode == "preserved":
        thinking_config["clear_thinking"] = False

    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 131072,
        "thinking": thinking_config,
        "tools": TOOLS,
    }

    label = f"{thinking_mode:12s} | msgs={len(messages)}"
    print(f"  {label} | sending...")

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json=body,
            )
        elapsed = time.time() - start

        if resp.status_code != 200:
            print(f"  ❌ {resp.status_code}: {resp.text[:300]}")
            return None, elapsed

        data = resp.json()
        usage = data.get("usage", {})
        details = usage.get("completion_tokens_details", {})
        reasoning_tokens = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0

        choices = data.get("choices", [])
        msg = choices[0].get("message", {}) if choices else {}
        reasoning_content = msg.get("reasoning_content", "")
        has_tool_calls = "tool_calls" in msg and msg["tool_calls"]

        print(f"  ✅ {elapsed:6.1f}s | completion={usage.get('completion_tokens',0):6d} reasoning={reasoning_tokens:6d} | reasoning_chars={len(reasoning_content):6d} | tool_calls={has_tool_calls} | finish={choices[0].get('finish_reason','')}")

        return {
            "msg": msg,
            "usage": usage,
            "reasoning_tokens": reasoning_tokens,
            "reasoning_chars": len(reasoning_content),
            "elapsed": elapsed,
        }, elapsed

    except httpx.TimeoutException:
        elapsed = time.time() - start
        print(f"  ⏰ TIMEOUT after {elapsed:.1f}s")
        return None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ {elapsed:.1f}s: {type(e).__name__}: {e}")
        return None, elapsed


async def main():
    print(f"Model: {MODEL}")
    print(f"Prompt: {len(AGENT_PROMPT)} chars")
    print("=" * 80)

    # ==========================================
    # Test 1: 交错式 Round 1
    # ==========================================
    print("\n### 交错式 Round 1 ###")
    r1_int, _ = await chat([{"role": "user", "content": AGENT_PROMPT}], "interleaved")
    if not r1_int:
        print("交错式 Round 1 失败，跳过")
        return

    # ==========================================
    # Test 2: 保留式 Round 1
    # ==========================================
    print("\n### 保留式 Round 1 ###")
    r1_pre, _ = await chat([{"role": "user", "content": AGENT_PROMPT}], "preserved")
    if not r1_pre:
        print("保留式 Round 1 失败，跳过")
        return

    # ==========================================
    # Test 3: 交错式 Round 2（带 reasoning + tool result）
    # ==========================================
    msg1_int = r1_int["msg"]
    tc_id = msg1_int.get("tool_calls", [{}])[0].get("id", "call_1") if msg1_int.get("tool_calls") else "call_1"

    # 交错式：reasoning_content 也要放入
    int_messages = [
        {"role": "user", "content": AGENT_PROMPT},
        {k: v for k, v in msg1_int.items() if v},  # 包含 reasoning_content
        {"role": "tool", "tool_call_id": tc_id, "content": "File solution.c written (500 bytes)"},
    ]
    print(f"\n### 交错式 Round 2 (history size ~{sum(len(json.dumps(m, ensure_ascii=False)) for m in int_messages)} chars) ###")
    r2_int, _ = await chat(int_messages, "interleaved")

    # ==========================================
    # Test 4: 保留式 Round 2（带 reasoning + tool result）
    # ==========================================
    msg1_pre = r1_pre["msg"]
    tc_id2 = msg1_pre.get("tool_calls", [{}])[0].get("id", "call_1") if msg1_pre.get("tool_calls") else "call_1"

    pre_messages = [
        {"role": "user", "content": AGENT_PROMPT},
        {k: v for k, v in msg1_pre.items() if v},
        {"role": "tool", "tool_call_id": tc_id2, "content": "File solution.c written (500 bytes)"},
    ]
    print(f"\n### 保留式 Round 2 (history size ~{sum(len(json.dumps(m, ensure_ascii=False)) for m in pre_messages)} chars) ###")
    r2_pre, _ = await chat(pre_messages, "preserved")

    # ==========================================
    # Summary
    # ==========================================
    print("\n" + "=" * 80)
    print("📊 对比总结")
    print("=" * 80)
    print(f"{'Mode':15s} | {'Round':6s} | {'Time':>7s} | {'Reason tokens':>14s} | {'Reason chars':>12s}")
    print("-" * 80)
    for label, r1, r2 in [
        ("Interleaved", r1_int, r2_int),
        ("Preserved", r1_pre, r2_pre),
    ]:
        if r1:
            print(f"{label:15s} | {'R1':6s} | {r1['elapsed']:6.1f}s | {r1['reasoning_tokens']:14d} | {r1['reasoning_chars']:12d}")
        if r2:
            print(f"{label:15s} | {'R2':6s} | {r2['elapsed']:6.1f}s | {r2['reasoning_tokens']:14d} | {r2['reasoning_chars']:12d}")


if __name__ == "__main__":
    asyncio.run(main())
