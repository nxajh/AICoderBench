#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include <pthread.h>
#include "solution.h"

static void *rb_producer(void *arg) {
    RingBuffer *rb = (RingBuffer *)arg;
    for (int i = 1; i <= 1000; i++) {
        while (!rb_push(rb, &i)) ;
    }
    return NULL;
}

static void *rb_consumer(void *arg) {
    RingBuffer *rb = (RingBuffer *)arg;
    int *results = malloc(1000 * sizeof(int));
    for (int i = 0; i < 1000; i++) {
        while (!rb_pop(rb, &results[i])) ;
    }
    return results;
}

int main(void) {
    /* TEST basic push/pop */
    {
        RingBuffer *rb = rb_create(16, sizeof(int));
        TEST_NOT_NULL("basic_create", rb);
        int val = 42;
        TEST_TRUE("basic_push", rb_push(rb, &val) == true);
        int out = 0;
        TEST_TRUE("basic_pop", rb_pop(rb, &out) == true);
        TEST_INT("basic_value", out, 42);
        TEST_FALSE("basic_pop_empty", rb_pop(rb, &out));
        rb_destroy(rb);
    }

    /* TEST full */
    {
        RingBuffer *rb = rb_create(16, sizeof(int));
        int val = 0;
        for (int i = 0; i < 16; i++) {
            char name[64];
            snprintf(name, sizeof(name), "fill_push_%d", i);
            TEST_TRUE(name, rb_push(rb, &i) == true);
        }
        TEST_FALSE("full_push_rejected", rb_push(rb, &val));
        rb_destroy(rb);
    }

    /* TEST spsc concurrent */
    {
        RingBuffer *rb = rb_create(32, sizeof(int));
        pthread_t prod, cons;
        pthread_create(&prod, NULL, rb_producer, rb);
        pthread_create(&cons, NULL, rb_consumer, rb);
        int *res;
        pthread_join(prod, NULL);
        pthread_join(cons, (void **)&res);
        for (int i = 0; i < 1000; i++) {
            char name[64];
            snprintf(name, sizeof(name), "spsc_result_%d", i);
            TEST_INT(name, res[i], i + 1);
        }
        free(res);
        rb_destroy(rb);
    }

    TEST_SUMMARY();
}
