# MPMC有界阻塞队列

## 题目描述

实现一个多生产者多消费者（MPMC）有界阻塞队列。当队列满时 push 阻塞，队列空时 pop 阻塞，支持可配置的超时时间。

## 接口

完整接口见 `solution.h`：

- `mpmc_create(capacity, item_size)` — 创建队列
- `mpmc_destroy(q)` — 释放资源
- `mpmc_push(q, item, timeout_ms)` — 推入数据项；队列满时阻塞；超时或关闭时返回 false
- `mpmc_pop(q, item, timeout_ms)` — 弹出数据项；队列空时阻塞；超时或关闭时返回 false
- `mpmc_size(q)` — 当前数据项数量
- `mpmc_shutdown(q)` — 发出关闭信号；唤醒所有等待线程；后续 push/pop 返回 false

## 要求

1. 支持多生产者和多消费者的线程安全
2. 使用 mutex + 条件变量（或等价机制）
3. `timeout_ms < 0` 表示无限等待；`timeout_ms == 0` 表示非阻塞
4. 调用 `mpmc_shutdown` 后，所有阻塞中和未来的 push/pop 均返回 false
5. 数据项按 `item_size` 大小进行拷贝写入/读出
