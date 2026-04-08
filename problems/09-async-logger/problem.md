# 异步日志器

## 题目描述

实现一个异步日志系统。日志消息被加入队列，由后台线程写入文件。调用方不会因文件 I/O 而阻塞。

## 接口

完整接口见 `solution.h`：

- `logger_create(filepath)` — 创建日志器，打开文件，启动后台写入线程
- `logger_destroy(logger)` — 刷新剩余消息，停止写入线程，关闭文件
- `logger_log(logger, level, message)` — 将日志消息加入队列（非阻塞或最小阻塞）
- `logger_pending(logger)` — 等待写入的消息数量

## 要求

1. 后台线程从内部队列消费消息并写入文件
2. `logger_log` 不应因磁盘 I/O 阻塞（仅在队列操作时可能短暂阻塞）
3. 每行日志格式：`[LEVEL] message\n`
4. `logger_destroy` 必须在返回前刷新所有待写入消息
5. 不丢失消息——销毁后所有已记录的消息必须出现在文件中
6. 支持多线程并发调用 `logger_log`，保证线程安全
