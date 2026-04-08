#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include <unistd.h>
#include "solution.h"

/* TEST one-shot timer */
static void oneshot_cb(void *arg) {
    int *count = (int *)arg;
    (*count)++;
}

static void test_oneshot(void) {
    EventLoop *ev = ev_create();
    int count = 0;
    int tid = ev_set_timer(ev, 50, oneshot_cb, &count);
    TEST_TRUE("oneshot_timer_id", tid >= 0);

    ev_run(ev, 100); /* run for 100ms */
    TEST_INT("oneshot_fired_once", count, 1);

    /* should not fire again */
    ev_run(ev, 100);
    TEST_INT("oneshot_no_refire", count, 1);

    ev_destroy(ev);
}

/* TEST repeating timer */
static void test_interval(void) {
    EventLoop *ev = ev_create();
    int count = 0;
    int tid = ev_set_interval(ev, 50, oneshot_cb, &count);
    TEST_TRUE("interval_timer_id", tid >= 0);

    ev_run(ev, 200); /* should fire ~3-4 times */
    TEST_TRUE("interval_fired_multiple", count >= 3);

    ev_destroy(ev);
}

/* TEST cancel */
static void test_cancel(void) {
    EventLoop *ev = ev_create();
    int count = 0;
    int tid = ev_set_timer(ev, 100, oneshot_cb, &count);
    ev_cancel_timer(ev, tid);

    ev_run(ev, 200);
    TEST_INT("cancel_no_fire", count, 0);

    ev_destroy(ev);
}

/* TEST ordering */
static int order_log[10];
static int order_idx = 0;

static void order_cb(void *arg) {
    order_log[order_idx++] = (int)(long)arg;
}

static void test_ordering(void) {
    EventLoop *ev = ev_create();
    order_idx = 0;

    ev_set_timer(ev, 100, order_cb, (void*)3L);
    ev_set_timer(ev, 30, order_cb, (void*)1L);
    ev_set_timer(ev, 60, order_cb, (void*)2L);

    ev_run(ev, 200);
    TEST_INT("ordering_count", order_idx, 3);
    TEST_INT("ordering_first", order_log[0], 1);
    TEST_INT("ordering_second", order_log[1], 2);
    TEST_INT("ordering_third", order_log[2], 3);

    ev_destroy(ev);
}

/* TEST non-blocking run (timeout_ms=0) */
static void test_nonblocking(void) {
    EventLoop *ev = ev_create();
    int count = 0;
    ev_set_timer(ev, 50, oneshot_cb, &count);

    ev_run(ev, 0); /* non-blocking, timer not due yet */
    TEST_INT("nonblocking_no_fire", count, 0);

    usleep(60000); /* wait 60ms */
    ev_run(ev, 0); /* now it should fire */
    TEST_INT("nonblocking_fired", count, 1);

    ev_destroy(ev);
}

int main(void) {
    test_oneshot();
    test_interval();
    test_cancel();
    test_ordering();
    test_nonblocking();
    TEST_SUMMARY();
}
