#!/usr/bin/env python3
"""跑 GLM-5.1 非思考模式 3 次，保存每次生成的代码和编译结果"""
import asyncio, sys, os, json, time, subprocess
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(line_buffering=True)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from app.models.problem import load_problem, _find_problem_dir
from app.providers.model_provider import GLMProvider
from app.scheduler.engine import build_prompt

async def main():
    problem = load_problem("03-interpreter")
    prompt = build_prompt(problem)
    problem_dir = _find_problem_dir(problem.id)
    solution_h = (problem_dir / "solution.h").read_text()
    test_c = (problem_dir / "test.c").read_text()

    provider = GLMProvider(
        api_key=os.getenv("GLM_API_KEY"),
        model="glm-5.1",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
        thinking=False,
    )

    for i in range(3):
        print(f"\n{'='*60}")
        print(f"Run {i+1}/3")
        print(f"{'='*60}")

        start = time.time()
        gen = await provider.generate(prompt)
        elapsed = time.time() - start

        print(f"Time: {elapsed:.1f}s")
        print(f"Method: {'tool_call' if gen.used_tool_call else 'text'}")
        print(f"Tokens: {gen.token_usage}")

        if not gen.files:
            print("❌ 没有生成代码")
            # 保存原始输出
            with open(f"/tmp/glm_debug_run{i+1}_raw.txt", "w") as f:
                f.write(gen.raw_output[:5000])
            continue

        code = gen.files[0].content
        print(f"Code: {len(code)} chars, {len(code.splitlines())} lines")
        print(f"Usage: {gen.token_usage}")

        # 保存代码
        out_dir = Path(f"/tmp/glm_debug_run{i+1}")
        out_dir.mkdir(exist_ok=True)
        (out_dir / "solution.c").write_text(code)
        (out_dir / "usage.json").write_text(json.dumps(gen.token_usage, indent=2))
        (out_dir / "raw.txt").write_text(gen.raw_output[:10000])

        # 尝试编译
        compile_cmd = [
            "gcc", "-fsanitize=address,undefined",
            "-o", str(out_dir / "test_binary"),
            str(out_dir / "solution.c"),
            "-lm", "-lpthread",
        ]
        # 也可能需要 -I 和 test.c
        # 先看能不能单独编译 solution.c
        result = subprocess.run(
            compile_cmd,
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print(f"✅ 编译通过")
        else:
            print(f"❌ 编译失败")
            print(f"stderr: {result.stderr[:1000]}")

        # 再带 test.c 一起编译
        (out_dir / "test.c").write_text(test_c)
        (out_dir / "solution.h").write_text(solution_h)
        compile_cmd2 = [
            "gcc", "-fsanitize=address,undefined",
            "-o", str(out_dir / "test_binary2"),
            str(out_dir / "solution.c"),
            str(out_dir / "test.c"),
            "-lm", "-lpthread",
            f"-I{out_dir}",
        ]
        result2 = subprocess.run(
            compile_cmd2,
            capture_output=True, text=True, timeout=30
        )
        if result2.returncode == 0:
            print(f"✅ 带 test.c 编译通过")
        else:
            print(f"❌ 带 test.c 编译失败")
            print(f"stderr: {result2.stderr[:1500]}")

        # 检查代码完整性：是否有未实现的函数
        # 从 solution.h 中提取函数声明
        import re
        h_funcs = re.findall(r'(\w+)\s*\(', solution_h)
        # 去掉 typedef/struct 等关键字
        h_funcs = [f for f in h_funcs if f not in ('struct', 'typedef', 'enum', 'void', 'int', 'double', 'char', 'const')]
        print(f"\nHeader functions: {h_funcs}")
        for fn in h_funcs:
            if fn in code:
                print(f"  ✅ {fn} - found in code")
            else:
                print(f"  ❌ {fn} - MISSING from code")

        print(f"\nLast 10 lines of code:")
        for line in code.splitlines()[-10:]:
            print(f"  {line}")

if __name__ == "__main__":
    asyncio.run(main())
