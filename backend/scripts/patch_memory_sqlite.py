"""本地 SQLite 开发库补列（create_all 不给已有表加列；新表自动创建）。
可重复执行：幂等检查每列是否存在。"""
import sqlite3

con = sqlite3.connect("webagent.db")

def ensure_column(table: str, column: str, ddl_type: str, default: str | None = None) -> None:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    if column in cols:
        return
    suffix = f" DEFAULT {default}" if default else ""
    con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}{suffix}")
    print(f"added {table}.{column}")

tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
if "sessions" in tables:
    ensure_column("sessions", "summary", "TEXT")
    ensure_column("sessions", "summarized_until", "DATETIME")
if "memory_items" in tables:
    ensure_column("memory_items", "last_used_at", "DATETIME", "CURRENT_TIMESTAMP")
else:
    print("memory_items 不存在：重启后端/worker 后 create_all 自动创建")

con.commit()
con.close()
print("done")
