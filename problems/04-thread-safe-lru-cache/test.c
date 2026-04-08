#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include <pthread.h>
#include "solution.h"

/* TEST basic CRUD */
static void test_basic(void) {
    LRUCache *c = lru_create(3);
    TEST_NOT_NULL("basic_create", c);
    TEST_INT("basic_size_empty", lru_size(c), 0);

    TEST_TRUE("basic_put_a", lru_put(c, "a", "1") == true);
    TEST_TRUE("basic_put_b", lru_put(c, "b", "2") == true);
    TEST_TRUE("basic_put_c", lru_put(c, "c", "3") == true);
    TEST_INT("basic_size_3", lru_size(c), 3);

    char *v = lru_get(c, "a");
    TEST_TRUE("basic_get_a", v != NULL && strcmp(v, "1") == 0);
    free(v);

    TEST_TRUE("basic_delete_b", lru_delete(c, "b") == true);
    TEST_FALSE("basic_delete_b_again", lru_delete(c, "b"));
    TEST_INT("basic_size_2", lru_size(c), 2);

    v = lru_get(c, "b");
    TEST_NULL("basic_get_b_deleted", v);

    lru_destroy(c);
}

/* TEST eviction */
static void test_eviction(void) {
    LRUCache *c = lru_create(3);
    lru_put(c, "a", "1");
    lru_put(c, "b", "2");
    lru_put(c, "c", "3");
    /* a is least recently used if we don't access it */
    lru_get(c, "b");
    lru_get(c, "c");
    lru_put(c, "d", "4"); /* evicts a */
    TEST_NULL("eviction_a_evicted", lru_get(c, "a"));
    char *v = lru_get(c, "d");
    TEST_TRUE("eviction_d_found", v != NULL && strcmp(v, "4") == 0);
    free(v);
    TEST_INT("eviction_size", lru_size(c), 3);
    lru_destroy(c);
}

/* TEST concurrent */
#define NOPS 1000
#define NTHREADS 4

static void *lru_worker(void *arg) {
    LRUCache *c = (LRUCache *)arg;
    char key[32], val[32];
    for (int i = 0; i < NOPS; i++) {
        snprintf(key, sizeof(key), "key%d", i % 50);
        snprintf(val, sizeof(val), "val%d", i);
        lru_put(c, key, val);
        char *v = lru_get(c, key);
        if (v) free(v);
        if (i % 3 == 0) lru_delete(c, key);
    }
    return NULL;
}

static void test_concurrent(void) {
    LRUCache *c = lru_create(100);
    pthread_t threads[NTHREADS];
    for (int i = 0; i < NTHREADS; i++)
        pthread_create(&threads[i], NULL, lru_worker, c);
    for (int i = 0; i < NTHREADS; i++)
        pthread_join(threads[i], NULL);
    TEST_TRUE("concurrent_size_limit", lru_size(c) <= 100);
    lru_destroy(c);
}

int main(void) {
    test_basic();
    test_eviction();
    test_concurrent();
    TEST_SUMMARY();
}
