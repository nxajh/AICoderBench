#!/bin/bash
set -euo pipefail

RESULT_FILE="${1:-/sandbox/result.json}"
CODE_FILE="${2:-solution.c}"
HEADER_FILE="${3:-}"
EXTRA_FLAGS="${4:-}"
CONCURRENT="${5:-1}"         # 1=并发题, 0=非并发题

TEST_TIMEOUT="${TEST_TIMEOUT:-30}"
TSAN_TEST_TIMEOUT="${TSAN_TEST_TIMEOUT:-60}"
ASAN_TEST_TIMEOUT="${ASAN_TEST_TIMEOUT:-60}"
VALGRIND_TIMEOUT="${VALGRIND_TIMEOUT:-60}"
HELGRIND_TIMEOUT="${HELGRIND_TIMEOUT:-60}"

# 确定测试文件
if [ -f test.c ]; then
    TEST_FILE="test.c"
elif [ -f test_basic.c ]; then
    TEST_FILE="test_basic.c"
else
    TEST_FILE=""
fi

# 输出辅助函数
json_escape() {
    printf '%s' "$1" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""'
}

# ===== Stage 1: 静态分析 =====
echo '{"stage": "static_analysis"}' >&2

# ── 1a. clang-tidy（替代 cppcheck）─────────────────────────────────────
CLANG_TIDY_ERRORS=0
CLANG_TIDY_WARNINGS=0
CLANG_TIDY_OUTPUT=""
if command -v clang-tidy &>/dev/null; then
    CLANG_TIDY_OUTPUT=$(clang-tidy \
        --checks='-*,clang-analyzer-core.*,clang-analyzer-security.*,bugprone-*' \
        "$CODE_FILE" \
        -- -std=c11 -D_DEFAULT_SOURCE $EXTRA_FLAGS 2>/dev/null || true)
    CLANG_TIDY_ERRORS=$(echo "$CLANG_TIDY_OUTPUT" \
        | grep -cE "^(\.\/)?${CODE_FILE}:.*: error:" || true)
    CLANG_TIDY_WARNINGS=$(echo "$CLANG_TIDY_OUTPUT" \
        | grep -cE "^(\.\/)?${CODE_FILE}:.*: warning:" || true)
fi

# ── 1b. 危险 C API 检测（无需外部工具）────────────────────────────────
# 检测 gets/strcpy/strcat/sprintf/system（不含 snprintf/strncpy 等安全版本）
DANGEROUS_APIS=$(grep -cE '\b(gets|strcpy|strcat|sprintf|system)\s*\(' \
    "$CODE_FILE" 2>/dev/null || true)

# ── 1c. lizard（圈复杂度 + 函数长度）──────────────────────────────────
MAX_CYCLO=0
AVG_CYCLO=0.0
MAX_FUNC_LEN=0
if command -v lizard &>/dev/null; then
    # CSV 列顺序：CCN, token_count, NLOC, function_name, ...
    LIZARD_CSV=$(lizard --csv "$CODE_FILE" 2>/dev/null || true)
    MAX_CYCLO=$(echo "$LIZARD_CSV" \
        | awk -F',' 'NF>=1 && $1~/^[0-9]+$/{if($1>max)max=$1} END{print max+0}')
    AVG_CYCLO=$(echo "$LIZARD_CSV" \
        | awk -F',' 'NF>=1 && $1~/^[0-9]+$/{sum+=$1;n++} END{if(n>0)printf "%.1f",sum/n; else print "0.0"}')
    MAX_FUNC_LEN=$(echo "$LIZARD_CSV" \
        | awk -F',' 'NF>=3 && $3~/^[0-9]+$/{if($3>max)max=$3} END{print max+0}')
fi

# ── 1d. cloc（注释率）──────────────────────────────────────────────────
TOTAL_LOC=0
COMMENT_RATIO=0.00
if command -v cloc &>/dev/null; then
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
fi

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

# 普通编译
if gcc -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -O2 \
       -o solution_normal $SRC_FILES $EXTRA_FLAGS 2>compile.log; then
    COMPILE_SUCCESS=true
    COMPILE_WARNINGS=$(grep -c 'warning:' compile.log || true)
else
    COMPILE_ERRORS=$(cat compile.log)
fi

# TSan 编译
gcc -std=c11 -D_DEFAULT_SOURCE -fsanitize=thread -O1 \
    -o solution_tsan $SRC_FILES $EXTRA_FLAGS 2>/dev/null \
    && COMPILE_TSAN_SUCCESS=true || true

# ASan + UBSan 编译
gcc -std=c11 -D_DEFAULT_SOURCE -fsanitize=address,undefined -O1 \
    -o solution_asan $SRC_FILES $EXTRA_FLAGS 2>/dev/null \
    && COMPILE_ASAN_SUCCESS=true || true

