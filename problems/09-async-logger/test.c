#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include <pthread.h>
#include <unistd.h>
#include "solution.h"

#define TESTFILE "/tmp/test_async_logger.log"

/* TEST basic write */
static void test_basic(void) {
    remove(TESTFILE);
    AsyncLogger *log = logger_create(TESTFILE);
    TEST_NOT_NULL("basic_create", log);

    logger_log(log, "INFO", "hello world");
    logger_log(log, "ERROR", "something broke");
    logger_log(log, "DEBUG", "trace msg");

    logger_destroy(log);

    /* verify file contents */
    FILE *f = fopen(TESTFILE, "r");
    TEST_NOT_NULL("basic_file_open", f);
    char buf[1024];
    int count = 0;
    int found_info = 0, found_error = 0, found_debug = 0;
    while (fgets(buf, sizeof(buf), f)) {
        count++;
        if (strstr(buf, "[INFO] hello world")) found_info = 1;
        if (strstr(buf, "[ERROR] something broke")) found_error = 1;
        if (strstr(buf, "[DEBUG] trace msg")) found_debug = 1;
    }
    fclose(f);
    TEST_INT("basic_line_count", count, 3);
    TEST_TRUE("basic_found_info", found_info);
    TEST_TRUE("basic_found_error", found_error);
    TEST_TRUE("basic_found_debug", found_debug);
}

/* TEST multi-threaded no loss */
#define LOGGER_NMSG 500
#define LOGGER_NTHREADS 4

static void *log_worker(void *arg) {
    AsyncLogger *log = (AsyncLogger *)arg;
    char msg[64];
    for (int i = 0; i < LOGGER_NMSG; i++) {
        snprintf(msg, sizeof(msg), "msg_%d", i);
        logger_log(log, "INFO", msg);
    }
    return NULL;
}

static void test_concurrent(void) {
    remove(TESTFILE);
    AsyncLogger *log = logger_create(TESTFILE);
    pthread_t threads[LOGGER_NTHREADS];
    for (int i = 0; i < LOGGER_NTHREADS; i++)
        pthread_create(&threads[i], NULL, log_worker, log);
    for (int i = 0; i < LOGGER_NTHREADS; i++)
        pthread_join(threads[i], NULL);
    logger_destroy(log);

    /* count lines */
    FILE *f = fopen(TESTFILE, "r");
    TEST_NOT_NULL("concurrent_file_open", f);
    int count = 0;
    char buf[256];
    while (fgets(buf, sizeof(buf), f)) count++;
    fclose(f);
    TEST_INT("concurrent_line_count", count, LOGGER_NTHREADS * LOGGER_NMSG);
}

/* TEST flush on destroy */
static void test_flush(void) {
    remove(TESTFILE);
    AsyncLogger *log = logger_create(TESTFILE);
    for (int i = 0; i < 1000; i++) {
        char msg[64];
        snprintf(msg, sizeof(msg), "flush_%d", i);
        logger_log(log, "INFO", msg);
    }
    logger_destroy(log);

    FILE *f = fopen(TESTFILE, "r");
    TEST_NOT_NULL("flush_file_open", f);
    int count = 0;
    char buf[256];
    while (fgets(buf, sizeof(buf), f)) count++;
    fclose(f);
    TEST_INT("flush_line_count", count, 1000);
}

int main(void) {
    test_basic();
    test_concurrent();
    test_flush();
    TEST_SUMMARY();
}
