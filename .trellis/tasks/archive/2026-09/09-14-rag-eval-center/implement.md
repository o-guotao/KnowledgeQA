# 执行计划 — RAG 评测中心

按序执行；回滚点：步骤 1（迁移 downgrade）、步骤 5 前任意 `git checkout`。

## 1. 数据模型 + 迁移

- [ ] `models/eval.py`：EvalDataset / EvalRun / EvalRunItem 三模型；`models/__init__.py` 注册。
- [ ] `alembic/versions/0014_eval_center.py`（down_revision=`0013_document_visibility`）：三新表 + `usage_records` 加 ttft_ms/total_ms/recall_ms/rerank_ms 四列。
- 校验：迁移模块可导入、链路正确。

## 2. 评测执行器

- [ ] `services/eval_runner.py`：数据集解析、临时库建库（sample_docs 切分+embedding）、配置矩阵（4 组）、top_k 扫描（单次召回多 K 复用）、分阶段计时、summary/items 落库。
- [ ] with_llm 分支：召回后调 provider 生成回答（非流式），gold_keywords 命中率 + 注入题标记。
- [ ] `worker/main.py`：`run_eval` 任务分支 + eval_runs 状态写回（running/done/failed + duration_ms）；with_llm 时放宽 timeout。
- 校验（sqlite + hash embedding 快速路径）：发起 run → 执行 → summary 含 4 组 recall_at_k/mrr，items 行数 = 题数。

## 3. 线上耗时采集

- [ ] `chat.py`：召回/重排/TTFT/流结束四处打点，写 UsageRecord 新列（复用既有事务）。
- 校验：一次真实问答后 usage_records 行四列非空（rerank 未开时允许 NULL）。

## 4. API

- [ ] `schemas/eval.py`；`api/admin/eval.py`（数据集 CRUD/导入、runs 发起/列表/详情/CSV、online-stats）；挂载并复用 `require_admin`。
- [ ] 并发闸：存在 pending/running run → 409 `EVAL_RUN_BUSY`。
- 校验（httpx ASGI）：普通用户 403；admin 导入内置集 → 发起 → 详情结构正确；非法 jsonl 400；online-stats 结构正确。

## 5. 前端

- [ ] `npm i recharts`；`api/schemas.ts` eval zod。
- [ ] AdminPage 改 Tab 壳；`pages/admin/EvalCenterTab.tsx`：KPI 卡、分组柱状、top_k 折线、线上延迟折线+点踩率卡、明细表（↑↓ 双编码）、run 列表勾选对比、NewRunDialog（with_llm 开关+成本提示）、轮询。
- 校验：`npm run build` 通过；构建产物中 recharts 进独立 chunk（非 index 主包）。

## 6. 端到端验证

- [ ] sqlite + fastembed（或 hash 快速路径）跑通完整链路：导入内置集 → 发起 4 组矩阵 → 页面各图表渲染正确。
- [ ] 与 `eval/run_recall_eval.py` 同口径抽对：同一数据集 recall@5/MRR 数量级一致。
- [ ] with_llm run（有 key 环境）答案正确率落库展示；无 key 时该组标记降级不报错。
- [ ] `read_lints` 无新增错误。

## 6. 收尾

- [ ] spec 更新：`.trellis/spec/backend/` 补 eval 子系统约定（任务类型/并发闸/临时库模式）。
- [ ] CHANGELOG 待发版时补；`docs/功能规划.md` 快照 P2 行不动（本项属规划外新增能力，记入 CHANGELOG 下一版）。

## 回滚

- 迁移 `alembic downgrade 0013_document_visibility`；代码 `git checkout`；前端卸载 recharts。
