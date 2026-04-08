#ifndef LRU_CACHE_H
#define LRU_CACHE_H

#include <stddef.h>
#include <stdbool.h>

typedef struct LRUCache LRUCache;

LRUCache* lru_create(size_t capacity);
void lru_destroy(LRUCache* cache);
bool lru_put(LRUCache* cache, const char* key, const char* value);
char* lru_get(LRUCache* cache, const char* key);
bool lru_delete(LRUCache* cache, const char* key);
size_t lru_size(LRUCache* cache);

#endif
