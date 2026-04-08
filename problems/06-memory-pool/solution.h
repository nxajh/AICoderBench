#ifndef MEM_POOL_H
#define MEM_POOL_H

#include <stddef.h>

typedef struct MemPool MemPool;

MemPool* pool_create(size_t block_size, size_t block_count);
void pool_destroy(MemPool* pool);
void* pool_alloc(MemPool* pool);
void pool_free(MemPool* pool, void* block);
size_t pool_available(MemPool* pool);

#endif
