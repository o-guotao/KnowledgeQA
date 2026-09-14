# RAG 评测中心（Admin）

## Goal

现有评测是手动脚本（`eval/run_recall_eval.py` 控制台输出 + JSON 落盘），不可持续、无权限、无可视化。本任务落地「评测中心」MVP（已评审的方案 B 之 S1-S4）：数据集/运行记录落库、worker 异步执行配置矩阵评测、Admin 后台新增"评测中心"Tab 可视化，支撑向量化/top_k/BM25/重排等优化的量化决策（对应规划原则"一切用评测说话"）。

权限：全部端点与页面仅 `role=admin`。

## Requirements

### 后端

1. **数据模型**（迁移 `0014`，sqlite 走 create_all）：
   - `eval_datasets`：问句集版本化（name、来源 builtin/上传、条目数、原始 jsonl 内容或文件 key）
   - `eval_runs`：一次评测运行（dataset_id、配置快照 JSON、状态 pending/running/done/failed、汇总指标 JSON：各配置组 recall@k 曲线/MRR/延迟、错误信息、耗时）
   - `eval_run_items`：逐题明细（run_id、题号、问题、gold_doc、各配置组 rank/命中/召回文档列表/各阶段耗时）
2. **评测执行器** `services/eval_runner.py`：抽取 `eval/run_recall_eval.py` 核心逻辑，支持：
   - 配置组矩阵：baseline（单向量）/ hybrid（RRF）/ hybrid_bm25 / hybrid_bm25_rerank
   - top_k 扫描：每组配置输出 K=1..10 的 recall@K
   - 分阶段计时：embedding / 召回 / 重排
   - 通过 `tasks` 表新任务类型 `run_eval` 由 worker 异步执行，状态写回 eval_runs
   - 评测在独立临时 sqlite 知识库进行（与线上数据隔离，沿用现有脚本模式）
3. **API** `/admin/eval/*`（全部 `require_admin`）：
   - 数据集：列表/详情/上传 jsonl/内置样例一键导入/删除
   - 运行：发起（dataset_id + 配置组选择 + top_k 上限）、列表、详情（含逐题明细）、两 run 对比、CSV 导出
4. **LLM 答案正确率（可选开关）**：发起运行时 `with_llm=true` 则每题在召回后调用配置的 LLM 生成回答，统计 `gold_keywords` 命中率（答案正确率）；含注入防护题的结果标记。token 成本在弹窗明确提示，默认关闭。
5. **线上耗时采集**：chat 链路对 召回/重排/LLM TTFT/总时长 打点，`usage_records` 加列落库（随迁移 `0014` 一起）；新增 `/admin/eval/online-stats?days=N` 返回按日 p50/p95 延迟与点踩率。
6. **schema**：eval 相关 pydantic 模型。

### 前端（AdminPage 新增"评测中心"Tab）

5. KPI 卡条：最近完成 run 的 Recall@5 / MRR / 配置组数 / 耗时。
6. 配置对比分组柱状图（各配置组 Recall@5 与 MRR）、top_k 扫描折线图（X=K，Y=Recall@K，多配置多线，实线/虚线区分）。
7. 逐题明细表：可排序，排名变化带 ↑↓ 符号 + 颜色（不只靠颜色）；命中 ✓/✗。
8. 历史 run 列表（配置快照摘要、时间、状态），勾选两个可对比；运行中 run 5s 轮询（终态即停，复用文档页模式）。
9. "运行新评测"弹窗：选数据集、勾配置组、设 top_k 上限、with_llm 开关（默认关，开启时提示 token 成本）。
10. **线上质量区**：延迟趋势折线（按日 p50/p95，来自线上真实请求）+ 点踩率卡片（复用 feedback 统计）。
11. 图表库引入 **Recharts**（仅 admin 路由懒加载，不进主包首屏）。

## Acceptance Criteria

- [ ] admin 导入内置样例数据集 → 发起默认矩阵运行 → worker 异步执行完成 → 页面展示柱状/折线/明细，数据与脚本口径一致
- [ ] 任意两 run 可对比（Recall@K 曲线与逐题 rank 差异可见）
- [ ] 普通用户访问 `/admin/eval/*` → 403；前端无评测入口
- [ ] Recharts 仅在 admin chunk 加载（构建产物分包验证）
- [ ] 非 admin 无法发起评测运行；上传非法 jsonl 有明确 4xx 提示
- [ ] `with_llm=true` 的 run：summary 含各配置组答案正确率（gold_keywords 命中率）
- [ ] 一次真实问答后 `usage_records` 对应行写入分阶段耗时；online-stats 返回 p50/p95 与点踩率，页面趋势图渲染
- [ ] postgres 迁移 upgrade/downgrade 通过；sqlite 正常

## Out of Scope（后续迭代，本期不做）

- CI 回归门禁（S6）
- Langfuse 下钻联动、评测集在线编辑 UI

## Notes

- 核心逻辑复用 `backend/eval/run_recall_eval.py`（三组配置 + recall_hit + MRR 口径已验证）。
- 规范参考：`.trellis/spec/backend/documents-api.md`、AdminPage 现有模式（`api/admin.py` + `require_admin`）。
- 图表 UX：直接标注数值、实/虚线区分系列、图表配数据表 fallback、不只靠颜色传达含义。
