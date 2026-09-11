/**
 * 前端运行时契约：zod schema 与后端 Pydantic 模型一一对应。
 * 所有外部数据（REST 响应、SSE 行、localStorage）一律先 parse 再消费，
 * 类型由 z.infer 推断，保证运行时与编译时一致。
 *
 * 另提供 `npm run gen:types`（openapi-typescript）从后端 /openapi.json
 * 生成 REST 类型到 src/api/schema.d.ts，用于交叉核对。
 */
import { z } from "zod";

// ---------- 鉴权 ----------
export const UserSchema = z.object({
  id: z.string().uuid(),
  username: z.string(),
  display_name: z.string(),
  role: z.string(),
  created_at: z.string(),
});
export type User = z.infer<typeof UserSchema>;

export const TokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  user: UserSchema,
});
export type TokenResponse = z.infer<typeof TokenResponseSchema>;

// ---------- 用户模型配置 ----------
export const ModelConfigSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  base_url: z.string().url(),
  model_name: z.string(),
  api_key_masked: z.string(),
  timeout_seconds: z.number(),
  temperature: z.number().nullable(),
  top_p: z.number().nullable(),
  max_tokens: z.number().nullable(),
  price_input_per_million: z.number().nullable(),
  price_output_per_million: z.number().nullable(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ModelConfig = z.infer<typeof ModelConfigSchema>;

export const ModelConfigTestResultSchema = z.object({ ok: z.boolean(), message: z.string() });
export type ModelConfigTestResult = z.infer<typeof ModelConfigTestResultSchema>;

// ---------- 会话与消息 ----------
export const SessionSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Session = z.infer<typeof SessionSchema>;

export const MessageSchema = z.object({
  id: z.string().uuid(),
  session_id: z.string().uuid(),
  role: z.enum(["user", "assistant", "tool"]),
  content: z.string(),
  status: z.enum(["complete", "streaming", "failed", "pending_confirm", "aborted"]),
  trace_id: z.string(),
  citations: z.array(z.record(z.unknown())).nullable(),
  tool_call: z.record(z.unknown()).nullable(),
  usage: z.record(z.unknown()).nullable(),
  error: z.string().nullable(),
  feedback: z.enum(["up", "down"]).nullable().optional(),
  created_at: z.string(),
});
export type Message = z.infer<typeof MessageSchema>;

// ---------- 文档与引用 ----------
export const DocumentSchema = z.object({
  id: z.string().uuid(),
  filename: z.string(),
  content_hash: z.string().nullable(),
  folder: z.string().default(""),
  tags: z.array(z.string()).default([]),
  status: z.enum(["uploaded", "processing", "ready", "failed", "no_text"]),
  chunk_size: z.number(),
  chunk_overlap: z.number(),
  chunk_count: z.number(),
  error: z.string().nullable(),
  version: z.number().default(1),
  ingested_at: z.string().nullable().default(null),
  stale: z.boolean().default(false),
  stale_reasons: z.array(z.string()).default([]),
  created_at: z.string(),
  updated_at: z.string(),
});
export type KnowledgeDocument = z.infer<typeof DocumentSchema>;

/** 就地更新响应：updated=false 表示内容未变化（幂等 no-op） */
export const ContentUpdateResultSchema = z.object({
  updated: z.boolean(),
  document: DocumentSchema,
});
export type ContentUpdateResult = z.infer<typeof ContentUpdateResultSchema>;

export const FeedbackStatsSchema = z.object({
  total_answered: z.number(),
  up_count: z.number(),
  down_count: z.number(),
  feedback_total: z.number(),
  down_rate: z.number(),
});
export type FeedbackStats = z.infer<typeof FeedbackStatsSchema>;

export const ChunkSchema = z.object({
  id: z.string().uuid(),
  document_id: z.string().uuid(),
  document_name: z.string(),
  chunk_index: z.number(),
  content: z.string(),
  start_offset: z.number(),
  end_offset: z.number(),
  total_chunks: z.number(),
});
export type Chunk = z.infer<typeof ChunkSchema>;

// ---------- 配额 ----------
export const QuotaSchema = z.object({
  period: z.string(),
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  total_tokens: z.number(),
  cost_cny: z.number(),
  limit_tokens: z.number(),
  remaining_tokens: z.number(),
  exhausted: z.boolean(),
});
export type Quota = z.infer<typeof QuotaSchema>;

// ---------- 管理后台 ----------
export const AdminUserMonthSchema = z.object({
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  total_tokens: z.number(),
  cost_cny: z.number(),
  limit_tokens: z.number(),
});
export const AdminUserSchema = z.object({
  id: z.string().uuid(),
  username: z.string(),
  display_name: z.string(),
  role: z.string(),
  created_at: z.string(),
  month: AdminUserMonthSchema,
});
export type AdminUser = z.infer<typeof AdminUserSchema>;

export const DailyUsageSchema = z.object({
  date: z.string(),
  calls: z.number(),
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  total_tokens: z.number(),
  cost_cny: z.number(),
});
export type DailyUsage = z.infer<typeof DailyUsageSchema>;

export const UserUsageSchema = z.object({
  user_id: z.string().uuid(),
  username: z.string(),
  calls: z.number(),
  total_tokens: z.number(),
  cost_cny: z.number(),
});
export type UserUsage = z.infer<typeof UserUsageSchema>;

export const ModelUsageSchema = z.object({
  model: z.string(),
  calls: z.number(),
  total_tokens: z.number(),
  cost_cny: z.number(),
});
export type ModelUsage = z.infer<typeof ModelUsageSchema>;

// ---------- SSE 事件：可辨识联合（type 字段） ----------
const TraceId = { trace_id: z.string() } as const;

export const DeltaEventSchema = z.object({
  ...TraceId,
  type: z.literal("delta"),
  content: z.string(),
});
export const CitationEventSchema = z.object({
  ...TraceId,
  type: z.literal("citation"),
  chunk_id: z.string().uuid(),
  document_id: z.string().uuid(),
  document_name: z.string(),
  snippet: z.string(),
});
export const ToolCallEventSchema = z.object({
  ...TraceId,
  type: z.literal("tool_call"),
  message_id: z.string().uuid(),
  tool_call_id: z.string(),
  name: z.string(),
  args: z.record(z.unknown()),
});
export const UsageEventSchema = z.object({
  ...TraceId,
  type: z.literal("usage"),
  prompt_tokens: z.number(),
  completion_tokens: z.number(),
  cost_cny: z.number(),
});
export const ErrorEventSchema = z.object({
  ...TraceId,
  type: z.literal("error"),
  code: z.enum(["TIMEOUT", "MODEL_ERROR", "ABORTED", "QUOTA_EXCEEDED", "INTERNAL"]),
  message: z.string(),
});
export const DoneEventSchema = z.object({
  ...TraceId,
  type: z.literal("done"),
  message_id: z.string().uuid(),
});

export const ChatEventSchema = z.discriminatedUnion("type", [
  DeltaEventSchema,
  CitationEventSchema,
  ToolCallEventSchema,
  UsageEventSchema,
  ErrorEventSchema,
  DoneEventSchema,
]);
export type ChatEvent = z.infer<typeof ChatEventSchema>;

/** unknown 收窄：原始 SSE data 行 -> 强类型 ChatEvent，失败返回 null 并记录。 */
export function parseChatEvent(raw: unknown): ChatEvent | null {
  const result = ChatEventSchema.safeParse(raw);
  if (!result.success) {
    console.error("SSE event parse failed", result.error, raw);
    return null;
  }
  return result.data;
}

// ---------- 工具确认 ----------
export const ToolConfirmResponseSchema = z.object({
  message_id: z.string().uuid(),
  tool_name: z.string(),
  approved: z.boolean(),
  result: z.string(),
});
export type ToolConfirmResponse = z.infer<typeof ToolConfirmResponseSchema>;

// ---------- 统一错误 ----------
export const ApiErrorSchema = z.object({
  detail: z.object({ code: z.string(), message: z.string() }),
});
