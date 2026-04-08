# 无锁SPSC环形缓冲区

## 题目描述

使用原子操作实现一个单生产者单消费者（SPSC）lock-free 环形缓冲区。缓冲区容量固定，支持任意大小的数据项。

## 接口

完整接口见 `solution.h`：

- `rb_create(capacity, item_size)` — 创建指定容量和数据项大小的环形缓冲区
- `rb_destroy(rb)` — 释放所有资源
- `rb_push(rb, item)` — 推入一个数据项（非阻塞，缓冲区满时返回 false）
- `rb_pop(rb, item)` — 弹出一个数据项（非阻塞，缓冲区空时返回 false）
- `rb_size(rb)` — 当前数据项数量

## 要求

1. 必须是 SPSC 场景下的 lock-free 实现（不使用 mutex）
2. 使用原子操作管理 head/tail 索引
3. 正确的内存序（至少使用 acquire/release 语义）
4. 缓冲区满时 `rb_push` 返回 `false`
5. 缓冲区空时 `rb_pop` 返回 `false`
6. 数据项通过拷贝写入/读出（调用方拥有内存所有权）
