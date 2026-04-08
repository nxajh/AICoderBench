# 定时器与回调事件循环

## 题目描述

实现一个简单的事件循环，管理定时器及其回调函数。不需要网络 I/O——只需实现定时器的调度、取消和触发。

## 接口

完整接口见 `solution.h`：

- `ev_create()` — 创建事件循环
- `ev_destroy(ev)` — 释放所有资源
- `ev_set_timer(ev, delay_ms, callback, arg)` — 单次定时器，返回 timer_id（成功返回 >=0，失败返回 -1）
- `ev_set_interval(ev, interval_ms, callback, arg)` — 重复定时器，返回 timer_id
- `ev_cancel_timer(ev, timer_id)` — 取消定时器
- `ev_run(ev, timeout_ms)` — 运行循环：处理到期的定时器，在 `timeout_ms` 毫秒后返回。0 = 仅处理已到期的定时器（非阻塞）。-1 = 持续运行直到没有定时器剩余

## 要求

1. 定时器在计划时间附近触发（允许 ±10ms 容差）
2. 单次定时器触发后自动移除
3. 重复定时器在每次触发后自动重新调度
4. 已取消的定时器不会触发
5. `ev_run` 处理所有到期定时器后，根据 `timeout_ms` 决定返回时机
6. 定时器 ID 为唯一的正整数（从 1 开始）
7. 使用最小堆或有序结构实现高效的定时器调度
