#!/usr/bin/env python3
"""交错式 vs 保留式思考模式对比 — 大 prompt + tools"""
import asyncio, json, os, sys, time, httpx
sys.stdout.reconfigure(line_buffering=True)
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

API_KEY = os.getenv("GLM_API_KEY")
MODEL = os.getenv("GLM_MODEL", "glm-5.1")
BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"

from app.models.problem import load_problem, _find_problem_dir
from app.scheduler.agent_runner import _build_agent_prompt, AGENT_TOOLS

problem = load_problem("03-interpreter")
problem_dir = _find_problem_dir(problem.id)
AGENT_PROMPT = _build_agent_prompt(problem, problem_dir)


async def test(label, thinking_config, timeout=600):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": AGENT_PROMPT}],
        "temperature": 0,
        "max_tokens": 131072,
        "thinking": thinking_config,
        "tools": AGENT_TOOLS,
    }

    print(f"\n{'='*60}")
    print(f"🧪 {label}")
    print(f"   thinking={json.dumps(thinking_config)}")
    print(f"   prompt={len(AGENT_PROMPT)} chars, timeout={timeout}s")
    print(f"   [{time.strftime('%H:%M:%S')}] sending...")
    print(f"{'='*60}")

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=body)
        elapsed = time.time() - start

        if resp.status_code != 200:
            print(f"  ❌ [{time.strftime('%H:%M:%S')}] {resp.status_code}: {resp.text[:300]}")
            return

        data = resp.json()
        usage = data.get("usage", {})
        details = usage.get("completion_tokens_details", {})
        reasoning_tokens = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0
        choices = data.get("choices", [])
        msg = choices[0].get("message", {}) if choices else {}
        rc_len = len(msg.get("reasoning_content", ""))
        has_tc = bool(msg.get("tool_calls"))
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        print(f"  ✅ [{time.strftime('%H:%M:%S')}] {elapsed:.1f}s")
        print(f"     prompt_tokens={prompt_tokens}, completion_tokens={completion_tokens}, reasoning_tokens={reasoning_tokens}")
        print(f"     reasoning_chars={rc_len}, tool_calls={has_tc}")
        
        # Save
        with open(f"/tmp/{label.replace(' ','_')}.json", "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"     saved to /tmp/{label.replace(' ','_')}.json")

        return {"elapsed": elapsed, "reasoning_tokens": reasoning_tokens, "rc_chars": rc_len, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}

    except httpx.TimeoutException:
        print(f"  ⏰ [{time.strftime('%H:%M:%S')}] TIMEOUT after {time.time()-start:.1f}s")
    except Exception as e:
        print(f"  ❌ [{time.strftime('%H:%M:%S')}] {time.time()-start:.1f}s: {type(e).__name__}: {e}")


async def main():
    print(f"Model: {MODEL}")

    # 交错式
    r_int = await test("interleaved", {"type": "enabled"}, timeout=600)

    # 保留式
    r_pre = await test("preserved", {"type": "enabled", "clear_thinking": False}, timeout=600)

    # 总结
    print(f"\n{'='*60}")
    print("📊 对比")
    print(f"{'='*60}")
    for label, r in [("交错式", r_int), ("保留式", r_pre)]:
        if r:
            print(f"  {label}: {r['elapsed']:.1f}s | reasoning={r['reasoning_tokens']} tokens | rc={r['rc_chars']} chars")
        else:
            print(f"  {label}: TIMEOUT/FAILED")


if __name__ == "__main__":
    asyncio.run(main())
