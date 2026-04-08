#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include <pthread.h>
#include <unistd.h>
#include "solution.h"

/* TEST basic push/pop */
static void test_basic(void) {
    MPMCQueue *q = mpmc_create(8, sizeof(int));
    TEST_NOT_NULL("basic_create", q);
    int val = 42;
    TEST_TRUE("basic_push", mpmc_push(q, &val, 1000) == true);
    TEST_INT("basic_size", mpmc_size(q), 1);
    int out = 0;
    TEST_TRUE("basic_pop", mpmc_pop(q, &out, 1000) == true);
    TEST_INT("basic_value", out, 42);
    TEST_INT("basic_size_after_pop", mpmc_size(q), 0);
    mpmc_destroy(q);
}

/* TEST full timeout */
static void test_full_timeout(void) {
    MPMCQueue *q = mpmc_create(4, sizeof(int));
    for (int i = 0; i < 4; i++) {
        char name[64];
        snprintf(name, sizeof(name), "fill_push_%d", i);
        TEST_TRUE(name, mpmc_push(q, &i, 0) == true);
    }
    int val = 99;
    TEST_FALSE("full_timeout_rejected", mpmc_push(q, &val, 50));
    mpmc_destroy(q);
}

/* TEST empty timeout */
static void test_empty_timeout(void) {
    MPMCQueue *q = mpmc_create(4, sizeof(int));
    int out = 0;
    TEST_FALSE("empty_timeout_rejected", mpmc_pop(q, &out, 50));
    mpmc_destroy(q);
}

/* TEST MPMC correctness */
#define MPMC_ITEMS 500
#define MPMC_NPROD 4
#define MPMC_NCONS 4

static void *mpmc_producer(void *arg) {
    MPMCQueue *q = (MPMCQueue *)arg;
    (void)arg; /* unused */
    for (int i = 0; i < MPMC_ITEMS; i++) {
        int val = i;
        while (!mpmc_push(q, &val, 1000)) ;
    }
    return NULL;
}

static void *mpmc_consumer(void *arg) {
    MPMCQueue *q = (MPMCQueue *)arg;
    int count = 0;
    int val;
    for (int i = 0; i < MPMC_ITEMS; i++) {
        while (!mpmc_pop(q, &val, 1000)) ;
        count++;
    }
    int *result = malloc(sizeof(int));
    *result = count;
    return result;
}

static void test_mpmc(void) {
    MPMCQueue *q = mpmc_create(64, sizeof(int));
    pthread_t prods[MPMC_NPROD], conss[MPMC_NCONS];
    int ids[MPMC_NPROD];
    for (int i = 0; i < MPMC_NPROD; i++) { ids[i] = i; pthread_create(&prods[i], NULL, mpmc_producer, &ids[i]); }
    for (int i = 0; i < MPMC_NCONS; i++) pthread_create(&conss[i], NULL, mpmc_consumer, q);
    for (int i = 0; i < MPMC_NPROD; i++) pthread_join(prods[i], NULL);
    int total = 0;
    for (int i = 0; i < MPMC_NCONS; i++) {
        int *r;
        pthread_join(conss[i], (void **)&r);
        total += *r;
        free(r);
    }
    TEST_INT("mpmc_total", total, MPMC_NPROD * MPMC_ITEMS);
    mpmc_destroy(q);
}

/* TEST shutdown */
static void test_shutdown(void) {
    MPMCQueue *q = mpmc_create(4, sizeof(int));
    mpmc_shutdown(q);
    int val = 1;
    TEST_FALSE("shutdown_push", mpmc_push(q, &val, 100) == true);
    TEST_FALSE("shutdown_pop", mpmc_pop(q, &val, 100) == true);
    mpmc_destroy(q);
}

int main(void) {
    test_basic();
    test_full_timeout();
    test_empty_timeout();
    test_mpmc();
    test_shutdown();
    TEST_SUMMARY();
}
