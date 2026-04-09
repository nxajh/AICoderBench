"""
Agent Runner — 多轮对话式代码生成
流程：模型写代码 → 编译 → 看错误修改 → 跑自测 → 看结果修改 → 提交
"""
import asyncio
import json
import logging
import time
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Awaitable

from ..providers.model_provider import ModelProvider
from ..evaluator.engine import run_eval_in_sandbox, compute_scores, EvalResult
from ..models.problem import Problem, _find_problem_dir
from ..utils import clean_thinking as _clean_thinking
from ..config import AGENT_MAX_TOKENS

logger = logging.getLogger(__name__)

# 总超时 2 小时
AGENT_TOTAL_TIMEOUT = 7200
# 单次编译超时
COMPILE_TIMEOUT = 30
# 单次运行测试超时
RUN_TESTS_TIMEOUT = 30
# 最大循环轮次
MAX_ROUNDS = 50

# ---- 工具定义 ----
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "创建或编辑文件，通过 command 参数选择模式：\n"
                "- create：创建新文件并写入完整内容（文件已存在则报错，请改用 str_replace）\n"
                "- str_replace：在已有文件中精确替换指定内容（old_string 必须在文件中唯一存在）"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["create", "str_replace"],
                        "description": "操作模式：create 创建新文件，str_replace 替换已有内容"
                    },
                    "path": {
                        "type": "string",
                        "description": "文件路径，如 solution.c 或 test_self.c"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件完整内容（create 模式必填）"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要被替换的原始内容，必须在文件中唯一存在（str_replace 模式必填）"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新内容（str_replace 模式必填）"
                    }
                },
                "required": ["command", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compile",
            "description": "编译 solution.c 为目标文件，返回编译结果（成功/错误/警告）。需要先用 write_file 写入 solution.c。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "将 compile() 生成的 solution.o 与 test_self.c 链接并运行，返回测试输出。需要先调用 compile() 且已写入 test_self.c。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定文件的内容，支持通过 start_line / end_line 只读取部分行（行号从 1 开始）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径，如 solution.c 或 test_self.c"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（从 1 开始，不填则从第 1 行读取）"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（包含该行，不填则读到文件末尾）"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit",
            "description": "提交最终代码进行平台评分。确认代码已通过自测后再调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


@dataclass
class AgentRunResult:
    """Agent 运行结果"""
    # 生成的文件
    files: dict[str, str] = field(default_factory=dict)  # {filename: content}
    # 总耗时（秒）
    total_time: float = 0.0
    # 总轮次
    rounds: int = 0
    # 总 token
    total_token_usage: dict = field(default_factory=dict)
    # 是否正常提交
    submitted: bool = False
    # 提交原因
    finish_reason: str = ""  # "submitted" | "timeout" | "max_rounds" | "error"
    # 每轮记录
    history: list[dict] = field(default_factory=list)
    # 错误信息
    error: str = ""


def _extract_text(resp: dict) -> str:
    choices = resp.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return ""


def _extract_reasoning(resp: dict) -> str:
    """提取 reasoning_content（GLM thinking 模式等）"""
    choices = resp.get("choices", [])
    if not choices:
        return ""
    msg = choices[0].get("message", {})
    # GLM 格式
    rc = msg.get("reasoning_content", "")
    if rc:
        return rc
    return ""


def _extract_tool_calls(resp: dict) -> list[dict]:
    choices = resp.get("choices", [])
    if not choices:
        return []
    message = choices[0].get("message", {})
    return message.get("tool_calls", [])



async def _do_compile(sandbox_dir: Path, compile_flags: str = "") -> dict:
    """编译 solution.c 为 .o（不链接），验证代码本身是否正确"""
    if not (sandbox_dir / "solution.c").exists():
        return {"success": False, "errors": "solution.c not found", "warnings": ""}

    cmd = [
        "gcc", "-std=c11", "-D_DEFAULT_SOURCE",
        "-Wall", "-Wextra", "-O2",
        "-c", "solution.c",
        "-o", "solution.o",
    ] + (compile_flags.split() if compile_flags else [])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(sandbox_dir),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=COMPILE_TIMEOUT)
        warnings = ""
        errors = ""
        stderr_text = stderr.decode("utf-8", errors="replace")
        if proc.returncode == 0:
            if stderr_text.strip():
                warnings = stderr_text.strip()
            return {"success": True, "errors": "", "warnings": warnings}
        else:
            return {"success": False, "errors": stderr_text.strip(), "warnings": ""}
    except asyncio.TimeoutError:
        return {"success": False, "errors": f"Compilation timed out ({COMPILE_TIMEOUT}s)", "warnings": ""}
    except Exception as e:
        return {"success": False, "errors": str(e), "warnings": ""}


