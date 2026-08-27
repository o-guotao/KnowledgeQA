# 证据：一次回滚说明

## 场景 A：数据库迁移回滚

迁移以 Alembic 管理，`alembic/versions/0001_init.py` 实现成对的 `upgrade()`/`downgrade()`。

```bash
# 误执行 upgrade 后回滚到初始状态之前（空库）
docker compose exec backend alembic downgrade base

# 回到最新
docker compose exec backend alembic upgrade head
```

约定：新增迁移必须实现可执行的 `downgrade()`（删表/删列/删索引逆序进行），
涉及数据迁移的， downgrade 中注明数据不可恢复的部分。

## 场景 B：应用版本回滚

镜像按 git tag 构建（`docker build -t web-agent-backend:v0.1.0`）：

```bash
git tag v0.1.0                  # 发布前打 tag
# 新版本异常时：
git checkout v0.1.0
docker compose up -d --build backend worker   # 用旧代码重建并替换
alembic downgrade <上一个迁移版本>              # 若 schema 有变更则同步回退
```

## 场景 C：切分参数回滚（评测场景）

切分参数在入库时固化到 `documents.chunk_size/chunk_overlap`。评测第二组参数效果变差时：

1. `.env` 改回 `CHUNK_SIZE=512 / CHUNK_OVERLAP=64`
2. `docker compose up -d --force-recreate backend worker`
3. 删除文档后重新上传（触发重切分），知识库即回到原参数状态

## 记录样例

| 日期 | 操作 | 原因 | 结果 |
| --- | --- | --- | --- |
| （演示时填写） | alembic downgrade base && upgrade head | 验证迁移可逆 | 7 张表重建成功 |
