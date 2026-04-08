#ifndef EVENT_LOOP_H
#define EVENT_LOOP_H

typedef struct EventLoop EventLoop;

EventLoop* ev_create(void);
void ev_destroy(EventLoop* ev);
int ev_set_timer(EventLoop* ev, int delay_ms, void (*callback)(void*), void* arg);
int ev_set_interval(EventLoop* ev, int interval_ms, void (*callback)(void*), void* arg);
void ev_cancel_timer(EventLoop* ev, int timer_id);
void ev_run(EventLoop* ev, int timeout_ms);

#endif
