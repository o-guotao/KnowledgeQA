"""重置死信/失败任务与文档状态为 pending/uploaded，便于本地演示重跑。"""
import sqlite3


def main() -> None:
    conn = sqlite3.connect("webagent.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET status='pending', retry_count=0, "
        "next_run_at=datetime('now'), started_at=NULL, error=NULL "
        "WHERE status IN ('dead','failed','running')"
    )
    tasks_reset = cur.rowcount
    cur.execute(
        "UPDATE documents SET status='uploaded', error=NULL "
        "WHERE status IN ('failed','processing')"
    )
    docs_reset = cur.rowcount
    conn.commit()
    conn.close()
    print(f"reset tasks: {tasks_reset}, documents: {docs_reset}")


if __name__ == "__main__":
    main()
