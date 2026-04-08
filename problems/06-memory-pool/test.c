#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include "solution.h"

/* TEST basic alloc/free */
static void test_basic(void) {
    MemPool *pool = pool_create(64, 10);
    TEST_NOT_NULL("basic_create", pool);
    TEST_INT("basic_available_init", pool_available(pool), 10);

    void *b1 = pool_alloc(pool);
    TEST_NOT_NULL("basic_alloc", b1);
    TEST_INT("basic_available_after_alloc", pool_available(pool), 9);

    memset(b1, 0xAB, 64); /* writable */

    pool_free(pool, b1);
    TEST_INT("basic_available_after_free", pool_available(pool), 10);
    pool_destroy(pool);
}

/* TEST exhaustion */
static void test_exhaust(void) {
    MemPool *pool = pool_create(32, 5);
    void *blocks[5];
    for (int i = 0; i < 5; i++) {
        blocks[i] = pool_alloc(pool);
        char name[64];
        snprintf(name, sizeof(name), "exhaust_alloc_%d", i);
        TEST_NOT_NULL(name, blocks[i]);
    }
    TEST_INT("exhaust_available_0", pool_available(pool), 0);
    TEST_NULL("exhaust_alloc_null", pool_alloc(pool));

    /* free one, alloc again */
    pool_free(pool, blocks[2]);
    TEST_INT("re_alloc_available_1", pool_available(pool), 1);
    void *b = pool_alloc(pool);
    TEST_NOT_NULL("re_alloc_block", b);
    TEST_INT("re_alloc_available_0", pool_available(pool), 0);
    pool_destroy(pool);
}

/* TEST alloc all free all */
static void test_cycle(void) {
    MemPool *pool = pool_create(128, 100);
    void *blocks[100];
    for (int i = 0; i < 100; i++) blocks[i] = pool_alloc(pool);
    TEST_INT("cycle_available_0", pool_available(pool), 0);
    for (int i = 0; i < 100; i++) pool_free(pool, blocks[i]);
    TEST_INT("cycle_available_100", pool_available(pool), 100);
    for (int i = 0; i < 100; i++) {
        blocks[i] = pool_alloc(pool);
        char name[64];
        snprintf(name, sizeof(name), "cycle_realloc_%d", i);
        TEST_NOT_NULL(name, blocks[i]);
    }
    pool_destroy(pool);
}

/* TEST null safety */
static void test_null(void) {
    pool_free(NULL, NULL);
    pool_free(NULL, (void*)1);
    MemPool *pool = pool_create(64, 4);
    pool_free(pool, NULL);
    TEST_INT("null_safety_available", pool_available(pool), 4);
    pool_destroy(pool);
}

int main(void) {
    test_basic();
    test_exhaust();
    test_cycle();
    test_null();
    TEST_SUMMARY();
}
