#!/bin/bash
set -euo pipefail

RESULT_FILE="${1:-/sandbox/result.json}"
CODE_FILE="${2:-solution.c}"
HEADER_FILE="${3:-}"
EXTRA_FLAGS="${4:-}"
TEST_TIMEOUT="${TEST_TIMEOUT:-30}"
TSAN_TEST_TIMEOUT="${TSAN_TEST_TIMEOUT:-60}"

# 确定测试文件
if [ -f test.c ]; then
    TEST_FILE="test.c"
elif [ -f test_basic.c ]; then
    TEST_FILE="test_basic.c"
else
    TEST_FILE=""
fi

RESULT=$(mktemp)

# 输出辅助函数
json_escape() {
    printf '%s' "$1" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""'
}

# ===== Stage 1: 静态分析 =====
echo '{"stage": "static_analysis"}' >&2

# cppcheck
CPPCHECK_OUT=$(cppcheck --enable=all --suppress=missingInclude \
    --xml 2>&1 "$CODE_FILE" 2>/dev/null || true)
CPPCHECK_ERRORS=$(echo "$CPPCHECK_OUT" | grep -c 'severity="error"' || true)
CPPCHECK_WARNINGS=$(echo "$CPPCHECK_OUT" | grep -c 'severity="warning"' || true)

# lizard (圈复杂度) — 用 --csv 输出，第1列是圈复杂度
LIZARD_CSV=$(lizard --csv "$CODE_FILE" 2>/dev/null || true)
MAX_CYCLO=$(echo "$LIZARD_CSV" | awk -F',' 'NF>=1 && $1~/^[0-9]+$/{if($1>max)max=$1} END{print max+0}')
AVG_CYCLO=$(echo "$LIZARD_CSV" | awk -F',' 'NF>=1 && $1~/^[0-9]+$/{sum+=$1;n++} END{if(n>0)printf "%.1f",sum/n; else print "0.0"}')

