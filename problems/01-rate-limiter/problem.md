# 高并发滑动窗口限流器

实现一个线程安全的滑动窗口限流器 RateLimiter。

## 接口定义

```c
RateLimiter* limiter_create(int max_requests, int window_ms);
void limiter_destroy(RateLimiter* limiter);
bool limiter_allow(RateLimiter* limiter, const char* client_id);
RateLimiterStats limiter_get_stats(RateLimiter* limiter);
```

其中 RateLimiterStats 定义为：
```c
typedef struct {
    long long total_requests;
    long long total_rejected;
    size_t active_clients;
} RateLimiterStats;
```

## 行为要求

- 每个 client_id 独立计数
- 滑动窗口（不是固定窗口）：任意连续 window_ms 内请求数 ≤ max_requests
- 多线程并发调用 limiter_allow 结果正确，无数据竞争
- 过期的请求记录自动清理，内存不无限增长
- stats 返回：总请求数、拒绝数、当前活跃client数

## 约束

- 代码完整可编译，包含所有必要的 #include
- 通过 TSan 和 ASan 检测
- 正确处理边界情况和错误
- 不使用外部库

请直接输出代码，不要解释。
