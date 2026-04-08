# 固定块内存池分配器

## 题目描述

实现一个固定块内存池分配器。内存池预分配一块连续内存，划分为等大小的块。分配和释放均为 O(1)，使用内嵌空闲链表实现。

## 接口

完整接口见 `solution.h`：

- `pool_create(block_size, block_count)` — 创建指定块大小和块数量的内存池
- `pool_destroy(pool)` — 释放所有内存池内存
- `pool_alloc(pool)` — 分配一个块；内存耗尽时返回 NULL
- `pool_free(pool, block)` — 将块归还到内存池
- `pool_available(pool)` — 当前可用块数量

## 要求

1. 分配和释放均为 O(1)
2. 无可用块时 `pool_alloc` 返回 NULL
3. `pool_free` 传入 NULL 块为空操作（安全）
4. `pool_free` 传入 NULL 池为空操作
5. 已释放的块可以被重新分配
6. 不使用每次分配的堆开销（使用内嵌空闲链表）
