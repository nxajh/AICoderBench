"""测试 GLM-5.1 coding API 在 interpreter 题目上的表现"""
import httpx, json, os, sys, time
from pathlib import Path
sys.stdout.reconfigure(line_buffering=True)

# Load env
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

api_key = os.getenv("GLM_API_KEY")
base_url = "https://open.bigmodel.cn/api/coding/paas/v4"

problem_dir = Path(__file__).parent.parent / "problems" / "03-interpreter"
problem_md = (problem_dir / "problem.md").read_text()
solution_h = (problem_dir / "solution.h").read_text()
test_c = (problem_dir / "test.c").read_text()

# 完整 prompt（和 test_glm_timeout.py 一样）
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

print(f"Prompt length: {len(prompt)} chars")

# Test with tool calling, max_tokens=65535
body = {
    "model": "glm-5.1",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "max_tokens": 65535,
    "tools": [TOOL],
}

print(f"\n### Tool Calling Mode (max_tokens=65535) ###")
start = time.time()
try:
    with httpx.Client(timeout=1800) as c:
        r = c.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
    elapsed = time.time() - start
    print(f"Status: {r.status_code} in {elapsed:.1f}s")
    if r.status_code == 200:
        d = r.json()
        print(f"Usage: {d.get('usage')}")
        msg = d["choices"][0]["message"]
        print(f"finish_reason: {d['choices'][0]['finish_reason']}")
        if "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                args = fn["arguments"]
                print(f"Tool: {fn['name']}, args len: {len(args)}")
                parsed = json.loads(args)
                code = parsed.get("content", "")
                print(f"Code: {len(code)} chars, {len(code.splitlines())} lines")
                with open("/tmp/glm_interp_tc.json", "w") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                print("Saved to /tmp/glm_interp_tc.json")
        else:
            print(f"Content: {msg.get('content', '')[:2000]}")
    else:
        print(f"Error: {r.text[:1000]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"Exception after {elapsed:.1f}s: {type(e).__name__}: {e}")

# Also test without tool calling
print(f"\n### Plain Text Mode (max_tokens=65535) ###")
body2 = {
    "model": "glm-5.1",
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0,
    "max_tokens": 65535,
}

start = time.time()
try:
    with httpx.Client(timeout=1800) as c:
        r = c.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body2,
        )
    elapsed = time.time() - start
    print(f"Status: {r.status_code} in {elapsed:.1f}s")
    if r.status_code == 200:
        d = r.json()
        print(f"Usage: {d.get('usage')}")
        msg = d["choices"][0]["message"]
        print(f"finish_reason: {d['choices'][0]['finish_reason']}")
        content = msg.get("content", "")
        print(f"Content: {len(content)} chars")
        with open("/tmp/glm_interp_plain.txt", "w") as f:
            f.write(content)
        print("Saved to /tmp/glm_interp_plain.txt")
    else:
        print(f"Error: {r.text[:1000]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"Exception after {elapsed:.1f}s: {type(e).__name__}: {e}")