async def _do_run_tests(sandbox_dir: Path, compile_flags: str = "") -> dict:
    """链接 solution.o + test_self.c 并运行"""
    if not (sandbox_dir / "solution.o").exists():
        return {"success": False, "output": "solution.o not found. Compile solution.c first."}
    if not (sandbox_dir / "test_self.c").exists():
        return {"success": False, "output": "test_self.c not found. Write test_self.c first."}

    # 链接 solution.o + test_self.c
    link_cmd = [
        "gcc", "-std=c11", "-D_DEFAULT_SOURCE", "-O2",
        "solution.o", "test_self.c",
        "-o", "test_binary",
    ] + (compile_flags.split() if compile_flags else []) + ["-lm", "-lpthread"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *link_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(sandbox_dir),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=COMPILE_TIMEOUT)
        if proc.returncode != 0:
            return {"success": False, "output": f"Link failed: {stderr.decode('utf-8', errors='replace').strip()}"}
    except Exception as e:
        return {"success": False, "output": f"Link error: {e}"}

    # 运行
    binary = sandbox_dir / "test_binary"
    if not binary.exists():
        return {"success": False, "output": "Binary not found. Compile first."}

    try:
        proc = await asyncio.create_subprocess_exec(
            str(binary),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(sandbox_dir),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=RUN_TESTS_TIMEOUT)
        output = ""
        if stdout:
            output += stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
        return {
            "success": proc.returncode == 0,
            "output": output.strip(),
            "exit_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"success": False, "output": f"Test run timed out ({RUN_TESTS_TIMEOUT}s)"}
    except Exception as e:
        return {"success": False, "output": str(e)}


_TOOL_RESULT_MAX_LEN = 8192  # tool result 最大长度（字节），超出截断


def _truncate_tool_result(text: str) -> str:
    if len(text) <= _TOOL_RESULT_MAX_LEN:
        return text
    kept = _TOOL_RESULT_MAX_LEN
    return text[:kept] + f"\n... [output truncated, {len(text) - kept} chars omitted]"


def _safe_path(sandbox: Path, fpath: str) -> Optional[Path]:
    """确保文件路径在 sandbox 目录内，防止路径穿越和符号链接穿越"""
    sandbox_real = sandbox.resolve()
    target = sandbox / fpath
    try:
        resolved = target.resolve()
        resolved.relative_to(sandbox_real)  # 路径必须在 sandbox 内
    except (ValueError, OSError):
        return None
    # 若目标已存在且是符号链接，验证其最终指向仍在 sandbox 内
    if target.exists() and target.is_symlink():
        try:
            target.resolve().relative_to(sandbox_real)
        except ValueError:
            return None
    return resolved


def _build_agent_prompt(problem: Problem, problem_dir: Path) -> str:
    """构造 Agent 模式的初始 prompt"""
    desc_file = problem_dir / "problem.md"
    description = desc_file.read_text() if desc_file.exists() else problem.title

    header_file = problem_dir / "solution.h"
    interface = header_file.read_text() if header_file.exists() else ""

    # 读取编译参数
    extra_flags = ""
    problem_json = problem_dir / "problem.json"
    if problem_json.exists():
        pdata = json.loads(problem_json.read_text())
        extra_flags = pdata.get("compile_flags", "")

    return f"""请用 C 语言实现以下功能。

【重要】你必须全程使用中文进行思考和回复，包括分析、说明、注释等所有文字内容。不要使用英文。

## 编译器和运行环境

**编译器**: gcc (GCC)
- 标准: C11 (`-std=c11`)
- 优化级别: `-O2`
- 警告选项: `-Wall -Wextra`
- 额外编译参数: {extra_flags if extra_flags else "无"}
- 链接: `-lm -lpthread`

**运行环境**: Linux

## 头文件

- 代码中使用的所有标准库函数和类型都必须包含对应的头文件
- 缺少头文件会导致编译失败
- 常用头文件参考：`<stddef.h>` `<stdint.h>` `<stdbool.h>` `<stdlib.h>` `<string.h>` `<stdio.h>` `<time.h>` `<errno.h>` `<stdarg.h>` `<math.h>`
- 线程相关：`<pthread.h>` `<unistd.h>`

## 接口定义

工作目录已预置 `solution.h`（接口定义）和 `test_framework.h`（测试框架），无需自行创建。

```c
{interface}
```

## 题目描述
{description}

## 工具说明

**write_file(command, path, ...)** — 创建或编辑文件，两种模式：
- `create`：创建新文件，需提供 `content`（完整内容）。文件已存在时报错。
- `str_replace`：精确替换已有文件中的内容，需提供 `old_string`（原内容，必须唯一）和 `new_string`（新内容）。

**read_file(path, start_line?, end_line?)** — 读取文件内容，可通过 `start_line` / `end_line` 只读取指定行范围（行号从 1 开始）。

**compile()** — 编译 `solution.c`，生成 `solution.o`，返回编译结果（成功/错误/警告）。

**run_tests()** — 将 `solution.o` 与 `test_self.c` 链接并运行，返回测试输出。需先调用 `compile()` 且已写入 `test_self.c`。

**submit()** — 提交最终代码进行平台评分。

## 建议工作流程

1. 用 `write_file(create)` 写 `solution.c`（实现接口）和 `test_self.c`（自测代码）
2. 调用 `compile()` 检查编译
3. 编译失败时，用 `write_file(str_replace)` 精确修复错误，重新编译
4. 编译通过后，调用 `run_tests()` 运行自测
5. 测试失败时，修改代码，重新编译和测试
6. 所有测试通过后，调用 `submit()` 提交

**注意：**
- `solution.c` 需实现 `solution.h` 中声明的所有函数
- `test_self.c` 需包含 `#include "solution.h"` 和 `main()` 函数，自测应覆盖边界情况
- 修改代码时优先使用 `str_replace` 精确替换，避免重写整个文件
- 你最多可以进行 {MAX_ROUNDS} 轮交互，总时间限制 2 小时
"""


async def run_agent(
    provider: ModelProvider,
    problem: Problem,
    total_timeout: int = AGENT_TOTAL_TIMEOUT,
    on_progress: Optional[Callable[[int], Awaitable[None]]] = None,
) -> AgentRunResult:
    """
    以 Agent 模式运行代码生成。
    on_progress(round_num) 在每轮开始时回调，用于实时写入进度。
    """
    result = AgentRunResult()
    start_time = time.time()
    problem_dir = _find_problem_dir(problem.id)

    # 读取编译参数
    compile_flags = ""
    problem_json = problem_dir / "problem.json"
    if problem_json.exists():
        pdata = json.loads(problem_json.read_text())
        compile_flags = pdata.get("compile_flags", "")

    # 构造初始 prompt
    system_prompt = _build_agent_prompt(problem, problem_dir)
    messages = [{"role": "user", "content": system_prompt}]

    # 临时目录存放当前轮次的代码
    sandbox = Path(tempfile.mkdtemp(prefix="agent_"))

    # 预置题目头文件：solution.h 是接口契约，test_framework.h 是测试框架
    for fname in ("solution.h", "test_framework.h"):
        src = problem_dir / fname
        if not src.exists():
            src = problem_dir.parent / fname
        if src.exists():
            (sandbox / fname).write_text(src.read_text())

    # Token 累计
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_reasoning_tokens = 0

    submitted = False
    no_tool_call_streak = 0

    try:
        for round_num in range(1, MAX_ROUNDS + 1):
            elapsed = time.time() - start_time
            if elapsed >= total_timeout:
                result.finish_reason = "timeout"
                break

            result.rounds = round_num
            round_start = time.time()

            # 上报进度（非阻塞，回调失败不影响主流程）
            if on_progress:
                try:
                    await on_progress(round_num)
                except Exception:
                    pass

            # 调用模型（含 429 重试）
            logger.info(f"[agent] Round {round_num}: calling LLM (messages={len(messages)}, elapsed={elapsed:.0f}s)")
            resp = None
            for attempt in range(4):
                try:
                    resp = await provider._chat(
                        messages,
                        tools=AGENT_TOOLS,
                        temperature=0,
                        max_tokens=AGENT_MAX_TOKENS,
                    )
                    break
                except Exception as e:
                    err_str = str(e)
                    is_429 = "429" in err_str
                    is_5xx = any(f"'{c}" in err_str or f'"{c}' in err_str
                                 for c in ("500", "501", "502", "503", "504"))
                    if is_429 and attempt < 3:
                        wait = (attempt + 1) * 15
                        # 若等待后会超时，放弃重试
                        if time.time() - start_time + wait >= total_timeout:
                            logger.warning(f"[agent] 429 backoff would exceed total_timeout, aborting")
                            result.finish_reason = "timeout"
                            resp = None
                            break
                        logger.warning(f"[agent] 429 rate limit, retrying in {wait}s (attempt {attempt+1}/3)")
                        await asyncio.sleep(wait)
                        continue
                    elif is_5xx and attempt < 2:
                        wait = 10
                        logger.warning(f"[agent] 5xx server error, retrying in {wait}s (attempt {attempt+1}/2): {e}")
                        await asyncio.sleep(wait)
                        continue
                    logger.error(f"[agent] LLM call failed at round {round_num}: {e}")
                    result.error = str(e)
                    result.finish_reason = "error"
                    break
            if resp is None:
                break

            llm_time = time.time() - round_start
            usage = resp.get("usage", {})
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            details = usage.get("completion_tokens_details", {})
            total_reasoning_tokens += details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0

            reasoning = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0
            logger.info(f"[agent] Round {round_num}: LLM responded in {llm_time:.1f}s, completion={usage.get('completion_tokens',0)}, reasoning={reasoning}")

            # 提取回复
            tool_calls = _extract_tool_calls(resp)
            text_content = _extract_text(resp)
            reasoning_content = _extract_reasoning(resp)

            # 把 assistant 消息加入历史
            assistant_msg = resp["choices"][0]["message"]
            messages.append(assistant_msg)

            # 滑动窗口：保留第一条（系统提示）+ 最近 MAX_CONTEXT_MESSAGES 条，防止超出上下文
            MAX_CONTEXT_MESSAGES = 60
            if len(messages) > MAX_CONTEXT_MESSAGES + 1:
                tail = messages[-(MAX_CONTEXT_MESSAGES):]
                # 跳过开头的 tool result 消息（没有对应的 tool_call 会导致 API 报错）
                while tail and tail[0].get("role") == "tool":
                    tail = tail[1:]
                messages = [messages[0]] + tail

            # 分离思考内容和输出
            thinking_content = ""
            output_content = text_content or ""

            # API 明确返回 reasoning_content 字段
            if reasoning_content:
                thinking_content = reasoning_content
            # 输出中包含 </think 标签
            elif "</think" in output_content:
                idx = output_content.find("</think")
                end_pos = output_content.find(">", idx)
                if end_pos >= 0:
                    thinking_content = output_content[:idx].strip()
                    output_content = output_content[end_pos+1:].strip()
                else:
                    thinking_content = output_content[:idx].strip()
                    output_content = ""

            thinking_content = _clean_thinking(thinking_content)
            round_record = {
                "round": round_num,
                "time": round(time.time() - round_start, 1),
                "tool_calls": [],
                "thinking": thinking_content,
                "output": output_content,
            }

            # 如果没有 tool calls，检查是否有纯文本代码输出
            if not tool_calls:
                no_tool_call_streak += 1
                # 模型可能直接输出了文本而没有调用工具
                # 检查是否包含代码
                if text_content:
                    round_record["note"] = f"No tool calls, text only (streak={no_tool_call_streak})"
                else:
                    round_record["note"] = f"No tool calls, empty response (streak={no_tool_call_streak})"
                result.history.append(round_record)

                if no_tool_call_streak >= 3:
                    result.error = "Model failed to use tools for 3 consecutive rounds"
                    result.finish_reason = "error"
                    break

                # 如果连续没有 tool call，可能是模型不知道该干什么了
                # 再给一个提示
                messages.append({
                    "role": "user",
                    "content": "请使用 write_file 工具写入代码文件，然后调用 compile() 编译。如果你认为代码已经完美，请调用 submit() 提交。"
                })
                continue

            no_tool_call_streak = 0

            # 处理每个 tool call
            logger.info(f"[agent] Round {round_num}: processing {len(tool_calls)} tool calls")
            for tc in tool_calls:
                tc_id = tc.get("id", f"call_{round_num}")
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                fn_args_str = fn.get("arguments", "{}")
                logger.info(f"[agent] Round {round_num}: tool={fn_name}")

                try:
                    fn_args = json.loads(fn_args_str)
                except json.JSONDecodeError:
                    fn_args = {}

                tool_result = ""
                tc_record = {"tool": fn_name}

                if fn_name == "write_file":
                    command = fn_args.get("command", "")
                    fpath = fn_args.get("path", "")
                    if not command or not fpath:
                        tool_result = "Error: command and path are required"
                    else:
                        safe = _safe_path(sandbox, fpath)
                        if safe is None:
                            tool_result = "Error: path escapes sandbox directory"
                        elif command == "create":
                            if safe.exists():
                                tool_result = f"Error: {fpath} already exists, use str_replace to modify it"
                            else:
                                content = fn_args.get("content", "")
                                safe.parent.mkdir(parents=True, exist_ok=True)
                                safe.write_text(content)
                                result.files[fpath] = content
                                tool_result = f"File {fpath} created ({len(content)} bytes, {len(content.splitlines())} lines)"
                                tc_record["file"] = fpath
                                tc_record["size"] = len(content)
                        elif command == "str_replace":
                            if not safe.exists():
                                tool_result = f"Error: {fpath} not found, use create to create it first"
                            else:
                                old_string = fn_args.get("old_string", "")
                                new_string = fn_args.get("new_string", "")
                                if not old_string:
                                    tool_result = "Error: old_string is required for str_replace"
                                else:
                                    current = safe.read_text()
                                    count = current.count(old_string)
                                    if count == 0:
                                        tool_result = f"Error: old_string not found in {fpath}"
                                    elif count > 1:
                                        tool_result = f"Error: old_string found {count} times in {fpath}, must be unique. Include more surrounding context."
                                    else:
                                        new_content = current.replace(old_string, new_string, 1)
                                        safe.write_text(new_content)
                                        result.files[fpath] = new_content
                                        tool_result = f"File {fpath} updated ({len(new_content)} bytes, {len(new_content.splitlines())} lines)"
                                        tc_record["file"] = fpath
                                        tc_record["size"] = len(new_content)
                        else:
                            tool_result = f"Error: unknown command '{command}', use 'create' or 'str_replace'"

                elif fn_name == "read_file":
                    fpath = fn_args.get("path", "")
                    if not fpath:
                        tool_result = "Error: path is required"
                    else:
                        safe = _safe_path(sandbox, fpath)
                        if safe is None:
                            tool_result = "Error: path escapes sandbox directory"
                        elif safe.exists():
                            content = safe.read_text()
                            start_line = fn_args.get("start_line")
                            end_line = fn_args.get("end_line")
                            if start_line is not None or end_line is not None:
                                lines = content.splitlines(keepends=True)
                                total = len(lines)
                                s = max(0, (start_line - 1) if start_line else 0)
                                e = min(total, end_line if end_line else total)
                                tool_result = f"[Lines {s+1}-{e} of {total}]\n" + "".join(lines[s:e])
                            else:
                                tool_result = content
                        else:
                            tool_result = f"Error: file {fpath} not found"
                    tc_record["file"] = fpath

                elif fn_name == "compile":
                    comp = await _do_compile(sandbox, compile_flags)
                    tool_result = json.dumps(comp, ensure_ascii=False)
                    tc_record["compile_success"] = comp.get("success", False)

                elif fn_name == "run_tests":
                    run = await _do_run_tests(sandbox, compile_flags)
                    tool_result = json.dumps(run, ensure_ascii=False)
                    tc_record["test_success"] = run.get("success", False)

                elif fn_name == "submit":
                    submitted = True
                    tool_result = "Code submitted for evaluation."
                    tc_record["submitted"] = True

                else:
                    tool_result = f"Unknown tool: {fn_name}"

                # 把 tool result 加入 messages（截断防止超出上下文）
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": _truncate_tool_result(tool_result),
                })
                round_record["tool_calls"].append(tc_record)

                if submitted:
                    break

            result.history.append(round_record)

            if submitted:
                result.finish_reason = "submitted"
                break

        else:
            result.finish_reason = "max_rounds"

    except Exception as e:
        logger.error(f"[agent] Unexpected error: {e}", exc_info=True)
        result.error = str(e)
        result.finish_reason = "error"

    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(sandbox, ignore_errors=True)

    result.total_time = round(time.time() - start_time, 1)
    result.submitted = submitted
    result.total_token_usage = {
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "reasoning_tokens": total_reasoning_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
    }

    return result
