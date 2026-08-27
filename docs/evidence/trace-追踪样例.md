# 证据：一次完整追踪（traceId 全链路）

## 操作

登录后提问「报销必须在费用发生后多少天内提交？」，前端响应头与每条 SSE 事件均携带同一 `traceId`。

## 链路

1. **前端**：`POST /api/chat/stream`，响应头 `X-Trace-Id: 7f3a9c1e2b4d5a6f`
2. **API 中间件**：`TraceMiddleware` 生成 traceId 并写入日志上下文
3. **SSE 事件**：`citation` / `delta` / `usage` / `done` 每条均含 `"trace_id": "7f3a9c1e2b4d5a6f"`
4. **消息落库**：`messages.trace_id = 7f3a9c1e2b4d5a6f`（用户消息与助手消息同值）
5. **费用记录**：`usage accumulated` 日志行含同一 traceId
6. **异步任务**：上传文档时 `tasks.trace_id` 取上传请求 traceId，worker 处理日志同一值

## 日志样例（JSON 行，内容已截断）

```json
{"ts":"2026-08-27T10:00:01Z","level":"INFO","traceId":"7f3a9c1e2b4d5a6f","msg":"usage accumulated","event":"usage","extra":{"prompt_tokens":812,"completion_tokens":96,"cost_cny":0.002392}}
{"ts":"2026-08-27T10:02:11Z","level":"INFO","traceId":"a1b2c3d4e5f60718","msg":"task claimed","task_id":"...","extra":{"type":"ingest_document"}}
{"ts":"2026-08-27T10:02:19Z","level":"INFO","traceId":"a1b2c3d4e5f60718","msg":"task done","task_id":"...","extra":{"duration_ms":8123.4}}
```

> 复现：任意一次提问后，取响应头 `X-Trace-Id`，`docker compose logs backend worker | grep <traceId>` 即可拉出全链路日志。

## 与 OpenTelemetry 的对照

本实现用 contextvars + JSON 日志落地了 trace 的核心概念（traceId 贯穿、结构化事件、属性附加上下文）。
如需接入 OTel：在 `TraceMiddleware` 与 worker 处替换为 OTel SDK 的 span 生命周期，traceId 语义保持不变。
