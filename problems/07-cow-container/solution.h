#ifndef COW_ARRAY_H
#define COW_ARRAY_H

#include <stddef.h>

typedef struct COWArray COWArray;

COWArray* cow_create(size_t capacity);
COWArray* cow_clone(COWArray* arr);
void cow_destroy(COWArray* arr);
int cow_get(COWArray* arr, size_t index, int* out);
int cow_set(COWArray* arr, size_t index, int value);
size_t cow_refcount(COWArray* arr);

#endif
