# 执行计划：LLM 厂商协议适配层（Anthropic）

## 前置

- 分支：story-1008（继续）；多 Agent 编排已提交（da5fdd7/eee05f1/5fa9962）
- 验收基线：现有 41 测试全绿，任何一步不得变红

## 执行步骤

### 1. 协议字段全链路

- [ ] alembic 迁移 `0015_model_config_protocol.py`：model_configs 加 `protocol String(20) server_default 'openai'`（参考 0014 双方言写法）
- [ ] `models/model_config.py` 加 protocol 列
- [ ] `schemas/model_config.py`：Create/Update/Out 加 `protocol: Literal["openai","anthropic"] = "openai"`
- [ ] `api/model_configs.py`：create/update 保存 protocol
- [ ] `model_configs.py`：ProviderConfig 加 `protocol: str = "openai"`；`resolve_provider_config` 透传；全局兜底恒 openai
- [ ] 验证：迁移在 sqlite 本地库跑通（启动时 alembic upgrade head）；现有测试全绿

### 2. Anthropic 适配层

- [ ] `services/anthropic.py`：`translate_messages`（system 提取/tool_result 转换/tool_use 转换/连续同角色合并）+ `translate_tools`
- [ ] `anthropic.py::stream_chat`：流式事件翻译为三元组；5xx 重试一次/超时不重试；usage 合成与事件顺序（usage → tool_call）与 openai 版一致
- [ ] `anthropic.py::chat`（非流式）：content blocks 拼接、usage 映射
- [ ] `openai_compatible.py`：`stream_chat` 入口按 protocol 分发；`test_provider_connection` 分流（anthropic 最小 messages 请求）
- [ ] `llm_client.py`：`chat` 按 protocol 分发到 `anthropic.chat`，包装为 LLMCallResult；json_mode 在 anthropic 下忽略（宽容解析兜底）
- [ ] 验证：`test_anthropic.py` 新测试全绿 + 既有 41 全绿

### 3. 前端

- [ ] `schemas.ts`：ModelConfigSchema 加 protocol
- [ ] `ModelSettingsPage.tsx`：协议下拉 + base_url 默认值联动 + 配置卡片协议徽标
- [ ] 验证：`npm run build` 通过

### 4. 测试与文档

- [ ] `test_anthropic.py`：翻译/流式/非流式/llm_client 分发/连接测试分流
- [ ] 全量：`backend pytest` + `frontend npm run build`
- [ ] spec/backend/llm-agents.md 增加适配层约定（新协议扩展指引）
- [ ] CHANGELOG.md [未发布] 补充

## 回滚点

- 步骤 1 单独提交（纯增量字段，默认 openai 不改变行为，可独立回滚）
- 步骤 2/3/4 各为一个提交点；适配层异常时删除 anthropic 配置或切回 openai 配置即可，无需 revert

## Review Gates

- 步骤 2 完成后：流式事件顺序与 openai 版逐一对照（usage 先于 tool_call；delta 不过滤 DSML）
- 步骤 4：全量测试绿 + 手工验证 Anthropic 配置的保存/激活/测试/问答全链路（需真实 ANTHROPIC key，无 key 时以单测覆盖为准）
