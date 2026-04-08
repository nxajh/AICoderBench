# 线程安全LRU缓存

## 题目描述

实现一个线程安全的最近最少使用（LRU）缓存，使用字符串键和字符串值。当缓存达到容量上限时，必须淘汰最近最少使用的条目。

## 接口

完整接口见 `solution.h`：

- `lru_create(capacity)` — 创建指定最大容量的缓存
- `lru_destroy(cache)` — 释放所有资源
- `lru_put(cache, key, value)` — 插入或更新条目；成功返回 true
- `lru_get(cache, key)` — 查找键值；返回堆分配的值拷贝（调用方需自行 `free()`），未找到返回 NULL。访问会更新最近使用时间
- `lru_delete(cache, key)` — 删除条目；找到返回 true
- `lru_size(cache)` — 当前条目数量

## 要求

1. 线程安全：多个线程可以并发调用任意函数
2. LRU 淘汰：缓存满时淘汰最近最少使用的条目
3. `get` 和 `put` 都算作"使用"，会更新最近使用时间
4. `lru_get` 返回的是拷贝——调用方拥有内存所有权，必须调用 `free()` 释放
5. 传入 NULL 的 key/value 应优雅地返回 false/NULL
