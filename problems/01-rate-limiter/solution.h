#ifndef RATE_LIMITER_H
#define RATE_LIMITER_H

#include <stdbool.h>
#include <stddef.h>

typedef struct {
    long long total_requests;
    long long total_rejected;
    size_t active_clients;
} RateLimiterStats;

typedef struct RateLimiter RateLimiter;

RateLimiter* limiter_create(int max_requests, int window_ms);
void limiter_destroy(RateLimiter* limiter);
bool limiter_allow(RateLimiter* limiter, const char* client_id);
RateLimiterStats limiter_get_stats(RateLimiter* limiter);

#endif
