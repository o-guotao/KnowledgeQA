"""演示用：入队一个恒超时的 demo_fail 任务，验证 超时 -> 重试 -> 死信 链路。

用法（TASK_TIMEOUT_SECONDS 建议临时调小，如 5s，加快演示）：
    docker compose exec -e TASK_TIMEOUT_SECONDS=5 backend python -m scripts.enqueue_demo_fail
    docker compose logs -f worker   # 观察 running -> failed(退避重试) -> dead
"""
import asyncio
import uuid

from app.db import SessionLocal
from app.models.task import Task


async def main() -> None:
    trace_id = uuid.uuid4().hex[:16]
    async with SessionLocal() as db:
        task = Task(type="demo_fail", payload={"demo": True}, trace_id=trace_id)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        print(f"enqueued demo_fail task id={task.id} traceId={trace_id}")
        print("查询状态：docker compose exec db psql -U webagent -c 'SELECT id,status,retry_count,error FROM tasks ORDER BY created_at DESC LIMIT 1;'")


if __name__ == "__main__":
    asyncio.run(main())
