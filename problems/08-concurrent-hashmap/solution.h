#ifndef CONC_HASHMAP_H
#define CONC_HASHMAP_H

#include <stddef.h>
#include <stdbool.h>

typedef struct ConcHashMap ConcHashMap;

ConcHashMap* chm_create(size_t num_segments, size_t segment_capacity);
void chm_destroy(ConcHashMap* map);
bool chm_put(ConcHashMap* map, const char* key, const char* value);
char* chm_get(ConcHashMap* map, const char* key);
bool chm_delete(ConcHashMap* map, const char* key);
size_t chm_size(ConcHashMap* map);

#endif
