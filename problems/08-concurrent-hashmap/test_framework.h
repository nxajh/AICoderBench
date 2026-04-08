/* test_framework.h - 极简 C 测试框架
 * 失败不崩溃，继续执行，最后汇总结果
 *
 * 用法：
 *   TEST_INT(name, expr, expected)     - 整数比较
 *   TEST_FLOAT(name, expr, expected)   - 浮点比较 (精度 1e-9)
 *   TEST_TRUE(name, expr)              - 布尔真
 *   TEST_FALSE(name, expr)             - 布尔假
 *   TEST_NULL(name, expr)              - 指针为 NULL
 *   TEST_NOT_NULL(name, expr)          - 指针非 NULL
 *   TEST_ERROR(name, expr)             - 浮点返回 NaN（表示错误）
 *   TEST_STR(name, expr, expected)     - 字符串比较
 *   TEST_SUMMARY()                     - 打印汇总，返回 0/1
 */
#ifndef TEST_FRAMEWORK_H
#define TEST_FRAMEWORK_H

#include <stdio.h>
#include <string.h>
#include <math.h>

static int _tf_passed = 0;
static int _tf_failed = 0;
static int _tf_total  = 0;

#define _TF_CHECK(name, condition, fail_msg) do { \
    _tf_total++; \
    if (condition) { \
        printf("PASS: %s\n", name); \
        _tf_passed++; \
    } else { \
        printf("FAIL: %s %s\n", name, fail_msg); \
        _tf_failed++; \
    } \
} while(0)

/* 整数相等 */
#define TEST_INT(name, expr, expected) do { \
    long _v = (long)(expr); \
    long _e = (long)(expected); \
    char _buf[128]; \
    snprintf(_buf, sizeof(_buf), "(got %ld, want %ld)", _v, _e); \
    _TF_CHECK(name, _v == _e, _buf); \
} while(0)

/* 浮点近似相等 */
#define TEST_FLOAT(name, expr, expected) do { \
    double _v = (double)(expr); \
    double _e = (double)(expected); \
    char _buf[128]; \
    snprintf(_buf, sizeof(_buf), "(got %g, want %g)", _v, _e); \
    _TF_CHECK(name, fabs(_v - _e) < 1e-9, _buf); \
} while(0)

/* 布尔真 */
#define TEST_TRUE(name, expr) \
    _TF_CHECK(name, !!(expr), "(expected true)")

/* 布尔假 */
#define TEST_FALSE(name, expr) \
    _TF_CHECK(name, !(expr), "(expected false)")

/* 指针为 NULL */
#define TEST_NULL(name, expr) \
    _TF_CHECK(name, (expr) == NULL, "(expected NULL)")

/* 指针非 NULL */
#define TEST_NOT_NULL(name, expr) \
    _TF_CHECK(name, (expr) != NULL, "(expected non-NULL)")

/* 浮点返回 NaN（用于错误检测） */
#define TEST_ERROR(name, expr) do { \
    double _v = (double)(expr); \
    char _buf[128]; \
    snprintf(_buf, sizeof(_buf), "(expected NaN/error, got %g)", _v); \
    _TF_CHECK(name, isnan(_v), _buf); \
} while(0)

/* 字符串相等 */
#define TEST_STR(name, expr, expected) do { \
    const char *_v = (expr); \
    const char *_e = (expected); \
    char _buf[256]; \
    snprintf(_buf, sizeof(_buf), "(got \"%s\", want \"%s\")", \
             _v ? _v : "(null)", _e ? _e : "(null)"); \
    _TF_CHECK(name, _v && _e && strcmp(_v, _e) == 0, _buf); \
} while(0)

/* 汇总：打印结果，返回 exit code (0=全过, 1=有失败) */
#define TEST_SUMMARY() do { \
    printf("\n=== TEST RESULTS: %d/%d passed, %d failed ===\n", \
           _tf_passed, _tf_total, _tf_failed); \
    return _tf_failed > 0 ? 1 : 0; \
} while(0)

#endif /* TEST_FRAMEWORK_H */