# ===== Stage 3: 功能 / TSan / ASan 测试 =====
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
    set +e
    _TIME_START=$(date +%s%N 2>/dev/null || date +%s)
    TEST_OUTPUT=$(timeout "$TEST_TIMEOUT" ./solution_normal 2>&1)
    TEST_EXIT=$?
    _TIME_END=$(date +%s%N 2>/dev/null || date +%s)
    set -e

    if [[ "$_TIME_START" =~ ^[0-9]+$ && "$_TIME_END" =~ ^[0-9]+$ ]]; then
        if [ ${#_TIME_START} -gt 10 ]; then
            EXEC_TIME_MS=$(( (_TIME_END - _TIME_START) / 1000000 ))
        else
            EXEC_TIME_MS=$(( (_TIME_END - _TIME_START) * 1000 ))
        fi
    fi
    echo "EXEC_TIME_MS:${EXEC_TIME_MS}"

    # 解析测试结果（优先新格式 PASS:/FAIL:）
    _NEW_PASS=$(echo "$TEST_OUTPUT" | grep -cE '^PASS:' || true)
    _NEW_FAIL=$(echo "$TEST_OUTPUT" | grep -cE '^FAIL:' || true)
    if [ "$_NEW_PASS" -gt 0 ] || [ "$_NEW_FAIL" -gt 0 ]; then
        TESTS_PASSED=$_NEW_PASS
        TESTS_TOTAL=$(( _NEW_PASS + _NEW_FAIL ))
    elif [ $TEST_EXIT -eq 0 ]; then
        TESTS_PASSED=$(echo "$TEST_OUTPUT" | grep -c 'PASS' || true)
        TESTS_TOTAL=$(echo "$TEST_OUTPUT" | grep -cE 'TEST ' || true)
    else
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
    ASAN_OUTPUT=$(timeout "$ASAN_TEST_TIMEOUT" ./solution_asan 2>&1) || true
    ASAN_ISSUES=$(echo "$ASAN_OUTPUT" \
        | grep -cE 'AddressSanitizer|UndefinedBehaviorSanitizer' || true)
fi

# ===== Stage 4: Valgrind（更精确的内存与线程检测）=====
echo '{"stage": "valgrind"}' >&2

VALGRIND_LEAKS=0
HELGRIND_ISSUES=0

if [ "$COMPILE_SUCCESS" = true ] && command -v valgrind &>/dev/null; then

    # ── 4a. memcheck：精确泄漏计数（直接 + 间接）─────────────────────
    set +e
    _VMEM_OUT=$(timeout "$VALGRIND_TIMEOUT" valgrind \
        --tool=memcheck \
        --leak-check=full \
        --error-exitcode=1 \
        --quiet \
        ./solution_normal 2>&1 || true)
    set -e
    _VLEAK_DIRECT=$(echo "$_VMEM_OUT" \
        | grep "definitely lost:" \
        | grep -oE 'in [0-9]+ blocks' | grep -oE '[0-9]+' | head -1 || echo 0)
    _VLEAK_INDIRECT=$(echo "$_VMEM_OUT" \
        | grep "indirectly lost:" \
        | grep -oE 'in [0-9]+ blocks' | grep -oE '[0-9]+' | head -1 || echo 0)
    VALGRIND_LEAKS=$(( ${_VLEAK_DIRECT:-0} + ${_VLEAK_INDIRECT:-0} ))

    # ── 4b. helgrind：线程竞争（仅并发题）───────────────────────────
    if [ "${CONCURRENT}" = "1" ]; then
        set +e
        _VHEL_OUT=$(timeout "$HELGRIND_TIMEOUT" valgrind \
            --tool=helgrind \
            --error-exitcode=1 \
            --quiet \
            ./solution_normal 2>&1 || true)
        set -e
        HELGRIND_ISSUES=$(echo "$_VHEL_OUT" \
            | grep "ERROR SUMMARY:" \
            | grep -oE '[0-9]+ error' | grep -oE '^[0-9]+' \
            | head -1 || echo 0)
        HELGRIND_ISSUES=${HELGRIND_ISSUES:-0}
    fi
fi

# ===== 输出结果 =====
_py_compile_success="True"  && [ "$COMPILE_SUCCESS"      = true ] || _py_compile_success="False"
_py_compile_tsan="True"     && [ "$COMPILE_TSAN_SUCCESS"  = true ] || _py_compile_tsan="False"
_py_compile_asan="True"     && [ "$COMPILE_ASAN_SUCCESS"  = true ] || _py_compile_asan="False"

python3 -c "
import json
result = {
    'compile_success':        $_py_compile_success,
    'compile_warnings':       $COMPILE_WARNINGS,
    'compile_errors':         $(json_escape "$COMPILE_ERRORS"),
    'compile_tsan_success':   $_py_compile_tsan,
    'compile_asan_success':   $_py_compile_asan,
    'tests_passed':           $TESTS_PASSED,
    'tests_total':            $TESTS_TOTAL,
    'test_output':            $(json_escape "$TEST_OUTPUT"),
    'tsan_issues':            $TSAN_ISSUES,
    'tsan_output':            $(json_escape "$TSAN_OUTPUT"),
    'asan_issues':            $ASAN_ISSUES,
    'asan_output':            $(json_escape "$ASAN_OUTPUT"),
    'clang_tidy_errors':      $CLANG_TIDY_ERRORS,
    'clang_tidy_warnings':    $CLANG_TIDY_WARNINGS,
    'cppcheck_errors':        0,
    'cppcheck_warnings':      0,
    'cppcheck_output':        '',
    'dangerous_apis':         $DANGEROUS_APIS,
    'max_cyclomatic':         $MAX_CYCLO,
    'avg_cyclomatic':         $AVG_CYCLO,
    'max_func_length':        $MAX_FUNC_LEN,
    'total_loc':              $TOTAL_LOC,
    'comment_ratio':          $COMMENT_RATIO,
    'valgrind_leaks':         $VALGRIND_LEAKS,
    'helgrind_issues':        $HELGRIND_ISSUES,
    'exec_time_ms':           $EXEC_TIME_MS,
}
with open('$RESULT_FILE', 'w') as f:
    json.dump(result, f, indent=2)
print(json.dumps(result, indent=2))
"
