#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include <pthread.h>
#include "solution.h"

/* TEST basic CRUD */
static void test_basic(void) {
    ConcHashMap *m = chm_create(16, 64);
    TEST_NOT_NULL("basic_create", m);

    TEST_TRUE("basic_put_hello", chm_put(m, "hello", "world") == true);
    TEST_TRUE("basic_put_foo", chm_put(m, "foo", "bar") == true);

    char *v = chm_get(m, "hello");
    TEST_TRUE("basic_get_hello", v != NULL && strcmp(v, "world") == 0);
    free(v);

    /* update */
    chm_put(m, "hello", "updated");
    v = chm_get(m, "hello");
    TEST_TRUE("basic_get_updated", v != NULL && strcmp(v, "updated") == 0);
    free(v);

    TEST_INT("basic_size_2", chm_size(m), 2);
    TEST_TRUE("basic_delete_foo", chm_delete(m, "foo") == true);
    TEST_FALSE("basic_delete_foo_again", chm_delete(m, "foo"));
    TEST_INT("basic_size_1", chm_size(m), 1);

    v = chm_get(m, "foo");
    TEST_NULL("basic_get_foo_deleted", v);

    /* null safety */
    TEST_FALSE("basic_put_null_key", chm_put(m, NULL, "x") == true);
    TEST_NULL("basic_get_null_key", chm_get(m, NULL));

    chm_destroy(m);
}

/* TEST concurrent */
#define CHM_OPS 2000
#define CHM_THREADS 8

static void *chm_worker(void *arg) {
    ConcHashMap *m = (ConcHashMap *)arg;
    char key[32], val[32];
    for (int i = 0; i < CHM_OPS; i++) {
        snprintf(key, sizeof(key), "key%d", i % 100);
        snprintf(val, sizeof(val), "val%d", i);
        chm_put(m, key, val);
        char *v = chm_get(m, key);
        if (v) free(v);
        if (i % 5 == 0) chm_delete(m, key);
    }
    return NULL;
}

static void test_concurrent(void) {
    ConcHashMap *m = chm_create(8, 256);
    pthread_t threads[CHM_THREADS];
    for (int i = 0; i < CHM_THREADS; i++)
        pthread_create(&threads[i], NULL, chm_worker, m);
    for (int i = 0; i < CHM_THREADS; i++)
        pthread_join(threads[i], NULL);
    size_t s = chm_size(m);
    printf("INFO: concurrent final_size=%zu\n", s);
    chm_destroy(m);
}

int main(void) {
    test_basic();
    test_concurrent();
    TEST_SUMMARY();
}
