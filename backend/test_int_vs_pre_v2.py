#!/usr/bin/env python3
"""交错式 vs 保留式详细对比 — 记录完整 reasoning + output"""
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

OUT_DIR = Path("/tmp/thinking_compare_v2")
OUT_DIR.mkdir(exist_ok=True)


async def test(label, thinking_config, timeout=1200):
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
    print(f"   prompt={len(AGENT_PROMPT)} chars (~{len(AGENT_PROMPT)//4} tokens)")
    print(f"   timeout={timeout}s")
    print(f"   [{time.strftime('%H:%M:%S')}] sending...")
    print(f"{'='*60}")

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{BASE_URL}/chat/completions", headers=headers, json=body)
        elapsed = time.time() - start

        if resp.status_code != 200:
            print(f"  ❌ [{time.strftime('%H:%M:%S')}] {resp.status_code}: {resp.text[:500]}")
            return None

        data = resp.json()
        usage = data.get("usage", {})
        det = usage.get("completion_tokens_details", {})
        rt = det.get("reasoning_tokens", 0) if isinstance(det, dict) else 0
        msg = data["choices"][0]["message"]
        rc = msg.get("reasoning_content", "")
        content = msg.get("content", "")
        tc = msg.get("tool_calls", [])
        finish = data["choices"][0].get("finish_reason", "")

        # Save full response
        slug = label.replace(" ", "_")
        with open(OUT_DIR / f"{slug}_full.json", "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Save reasoning content separately
        with open(OUT_DIR / f"{slug}_reasoning.txt", "w") as f:
            f.write(rc)

        # Save content separately
        with open(OUT_DIR / f"{slug}_content.txt", "w") as f:
            f.write(content)

        # Save tool calls
        with open(OUT_DIR / f"{slug}_tools.json", "w") as f:
            json.dump(tc, f, ensure_ascii=False, indent=2)

        print(f"  ✅ [{time.strftime('%H:%M:%S')}] {elapsed:.1f}s | finish={finish}")
        print(f"     prompt_tokens={usage.get('prompt_tokens')}")
        print(f"     completion_tokens={usage.get('completion_tokens')}")
        print(f"     reasoning_tokens={rt}")
        print(f"     total_tokens={usage.get('total_tokens')}")
        print(f"     reasoning_chars={len(rc)}")
        print(f"     content_chars={len(content)}")
        print(f"     tool_calls={len(tc)}")
        print(f"     saved to {OUT_DIR}/{slug}_*")

        return {
            "label": label, "elapsed": elapsed, "finish": finish,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "reasoning_tokens": rt,
            "total_tokens": usage.get("total_tokens", 0),
            "reasoning_chars": len(rc),
            "content_chars": len(content),
            "tool_calls_count": len(tc),
        }
    except httpx.TimeoutException:
        print(f"  ⏰ TIMEOUT after {time.time()-start:.1f}s")
    except Exception as e:
        print(f"  ❌ {time.time()-start:.1f}s: {type(e).__name__}: {e}")
    return None


async def main():
    print(f"Model: {MODEL}")
    print(f"Output dir: {OUT_DIR}")

    # 交错式
    r_int = await test("interleaved", {"type": "enabled"}, timeout=1200)
    
    # 保留式
    r_pre = await test("preserved", {"type": "enabled", "clear_thinking": False}, timeout=1200)

    # 总结
    print(f"\n{'='*60}")
    print("📊 对比总结")
    print(f"{'='*60}")
    for label, r in [("交错式", r_int), ("保留式", r_pre)]:
        if r:
            print(f"  {label}: {r['elapsed']:.1f}s | prompt={r['prompt_tokens']} | completion={r['completion_tokens']} | reasoning={r['reasoning_tokens']} | total={r['total_tokens']} | rc={r['reasoning_chars']} chars | content={r['content_chars']} chars | tools={r['tool_calls_count']} | finish={r['finish']}")
        else:
            print(f"  {label}: FAILED/TIMEOUT")

    if r_int and r_pre:
        print(f"\n  倍率差异:")
        print(f"    时间:   交错/保留 = {r_int['elapsed']/r_pre['elapsed']:.2f}x")
        print(f"    reasoning tokens: {r_int['reasoning_tokens']/r_pre['reasoning_tokens']:.2f}x")
        print(f"    completion tokens: {r_int['completion_tokens']/r_pre['completion_tokens']:.2f}x")

if __name__ == "__main__":
    asyncio.run(main())
