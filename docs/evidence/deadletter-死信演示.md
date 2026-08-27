# 证据：一次超时进死信

## 操作步骤

```bash
# 1. 临时把 .env 中 TASK_TIMEOUT_SECONDS 调小到 5，加快演示
docker compose up -d --force-recreate worker

# 2. 入队恒超时演示任务
docker compose exec backend python -m scripts.enqueue_demo_fail
# 输出：enqueued demo_fail task id=<task_id> traceId=<traceId>

# 3. 观察 worker 日志
docker compose logs -f worker

# 4. 查看任务终态
docker compose exec db psql -U webagent -c \
  "SELECT id, type, status, retry_count, error FROM tasks WHERE type='demo_fail';"
```

## 预期日志序列（traceId 一致）

```json
{"level":"INFO","traceId":"<traceId>","msg":"task claimed","extra":{"type":"demo_fail"}}
{"level":"WARNING","traceId":"<traceId>","msg":"task failed, will retry","extra":{"retry":1,"backoff_s":5.0}}
{"level":"WARNING","traceId":"<traceId>","msg":"task failed, will retry","extra":{"retry":2,"backoff_s":10.0}}
{"level":"WARNING","traceId":"<traceId>","msg":"task failed, will retry","extra":{"retry":3,"backoff_s":20.0}}
{"level":"ERROR","traceId":"<traceId>","msg":"task moved to dead letter","event":"task_dead"}
```

## 预期任务状态机

| 时刻 | status | retry_count | error |
| --- | --- | --- | --- |
| 入队 | pending | 0 | NULL |
| 第 1 次超时 | failed | 1 | 任务超时（>5.0s） |
| 第 2 次超时 | failed | 2 | 同上 |
| 第 3 次超时 | failed | 3 | 同上 |
| 超过 max_retries=3 | **dead** | 3 | 同上 |

死信任务不再被 worker 抢占（只消费 pending/failed 且到期的任务），可人工审计后删除或重置。
