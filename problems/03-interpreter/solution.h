#ifndef INTERPRETER_H
#define INTERPRETER_H

typedef struct Interpreter Interpreter;

Interpreter* interp_create(void);
void interp_destroy(Interpreter* interp);
double interp_eval(Interpreter* interp, const char* expr, char* error_buf);

#endif
