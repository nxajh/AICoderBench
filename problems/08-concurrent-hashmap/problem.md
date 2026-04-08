# 分段锁并发哈希表

## 题目描述

使用分段锁（striped locking）实现一个并发哈希表，存储字符串键值对。每个分段拥有独立的锁，允许对不同分段的并发访问。

## 接口

完整接口见 `solution.h`：

- `chm_create(num_segments, segment_capacity)` — 创建 N 个分段的哈希表，每个分段最多容纳 segment_capacity 个条目
- `chm_destroy(map)` — 释放所有资源
- `chm_put(map, key, value)` — 插入或更新条目；成功返回 true
- `chm_get(map, key)` — 查找键值；返回堆分配的拷贝（调用方需 `free()`），未找到返回 NULL
- `chm_delete(map, key)` — 删除条目；找到返回 true
- `chm_size(map)` — 所有分段的总条目数

## 要求

1. 通过分段锁实现线程安全（每个分段拥有独立的 mutex）
2. 键决定所属分段（例如 `hash(key) % num_segments`）
3. `chm_get` 返回的是拷贝——调用方必须调用 `free()` 释放
4. 对已存在的键执行 `chm_put` 会更新值
5. 传入 NULL 的 key/value 应优雅地返回 false/NULL
6. `chm_size` 应基本准确（无并发时精确，有并发时允许小幅偏差）
