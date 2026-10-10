# 执行计划：多 Agent 编排

## 前置

- 分支：story-1008（当前分支，继续在其上开发）
- 全程 feature flag 默认关闭（opt-in），任何一层出问题可用开关回退，无需 revert 代码

## 执行步骤（按依赖顺序）

### 1. 统一非流式 LLM client（unify-llm-client）

- [ ] 新增 `backend/app/services/llm_client.py`：收完整 ProviderConfig；非流式 chat；response_format JSON + Pydantic 校验；超时（min(provider.timeout, 节点上限)）；仅 5xx/网络错误重试一次，超时不重试；usage 回调；Langfuse 埋点
- [ ] 迁移 `memory.py:_chat`（:54）到 llm_client，行为不变
- [ ] 迁移 `query_rewrite.py:rewrite_query`（:72-98）到 llm_client，行为不变
- [ ] 验证：`pytest backend/tests -k "memory or rewrite"`；`test_llm_client.py` 新增（JSON 解析/重试/超时/计费回调）

### 2. Agent 底座（agents-foundation）

- [ ] `agents/__init__.py` 包导出
- [ ] `agents/steps.py`：AgentStep + SSE 序列化 + kind="agent_steps" 留痕格式
- [ ] `agents/context.py`：AgentContext（证据集含 chunks 与 tool 结果两类；token 预算消耗追踪）
- [ ] `agents/roles.py`：角色协议（name + prompt 构建器 + IO schema + 执行函数）；prompt 模板统一含注入防护约束声明 + RETRIEVED_DATA 分隔符
- [ ] `config.py` 新增：llm_router_enabled / agent_orchestration_enabled / agent_max_steps(4) / agent_token_budget(8000) / agent_step_timeout，默认关闭
- [ ] 验证：`pytest backend/tests -k agents`（底座序列化/预算追踪单测）

### 3. Router Agent（router-agent）

- [ ] `agents/router.py`：分类提示词 + RouteDecision schema + top_k 映射（factual→3, list/comparison→10, summary→8）+ RouterFallback 异常
- [ ] Router 缓存：(session_id, hash(retrieval_query))，TTL 5 分钟，每 session 50 条 LRU
- [ ] 接入 `chat.py:212`：开关开 → Router；失败/关闭 → 回退 auto_top_k（rag.py 签名兼容，L2 保留）
- [ ] 发 agent_step(router) 事件（位于 citation 之前，按实际时序）
- [ ] eval_runner 配置组扩展：_ENV_KEYS 加 LLM_ROUTER_ENABLED，新增 router/router_off 对比组
- [ ] 验证：test_agents.py Router 用例（映射/降级/缓存）；eval_runner 两组对比 recall@K/MRR 不回退

### 4. 编排循环（orchestrator-loop）

- [ ] 先用 code-explorer 子代理确认 chat.py 工具回路、tools.py 确认链路、retrieve/rerank 调用点的精确替换清单
- [ ] `agents/planner.py`：Planner（Plan/PlanStep schema，≤3 步仅意图）+ Reviewer（充分性校验），JSON 强校验，失败即降级
- [ ] `agents/orchestrator.py`：run_orchestrated——Planner→Executor（retrieve/tool/answer 三类步骤语义按定案 B4）→Reviewer；硬限制；断连检查（每步骤边界 request.is_disconnected()）；REQUIRE_CONFIRM 终止（定案 A2）；异常中断用已有证据直接终答
- [ ] 改造 `chat.py:262-353`：开关关 → 现有 range(2)（回归测试固化行为等价）；开 → orchestrator
- [ ] Agent 节点计费：accumulate_usage + UsageRecord（model 字段带 `[role]` 后缀）；Langfuse trace_generation 子 span
- [ ] 清理 chat.py:350-351 dead usage 分支
- [ ] 验证：test_agents.py 编排用例（步数上限/token 预算/Reviewer 终止/确认闸门/断连）；开关关闭回归测试

### 5. 步骤时间线 UI（step-timeline-ui）

- [ ] `schemas.ts`：AgentStepEventSchema 加入 ChatEventSchema 联合
- [ ] `AgentStepTimeline.tsx`：可折叠步骤时间线（沿用引用面板样式；running 状态展示）
- [ ] `MessageItem.tsx`：消息头部挂载时间线；历史加载从 tool_call(kind=agent_steps) 恢复；避免与原生 tool_call 事件双份展示
- [ ] `ChatPage.tsx`：SSE 消费收集 agent_step 挂到消息
- [ ] 验证：`npm run build`（tsc）+ lint；手工验证编排开/关两种模式前端表现

### 6. 评测、测试与文档（eval-tests-docs）

- [ ] 单测全量：`cd backend && pytest`
- [ ] 前端：`cd frontend && npm run build && npm run lint`
- [ ] eval_runner 对比：Router 开/关召回指标；编排开/关召回指标 + 人工抽查答案质量
- [ ] 更新 docs/功能规划.md 中 P3 多 Agent 编排状态
- [ ] 更新 CHANGELOG.md

## 回滚点

- 任一层完成即是一个可独立提交的回滚点（每层独立 feature flag，提交顺序同执行顺序）
- 线上异常：关闭对应 env 开关即回退到改造前行为，无需 revert

## Review Gates

- 步骤 3 完成后：Router 接入点唯一性 + 降级路径 review
- 步骤 4 完成后：SSE 事件顺序契约 + 确认闸门语义 review（对照 design.md 定案 A2/B4）
- 步骤 6：全量测试绿 + 评测指标不回退，方可在部署环境开启开关（仓库默认仍关闭）
