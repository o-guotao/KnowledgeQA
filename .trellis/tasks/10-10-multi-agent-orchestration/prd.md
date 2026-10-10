# multi-agent-orchestration

## Goal

按功能规划 P3（docs/功能规划.md:75「检索/总结/校对分工，或工具路由 Agent」）落地轻量多 Agent 编排：查询先经 Router Agent 分类路由到合适的检索策略；回答过程由 Planner 拆解步骤、Executor 执行工具/检索、Reviewer 校验答案充分性；前端以步骤时间线展示编排过程。全部能力可开关、可降级，不影响现有用户体验。

## Background

当前对话是"单 Agent + 固定流水线"：SSE 主链路上串着 query 改写、规则路由（auto_top_k 启发式）、硬编码两轮工具调用等固定节点。`memory.py` 与 `query_rewrite.py` 各自裸写 httpx 非流式调用，无公共封装。

## Requirements

- **统一非流式 LLM client**：收敛 memory.py 与 query_rewrite.py 的裸写 httpx 为公共封装（超时/重试/JSON 结构化输出/计费/tracing 统一），迁移后两处行为不变
- **Router Agent（L4 查询分类路由）**：query 分类（factual/list/comparison/summary）映射召回策略与 top_k；超时/解析失败/开关关闭均自动回退现有 L2 启发式规则
- **Planner-Executor-Reviewer 编排循环**：工具回路从硬编码 2 轮升级为自主多步；最大步数/单步超时/token 预算硬限制防失控；delete_document 等危险操作仍走人工确认闸门
- **步骤时间线**：SSE 新增 agent_step 事件，前端消息中展示可折叠编排步骤（路由决策、计划、工具执行、校验结论），历史消息加载路径同样可渲染
- **降级与开关**：每个 Agent 节点独立 settings 开关，关闭或失败时行为与现状完全一致；默认配置保持关闭（opt-in）
- **评测先行**：Router/编排上线前用现有评测中心对比前后指标，召回指标不回退才允许开启

## Constraints

- 不引入任何新框架/中间件（不引入 LangGraph 等），完全复用现有栈（FastAPI + SQLAlchemy 2.0 asyncio + httpx + Pydantic v2 + React + zod）
- LLM 调用统一走 ProviderConfig，复用 openai_compatible 的协议与计费模式
- 不改 messages 表结构（步骤留痕复用 messages.tool_call JSON 字段，带 kind 判别键）
- 不改 worker；编排全部同步在 chat 请求内完成
- 无新权限点
- 日志只记决策摘要，不记录文档内容

## 已定案的关键机制（评审结论）

- **定案 B4**：Planner 只产出意图序列（PlanStep{type, intent}），不生成工具参数——计划时刻工具未执行，document_id 等参数不存在，意图先于参数是死结；参数由原生 tools 通道（stream_chat 的 delta.tool_calls）生成
- **定案 A2**：确认后终止本轮编排，计划不跨请求持久化——/tools/confirm 是独立请求，编排上下文已销毁；跨请求恢复协议的复杂度远超收益，且删除类操作天然是任务终点

## Acceptance Criteria

- [ ] llm_client 落地后 memory.py / query_rewrite.py 行为与迁移前一致（现有相关测试通过 + 新增 llm_client 单测覆盖 JSON 解析/重试/超时/计费回调）
- [ ] LLM_ROUTER_ENABLED=false 时召回行为与现状逐字节一致；开启时 Router 成功分类走 LLM 决策，失败/超时回退 L2 启发式（单测覆盖映射与降级）
- [ ] AGENT_ORCHESTRATION_ENABLED=false 时工具回路与现有 range(2) 行为一致（回归测试固化）
- [ ] 编排循环受硬限制约束：步数上限、单步超时、token 预算超限即中断并用已有证据直接终答（单测覆盖三种终止路径）
- [ ] delete_document 在编排模式下仍置 pending_confirm 走人工确认；确认走现有 /tools/confirm，确认后终止本轮不续跑（单测覆盖确认闸门）
- [ ] 前端 ChatEventSchema 覆盖 agent_step 事件；步骤时间线实时与历史加载路径均可渲染；编排关闭时前端无感知
- [ ] eval_runner 支持 Router 开/关配置组对比，recall@K/MRR 不回退；编排层评测以"召回不回退 + 人工抽查"为验收口径
- [ ] pytest 全量通过；前端 tsc/lint 通过
- [ ] docs/功能规划.md 中 P3 多 Agent 编排状态更新

## Notes

- 技术设计见 `design.md`，执行计划见 `implement.md`
- 详细评审记录（评测结构 A1-F3 六项维度结论）在本会话历史中，关键定案已并入 design.md
