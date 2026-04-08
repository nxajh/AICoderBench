#ifndef RING_BUFFER_H
#define RING_BUFFER_H

#include <stddef.h>
#include <stdbool.h>

typedef struct RingBuffer RingBuffer;

RingBuffer* rb_create(size_t capacity, size_t item_size);
void rb_destroy(RingBuffer* rb);
bool rb_push(RingBuffer* rb, const void* item);
bool rb_pop(RingBuffer* rb, void* item);
size_t rb_size(RingBuffer* rb);

#endif