# cloc
CLOC_OUT=$(cloc --json "$CODE_FILE" 2>/dev/null || echo '{}')
TOTAL_LOC=$(echo "$CLOC_OUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
c = data.get('C', {})
print(c.get('code', 0))
" 2>/dev/null || echo 0)
COMMENT_RATIO=$(echo "$CLOC_OUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
c = data.get('C', {})
total = c.get('code', 0) + c.get('comment', 0)
print(f'{c.get(\"comment\", 0) / total:.2f}' if total > 0 else '0.00')
" 2>/dev/null || echo "0.00")

# ===== Stage 2: 编译 =====
echo '{"stage": "compile"}' >&2

COMPILE_WARNINGS=0
COMPILE_SUCCESS=false
COMPILE_ERRORS=""
COMPILE_TSAN_SUCCESS=false
COMPILE_ASAN_SUCCESS=false

# 确定编译源文件
if [ -n "$TEST_FILE" ]; then
    SRC_FILES="$TEST_FILE $CODE_FILE"
else
    SRC_FILES="$CODE_FILE"
fi

# 普通编译（C11 标准，支持 alignas 等特性）
# -D_DEFAULT_SOURCE 使 POSIX 函数（如 usleep）在 -std=c11 下可见
if gcc -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -O2 -o solution_normal $SRC_FILES $EXTRA_FLAGS 2>compile.log; then
    COMPILE_SUCCESS=true
    COMPILE_WARNINGS=$(grep -c 'warning:' compile.log || true)
else
    COMPILE_ERRORS=$(cat compile.log)
fi

# TSan 编译
gcc -std=c11 -D_DEFAULT_SOURCE -fsanitize=thread -O1 -o solution_tsan $SRC_FILES $EXTRA_FLAGS 2>/dev/null && COMPILE_TSAN_SUCCESS=true || true

# ASan + UBSan 编译
gcc -std=c11 -D_DEFAULT_SOURCE -fsanitize=address,undefined -O1 -o solution_asan $SRC_FILES $EXTRA_FLAGS 2>/dev/null && COMPILE_ASAN_SUCCESS=true || true

# ===== Stage 3: 测试 =====
echo '{"stage": "test"}' >&2

TESTS_PASSED=0
TESTS_TOTAL=0
TEST_OUTPUT=""
TSAN_ISSUES=0
TSAN_OUTPUT=""
ASAN_ISSUES=0
ASAN_OUTPUT=""
EXEC_TIME_MS=0

if [ "$COMPILE_SUCCESS" = true ]; then
    # 运行功能测试，用 /usr/bin/time 记录执行时间
    set +e
    # Use bash TIMEFORMAT to get milliseconds
    _TIME_START=$(date +%s%N 2>/dev/null || date +%s)
    TEST_OUTPUT=$(timeout "$TEST_TIMEOUT" ./solution_normal 2>&1)
    TEST_EXIT=$?
    _TIME_END=$(date +%s%N 2>/dev/null || date +%s)
    set -e

    # Calculate execution time in milliseconds
    if [[ "$_TIME_START" =~ ^[0-9]+$ && "$_TIME_END" =~ ^[0-9]+$ ]]; then
        if [ ${#_TIME_START} -gt 10 ]; then
            # nanosecond precision (date +%s%N)
            EXEC_TIME_MS=$(( (_TIME_END - _TIME_START) / 1000000 ))
        else
            # second precision
            EXEC_TIME_MS=$(( (_TIME_END - _TIME_START) * 1000 ))
        fi
    fi

    # Output EXEC_TIME_MS for parsing
    echo "EXEC_TIME_MS:${EXEC_TIME_MS}"

    # 优先解析新格式 (test_framework.h): "^PASS:" / "^FAIL:"
    _NEW_PASS=$(echo "$TEST_OUTPUT" | grep -cE '^PASS:' || true)
    _NEW_FAIL=$(echo "$TEST_OUTPUT" | grep -cE '^FAIL:' || true)
    if [ "$_NEW_PASS" -gt 0 ] || [ "$_NEW_FAIL" -gt 0 ]; then
        TESTS_PASSED=$_NEW_PASS
        TESTS_TOTAL=$(( _NEW_PASS + _NEW_FAIL ))
    elif [ $TEST_EXIT -eq 0 ]; then
        # 旧格式兼容：程序正常退出
        TESTS_PASSED=$(echo "$TEST_OUTPUT" | grep -c 'PASS' || true)
        TESTS_TOTAL=$(echo "$TEST_OUTPUT" | grep -cE 'TEST ' || true)
    else
        # 旧格式兼容：程序崩溃，从已有输出统计
        TESTS_PASSED=$(echo "$TEST_OUTPUT" | grep -c 'PASS' || true)
        TESTS_TOTAL=$(echo "$TEST_OUTPUT" | grep -cE 'TEST ' || true)
        TEST_OUTPUT="$TEST_OUTPUT (exit_code=$TEST_EXIT)"
    fi
fi

if [ "$COMPILE_TSAN_SUCCESS" = true ]; then
    TSAN_OUTPUT=$(timeout "$TSAN_TEST_TIMEOUT" ./solution_tsan 2>&1) || true
    TSAN_ISSUES=$(echo "$TSAN_OUTPUT" | grep -c 'ThreadSanitizer' || true)
fi

if [ "$COMPILE_ASAN_SUCCESS" = true ]; then
    ASAN_OUTPUT=$(timeout "$TSAN_TEST_TIMEOUT" ./solution_asan 2>&1) || true
    ASAN_ISSUES=$(echo "$ASAN_OUTPUT" | grep -cE 'AddressSanitizer|UndefinedBehaviorSanitizer' || true)
fi

# ===== 输出结果 =====
# 将 bash true/false 转为 Python True/False
_py_compile_success="True" && [ "$COMPILE_SUCCESS" = true ] || _py_compile_success="False"
_py_compile_tsan="True" && [ "$COMPILE_TSAN_SUCCESS" = true ] || _py_compile_tsan="False"
_py_compile_asan="True" && [ "$COMPILE_ASAN_SUCCESS" = true ] || _py_compile_asan="False"

python3 -c "
import json
result = {
    'compile_success': $_py_compile_success,
    'compile_warnings': $COMPILE_WARNINGS,
    'compile_errors': $(json_escape "$COMPILE_ERRORS"),
    'compile_tsan_success': $_py_compile_tsan,
    'compile_asan_success': $_py_compile_asan,
    'tests_passed': $TESTS_PASSED,
    'tests_total': $TESTS_TOTAL,
    'test_output': $(json_escape "$TEST_OUTPUT"),
    'tsan_issues': $TSAN_ISSUES,
    'tsan_output': $(json_escape "$TSAN_OUTPUT"),
    'asan_issues': $ASAN_ISSUES,
    'asan_output': $(json_escape "$ASAN_OUTPUT"),
    'cppcheck_errors': $CPPCHECK_ERRORS,
    'cppcheck_warnings': $CPPCHECK_WARNINGS,
    'max_cyclomatic': $MAX_CYCLO,
    'avg_cyclomatic': $AVG_CYCLO,
    'total_loc': $TOTAL_LOC,
    'comment_ratio': $COMMENT_RATIO,
    'exec_time_ms': $EXEC_TIME_MS,
}
with open('$RESULT_FILE', 'w') as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
"
