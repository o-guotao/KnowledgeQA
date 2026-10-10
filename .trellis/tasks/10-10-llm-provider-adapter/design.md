# 技术设计：LLM 厂商协议适配层（Anthropic）

## 总体策略

**单入口分流**：不新建并行调用链，在既有两个 LLM 入口内部按 `provider.protocol` 分发——`openai_compatible.stream_chat`（流式+tools）与 `llm_client.chat`（非流式+结构化）。所有调用方（chat.py 主回路、orchestrator、Agent 角色、memory、query_rewrite、eval_runner、worker）零改动，协议差异完全封装在适配层内。

## 协议字段全链路

```
ModelConfig.protocol (DB, String(20), server_default 'openai')
  → schemas ModelConfigCreate/Update/Out.protocol (Literal["openai","anthropic"], default openai)
  → ProviderConfig.protocol (frozen dataclass, default "openai")
  → stream_chat / llm_client.chat 内部分发
```

- alembic 迁移 `0015_model_config_protocol.py`：add column，sqlite/postgres 双方言；既有行默认 'openai'
- 全局 DEEPSEEK_* 兜底配置 protocol 恒为 "openai"
- `resolve_provider_config` 透传 protocol

## Anthropic 适配层（`services/anthropic.py`）

### 请求侧

- 端点：`POST {base_url}/v1/messages`；headers：`x-api-key` + `anthropic-version: 2023-06-01`（模块常量）
- `translate_messages(messages) -> (system: str, messages: list)`：
  - 全部 role:system 内容拼接为顶层 `system` 字符串
  - role:tool（OpenAI 格式）→ 并入相邻 user 消息的 content blocks：`{"type":"tool_result","tool_use_id","content"}`
  - assistant 消息的 `tool_calls` → content blocks：`{"type":"tool_use","id","name","input": <arguments JSON parse 后的 dict>}`
  - 连续同角色消息合并（Anthropic 要求 user/assistant 严格交替，首条必须 user）
- `translate_tools(TOOL_DEFINITIONS)`：`{type:"function",function:{name,description,parameters}}` → `{name, description, input_schema: parameters}`
- `max_tokens` 必填：`provider.max_tokens or 4096` 兜底；`temperature`/`top_p` 为 None 时不传
- `stream_options`/`response_format`：Anthropic 无此概念，不下发（json_mode 优雅降级为 prompt 指令 + 客户端宽容解析，llm_client 的 `_extract_json_object` 已具备）

### 流式响应侧（`anthropic_stream_chat`）

Anthropic SSE 事件 → 现有 `(kind, payload, StreamResult)` 三元组，调用方协议零变化：

| Anthropic 事件 | 翻译 |
|---|---|
| `message_start`（usage.input_tokens） | 暂存输入 tokens |
| `content_block_start`（type=text） | 忽略 |
| `content_block_delta`（text_delta） | `yield ("delta", text, result)` |
| `content_block_start`（type=tool_use） | 开 slot：`result.tool_calls[index] = {id, name, arguments: ""}` |
| `content_block_delta`（input_json_delta） | slot.arguments += partial_json |
| `content_block_stop` | 无操作（slot 已闭合） |
| `message_delta`（usage.output_tokens + stop_reason） | 合成 `result.usage = {prompt_tokens, completion_tokens}` |
| 流结束 | 与 openai 版同序：先 `("usage", ...)`，有 tool_calls 再 `("tool_call", ...)` |

### 非流式响应侧（llm_client 分发）

`content` blocks 中 type=text 的 text 拼接为 content；`usage.{input_tokens→prompt_tokens, output_tokens→completion_tokens}`；schema 校验复用 `_extract_json_object` 宽容解析。

### 可靠性对齐

- 重试策略与 openai 版一致：5xx/网络错误重试一次，超时不重试（超时抛 ModelTimeoutError）
- DSML `_MarkupFilter` 仅 openai 路径使用，Anthropic 内容无此问题
- `test_provider_connection` 按 protocol 分流：anthropic 发 `max_tokens=1` 最小 messages 请求

## 前端

- `ModelConfigSchema` 加 `protocol: z.enum(["openai","anthropic"]).default("openai")`
- 模型设置表单加协议下拉（OpenAI 兼容 / Claude (Anthropic)）；选 anthropic 时 base_url 默认值切换为 `https://api.anthropic.com`、placeholder 提示 Messages API
- 配置卡片 `model_name · base_url` 行前加协议 Badge

## 演进预留

- 后续新增协议（Gemini/Azure）：新增 `services/<protocol>.py` 实现同一对入口函数（stream + chat），在两个分发点各加一行分支；`translate_messages` 等按协议独立实现，不抽象公共基类（协议差异大，过早抽象反而脆弱）
- `ANTHROPIC_VERSION` 如需升级改为 settings 配置项

## 目录结构

```
backend/
├── alembic/versions/0015_model_config_protocol.py   # [NEW] protocol 列迁移
├── app/
│   ├── models/model_config.py                       # [MODIFY] protocol 列
│   ├── schemas/model_config.py                      # [MODIFY] Create/Update/Out 加 protocol
│   ├── api/model_configs.py                         # [MODIFY] create/update 透传 protocol；test 按协议分流
│   └── services/
│       ├── model_configs.py                         # [MODIFY] ProviderConfig.protocol + resolve 透传
│       ├── anthropic.py                             # [NEW] Messages API 客户端：消息/tools 翻译、流式事件翻译、非流式调用、连接测试
│       ├── openai_compatible.py                     # [MODIFY] stream_chat 按 protocol 分发；test_provider_connection 分流
│       └── llm_client.py                            # [MODIFY] chat 按 protocol 分发
└── tests/
    └── test_anthropic.py                            # [NEW] 消息/tools 翻译、流式事件翻译、非流式、llm_client 分发

frontend/src/
├── api/schemas.ts                                   # [MODIFY] ModelConfigSchema.protocol
└── pages/ModelSettingsPage.tsx                      # [MODIFY] 协议下拉 + 默认 URL 联动 + 协议徽标
```

## Key Code Structures

```python
# services/anthropic.py — 消息翻译（OpenAI 内部格式 → Anthropic Messages 格式）
def translate_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """提取 system → 顶层字段；role:tool → tool_result 块；assistant.tool_calls → tool_use 块；
    合并连续同角色（Anthropic 要求 user/assistant 严格交替）。"""

def translate_tools(tools: list[dict] | None) -> list[dict] | None:
    """OpenAI function 格式 → Anthropic input_schema 格式。"""

async def stream_chat(
    provider: ProviderConfig, messages: list[dict], tools: list[dict] | None = None
) -> AsyncGenerator[tuple[str, dict | None, StreamResult], None]:
    """Anthropic 流式：事件翻译为与 openai_compatible.stream_chat 完全一致的三元组协议。"""

async def chat(provider: ProviderConfig, messages: list[dict], *, max_tokens: int, ...) -> tuple[str, dict | None]:
    """Anthropic 非流式（供 llm_client 分发）：返回 (content, usage)。"""

# services/model_configs.py — ProviderConfig 加 protocol（frozen，默认 openai 向后兼容）
@dataclass(frozen=True)
class ProviderConfig:
    ...
    protocol: str = "openai"  # openai | anthropic
```
