#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include "solution.h"
#include "test_framework.h"

// 测试1: 基本限流
static void test_basic(RateLimiter* rl) {
    for (int i = 0; i < 5; i++) {
        TEST_TRUE("basic: first 5 allowed", limiter_allow(rl, "c1"));
    }
    TEST_FALSE("basic: 6th rejected", limiter_allow(rl, "c1"));
    // 不同客户端独立
    TEST_TRUE("basic: different client allowed", limiter_allow(rl, "c2"));

    RateLimiterStats s = limiter_get_stats(rl);
    TEST_INT("basic: total_requests=7", s.total_requests, 7);
    TEST_INT("basic: total_rejected=1", s.total_rejected, 1);
    TEST_INT("basic: active_clients=2", (int)s.active_clients, 2);
}

// 测试2: 边界情况
static void test_edge(RateLimiter* rl) {
    TEST_FALSE("edge: NULL limiter", limiter_allow(NULL, "c1"));
    TEST_FALSE("edge: NULL client_id", limiter_allow(rl, NULL));
}

// 测试3: 并发安全
static void* thread_func(void* arg) {
    RateLimiter* rl = (RateLimiter*)arg;
    for (int i = 0; i < 100; i++) {
        limiter_allow(rl, "concurrent_client");
    }
    return NULL;
}

static void test_concurrent(RateLimiter* rl) {
    enum { NTHREADS = 8 };
    pthread_t threads[NTHREADS];
    for (int i = 0; i < NTHREADS; i++) {
        pthread_create(&threads[i], NULL, thread_func, rl);
    }
    for (int i = 0; i < NTHREADS; i++) {
        pthread_join(threads[i], NULL);
    }
    RateLimiterStats s = limiter_get_stats(rl);
    // 8线程各100次 = 800次请求
    TEST_TRUE("concurrent: total_requests >= 800", s.total_requests >= 800);
}

int main(void) {
    RateLimiter* rl = limiter_create(5, 5000);
    TEST_NOT_NULL("create limiter", rl);

    test_basic(rl);
    test_edge(rl);

    // 新建一个限流器专门测并发
    RateLimiter* rl2 = limiter_create(500, 5000);
    test_concurrent(rl2);
    limiter_destroy(rl2);

    limiter_destroy(rl);
    TEST_SUMMARY();
}
