#!/usr/bin/env python3
"""对比交错式 vs 保留式 — 跳过已知会超时的交错式 R1，直接比较保留式全流程"""
import asyncio, json, os, sys, time
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
import httpx

API_KEY = os.getenv("GLM_API_KEY")
MODEL = os.getenv("GLM_MODEL", "glm-5.1")
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"

from app.models.problem import load_problem, _find_problem_dir
from app.scheduler.agent_runner import _build_agent_prompt

problem = load_problem("03-interpreter")
problem_dir = _find_problem_dir(problem.id)
AGENT_PROMPT = _build_agent_prompt(problem, problem_dir)

TOOLS = [
    {"type": "function", "function": {
        "name": "write_file",
        "description": "写入文件",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}
    }},
    {"type": "function", "function": {
        "name": "compile",
        "description": "编译",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "submit",
        "description": "提交",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
]


async def chat(messages, mode, timeout=300):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    thinking = {"type": "enabled"}
    if mode == "preserved":
        thinking["clear_thinking"] = False
    elif mode == "no_thinking":
        thinking = {"type": "disabled"}

    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 131072,
        "thinking": thinking,
        "tools": TOOLS,
    }

    label = f"{mode:12s} | msgs={len(messages)}"
    start = time.time()
    print(f"  [{time.strftime('%H:%M:%S')}] {label} | sending...")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=body)
        elapsed = time.time() - start

        if resp.status_code != 200:
            print(f"  [{time.strftime('%H:%M:%S')}] ❌ {resp.status_code}: {resp.text[:300]}")
            return None

        data = resp.json()
        usage = data.get("usage", {})
        details = usage.get("completion_tokens_details", {})
        reasoning_tokens = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0
        choices = data.get("choices", [])
        msg = choices[0].get("message", {}) if choices else {}
        rc_len = len(msg.get("reasoning_content", ""))

        print(f"  [{time.strftime('%H:%M:%S')}] ✅ {elapsed:6.1f}s | completion={usage.get('completion_tokens',0)} reasoning={reasoning_tokens} | rc_chars={rc_len} | finish={choices[0].get('finish_reason','') if choices else ''}")

        # Save full response for analysis
        result = {
            "msg": msg,
            "elapsed": elapsed,
            "usage": usage,
            "reasoning_tokens": reasoning_tokens,
            "reasoning_chars": rc_len,
        }
        return result

    except httpx.TimeoutException:
        elapsed = time.time() - start
        print(f"  [{time.strftime('%H:%M:%S')}] ⏰ TIMEOUT after {elapsed:.1f}s")
        return None
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [{time.strftime('%H:%M:%S')}] ❌ {elapsed:.1f}s: {type(e).__name__}: {e}")
        return None


async def main():
    print(f"Model: {MODEL}")
    print(f"Prompt: {len(AGENT_PROMPT)} chars")
    print("=" * 80)

    # === 保留式 R1 ===
    print("\n### 保留式 Round 1 ###")
    r1 = await chat([{"role": "user", "content": AGENT_PROMPT}], "preserved")
    if not r1:
        print("保留式 R1 失败"); return

    msg1 = r1["msg"]
    tc_id = msg1.get("tool_calls", [{}])[0].get("id", "call_1") if msg1.get("tool_calls") else "call_1"

    # === 保留式 R2（带完整 reasoning_content） ===
    msgs2 = [
        {"role": "user", "content": AGENT_PROMPT},
        msg1,
        {"role": "tool", "tool_call_id": tc_id, "content": "File solution.c written (1500 bytes)"},
    ]
    print(f"\n### 保留式 Round 2 (history ~{sum(len(json.dumps(m, ensure_ascii=False)) for m in msgs2)} chars) ###")
    r2 = await chat(msgs2, "preserved")

    # === 交错式 R1（大输入 + 多 tools） ===
    print("\n### 交错式 Round 1 (timeout=300s) ###")
    r_int1 = await chat([{"role": "user", "content": AGENT_PROMPT}], "interleaved", timeout=300)

    # === 非思考对照组 R1 ===
    print("\n### 非思考 Round 1 ###")
    r_no = await chat([{"role": "user", "content": AGENT_PROMPT}], "no_thinking")

    # === Summary ===
    print("\n" + "=" * 80)
    print("📊 总结")
    print("=" * 80)
    for label, r in [
        ("保留式 R1", r1), ("保留式 R2", r2),
        ("交错式 R1", r_int1), ("非思考 R1", r_no)
    ]:
        if r:
            print(f"  {label:12s}: {r['elapsed']:6.1f}s | reasoning={r['reasoning_tokens']:6d} tokens | rc={r['reasoning_chars']:6d} chars")
        else:
            print(f"  {label:12s}: FAILED/TIMEOUT")


if __name__ == "__main__":
    asyncio.run(main())
