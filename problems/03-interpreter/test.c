#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "solution.h"
#include "test_framework.h"

int main(void) {
    /* basic arithmetic */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_FLOAT("2+3*4", interp_eval(ip, "2 + 3 * 4", err), 14);
        TEST_FLOAT("(2+3)*4", interp_eval(ip, "(2 + 3) * 4", err), 20);
        interp_destroy(ip);
    }

    /* power (right-associative) */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_FLOAT("2**3**2", interp_eval(ip, "2 ** 3 ** 2", err), 512);
        interp_destroy(ip);
    }

    /* modulo */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_FLOAT("10%3", interp_eval(ip, "10 % 3", err), 1);
        interp_destroy(ip);
    }

    /* division by zero */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_ERROR("10/0", interp_eval(ip, "10 / 0", err));
        interp_destroy(ip);
    }

    /* comparison */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_FLOAT("1>2", interp_eval(ip, "1 > 2", err), 0);
        TEST_FLOAT("2>=2", interp_eval(ip, "2 >= 2", err), 1);
        interp_destroy(ip);
    }

    /* logical */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_FLOAT("1==1&&0==0", interp_eval(ip, "1 == 1 && 0 == 0", err), 1);
        TEST_FLOAT("!0", interp_eval(ip, "!0", err), 1);
        TEST_FLOAT("!1", interp_eval(ip, "!1", err), 0);
        interp_destroy(ip);
    }

    /* functions */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_FLOAT("max(3,7)", interp_eval(ip, "max(3, 7)", err), 7);
        TEST_FLOAT("min(3,7)", interp_eval(ip, "min(3, 7)", err), 3);
        TEST_FLOAT("abs(-5)", interp_eval(ip, "abs(-5)", err), 5);
        TEST_FLOAT("round(3.6)", interp_eval(ip, "round(3.6)", err), 4);
        interp_destroy(ip);
    }

    /* variables */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_FLOAT("x=10", interp_eval(ip, "x = 10", err), 10);
        TEST_FLOAT("y=x*2+3", interp_eval(ip, "y = x * 2 + 3", err), 23);
        TEST_FLOAT("x+y", interp_eval(ip, "x + y", err), 33);
        interp_destroy(ip);
    }

    /* undefined variable */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_ERROR("undefined_var", interp_eval(ip, "z", err));
        interp_destroy(ip);
    }

    /* unmatched paren */
    {
        Interpreter *ip = interp_create();
        char err[256] = "";
        TEST_ERROR("unmatched_paren", interp_eval(ip, "(1+2", err));
        interp_destroy(ip);
    }

    TEST_SUMMARY();
}
