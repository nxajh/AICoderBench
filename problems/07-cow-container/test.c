#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_framework.h"
#include "solution.h"

/* TEST basic get/set */
static void test_basic(void) {
    COWArray *arr = cow_create(10);
    TEST_NOT_NULL("basic_create", arr);
    TEST_INT("basic_refcount_1", cow_refcount(arr), 1);

    TEST_INT("basic_set_idx0", cow_set(arr, 0, 42), 0);
    TEST_INT("basic_set_idx5", cow_set(arr, 5, 99), 0);

    int val = 0;
    TEST_TRUE("basic_get_idx0", cow_get(arr, 0, &val) == 0 && val == 42);
    TEST_TRUE("basic_get_idx5", cow_get(arr, 5, &val) == 0 && val == 99);

    /* out of bounds */
    TEST_INT("basic_oob_get", cow_get(arr, 10, &val), -1);
    TEST_INT("basic_oob_set", cow_set(arr, 10, 1), -1);

    /* default zero */
    TEST_TRUE("basic_default_zero", cow_get(arr, 3, &val) == 0 && val == 0);

    cow_destroy(arr);
}

/* TEST clone shares data */
static void test_clone(void) {
    COWArray *a = cow_create(8);
    cow_set(a, 0, 100);

    COWArray *b = cow_clone(a);
    TEST_INT("clone_refcount_a", cow_refcount(a), 2);
    TEST_INT("clone_refcount_b", cow_refcount(b), 2);

    int val = 0;
    TEST_TRUE("clone_get_b_0", cow_get(b, 0, &val) == 0 && val == 100);

    cow_destroy(b);
    TEST_INT("clone_refcount_a_after_destroy", cow_refcount(a), 1);
    cow_destroy(a);
}

/* TEST cow trigger */
static void test_cow(void) {
    COWArray *a = cow_create(8);
    cow_set(a, 0, 10);
    cow_set(a, 1, 20);

    COWArray *b = cow_clone(a);
    TEST_INT("cow_refcount_shared", cow_refcount(a), 2);

    /* write to b triggers COW */
    cow_set(b, 0, 999);
    TEST_INT("cow_refcount_b_after_write", cow_refcount(b), 1);
    TEST_INT("cow_refcount_a_after_write", cow_refcount(a), 1);

    int val = 0;
    cow_get(a, 0, &val);
    TEST_INT("cow_a_unchanged", val, 10);
    cow_get(b, 0, &val);
    TEST_INT("cow_b_new_value", val, 999);

    cow_get(a, 1, &val);
    TEST_INT("cow_a_idx1", val, 20);
    cow_get(b, 1, &val);
    TEST_INT("cow_b_idx1", val, 20);

    cow_destroy(a);
    cow_destroy(b);
}

/* TEST multi clone destroy order */
static void test_multi_destroy(void) {
    COWArray *a = cow_create(4);
    COWArray *b = cow_clone(a);
    COWArray *c = cow_clone(a);
    TEST_INT("multi_refcount_3", cow_refcount(a), 3);

    cow_destroy(a); /* destroy original first */
    TEST_INT("multi_refcount_b_2", cow_refcount(b), 2);
    cow_destroy(c); /* destroy c before b */
    TEST_INT("multi_refcount_b_1", cow_refcount(b), 1);
    cow_destroy(b);
}

int main(void) {
    test_basic();
    test_clone();
    test_cow();
    test_multi_destroy();
    TEST_SUMMARY();
}
