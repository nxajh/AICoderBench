#ifndef ASYNC_LOGGER_H
#define ASYNC_LOGGER_H

#include <stddef.h>

typedef struct AsyncLogger AsyncLogger;

AsyncLogger* logger_create(const char* filepath);
void logger_destroy(AsyncLogger* logger);
void logger_log(AsyncLogger* logger, const char* level, const char* message);
size_t logger_pending(AsyncLogger* logger);

#endif
