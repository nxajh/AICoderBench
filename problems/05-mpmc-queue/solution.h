#ifndef MPMC_QUEUE_H
#define MPMC_QUEUE_H

#include <stddef.h>
#include <stdbool.h>

typedef struct MPMCQueue MPMCQueue;

MPMCQueue* mpmc_create(size_t capacity, size_t item_size);
void mpmc_destroy(MPMCQueue* q);
bool mpmc_push(MPMCQueue* q, const void* item, int timeout_ms);
bool mpmc_pop(MPMCQueue* q, void* item, int timeout_ms);
size_t mpmc_size(MPMCQueue* q);
void mpmc_shutdown(MPMCQueue* q);

#endif
