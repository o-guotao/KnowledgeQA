# llm-provider-adapter

## Goal

为模型配置增加协议适配层：`ProviderConfig` 支持 `protocol`（openai | anthropic），实现 Anthropic Messages API 的完整映射（流式/tools/非流式结构化输出），厂商不支持的能力按现有降级链优雅退化。首个适配目标为 Claude (Anthropic)，架构上为后续协议（Gemini/Azure）预留扩展点。

## Background

当前代码仅支持 OpenAI Chat Completions 兼容协议（`openai_compatible.py` 流式 + `llm_client.py` 非流式），Claude 的 Messages API（system 独立字段、tool_use/tool_result 块、不同流式事件类型）无法接入。

## Requirements

- **协议字段**：ModelConfig/ProviderConfig/schemas 全链路增加 `protocol`（默认 openai，向后兼容既有配置与 DB 数据）
- **Anthropic 适配**：Messages API 完整映射——消息翻译（system 提取/tool_result 转换/连续同角色合并）、tools 定义翻译、流式 SSE 事件翻译为现有三元组协议（delta/usage/tool_call）、usage 字段映射（input/output_tokens → prompt/completion_tokens）
- **统一分流**：`stream_chat` 与 `llm_client.chat` 两个既有入口内部按 protocol 分发，所有调用方（chat.py/orchestrator/agents/memory/query_rewrite/eval_runner/worker）零改动
- **优雅降级**：Anthropic 无 `response_format`——json_mode 退化为 prompt 指令 + 宽容解析兜底；不支持的能力沿现有降级链（Router 回退 L2、编排回退旧回路），不阻断对话
- **UI**：模型设置页增加协议选择（OpenAI 兼容 / Claude Anthropic），选 Anthropic 时 base_url 默认 `https://api.anthropic.com`；配置卡片显示协议徽标
- **测试连接**：`/model-configs/{id}/test` 按协议发最小请求

## Constraints

- 不引入 SDK（anthropic-python 等），httpx 直连（与现有栈一致）
- 既有 OpenAI 路径行为零变化（41 个现有测试全绿为验收线）
- URL 校验规则不变（Anthropic 官方端点为 HTTPS 公网，天然过校验）
- DSML _MarkupFilter 仅作用于 openai 协议路径
- Anthropic API 版本头固定 `anthropic-version: 2023-06-01`（常量，后续可配）

## Acceptance Criteria

- [ ] alembic 迁移：model_configs 加 protocol 列（server_default 'openai'），sqlite/postgres 双方言可迁移，既有数据默认为 openai
- [ ] Anthropic 消息翻译单测：system 提取、role:tool → tool_result 块、assistant tool_calls → tool_use 块、连续同角色合并
- [ ] Anthropic 流式翻译单测：text_delta → delta、tool_use 块（input_json_delta 累积）→ tool_call、message_start/message_delta usage 合成
- [ ] llm_client anthropic 分发单测：非流式调用返回 LLMCallResult（content/usage/messages），schema 校验走宽容解析
- [ ] 既有 41 个测试全绿（openai 默认路径零变化）；前端 tsc build 通过
- [ ] 模型设置页可选协议并保存/激活/测试 Anthropic 配置（手工验证）
- [ ] spec/backend/llm-agents.md 更新适配层约定

## Notes

- 技术设计见 `design.md`，执行计划见 `implement.md`
