import { Bot, ThumbsDown, ThumbsUp, User as UserIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { z } from "zod";

import type { Message } from "../api/schemas";
import { cn } from "../lib/utils";
import { ErrorCard } from "./ErrorCard";

const CitationSchema = z.object({
  chunk_id: z.string(),
  document_name: z.string(),
});

export interface DisplayMessage {
  id: string;            // 本地稳定 id，用作 React key，永不变更
  serverId?: string;     // 服务端真实 message_id，用于工具确认等需要回查的场景
  role: "user" | "assistant" | "tool";
  content: string;
  status?: Message["status"] | "local_streaming";
  citations?: Array<z.infer<typeof CitationSchema>>;
  error?: string | null;
  traceId?: string;
  feedback?: "up" | "down" | null;
}

interface MessageItemProps {
  message: DisplayMessage;
  streaming?: boolean;
  onCitationClick?: (chunkId: string) => void;
  onRetry?: () => void;
  onFeedback?: (messageId: string, feedback: "up" | "down" | null) => void;
}

function parseCitations(raw: unknown): Array<z.infer<typeof CitationSchema>> {
  const parsed = z.array(z.unknown()).safeParse(raw);
  if (!parsed.success) return [];
  return parsed.data
    .map((item) => CitationSchema.safeParse(item))
    .filter((r) => r.success)
    .map((r) => r.data);
}

export function MessageItem({ message, streaming, onCitationClick, onRetry, onFeedback }: MessageItemProps) {
  const isUser = message.role === "user";
  const citations = parseCitations(message.citations);
  const canFeedback =
    !isUser && message.role === "assistant" && message.status === "complete" && !!message.serverId;

  const submitFeedback = (value: "up" | "down") => {
    if (!message.serverId || !onFeedback) return;
    // 再点同一按钮 = 取消反馈
    const next = message.feedback === value ? null : value;
    onFeedback(message.serverId, next);
  };

  return (
    <div className={cn("flex gap-3 animate-fade-up", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-brand text-white" : "bg-slate-800 text-white",
        )}
      >
        {isUser ? <UserIcon size={16} /> : <Bot size={16} />}
      </div>
      <div className={cn("max-w-[75%] space-y-2", isUser && "flex flex-col items-end")}>
        {message.status === "failed" ? (
          <ErrorCard
            message={message.error ?? "生成失败"}
            traceId={message.traceId}
            onRetry={onRetry}
          />
        ) : (
          <div
            className={cn(
              "rounded-2xl px-4 py-2.5 text-sm shadow-sm",
              isUser
                ? "rounded-tr-sm bg-brand text-white"
                : message.role === "tool"
                  ? "rounded-tl-sm border border-amber-200 bg-amber-50 text-amber-800"
                  : "rounded-tl-sm bg-white text-ink",
            )}
          >
            {isUser || message.role === "tool" ? (
              <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
            ) : (
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                {streaming && (
                  <span className="ml-0.5 inline-block h-4 w-2 animate-caret-blink bg-brand align-text-bottom" />
                )}
              </div>
            )}
          </div>
        )}
        {!isUser && (citations.length > 0 || canFeedback) && (
          <div className="flex items-center gap-1">
            {citations.map((c, i) => (
              <button
                key={c.chunk_id}
                type="button"
                onClick={() => onCitationClick?.(c.chunk_id)}
                title={c.document_name}
                className="rounded-md bg-brand/10 px-1.5 py-0.5 text-xs font-medium text-brand-dark transition-colors hover:bg-brand hover:text-white cursor-pointer"
              >
                [{i + 1}]
              </button>
            ))}
            {canFeedback && (
              <span className="ml-auto flex items-center gap-1">
                <button
                  type="button"
                  aria-label="回答有用"
                  title="回答有用"
                  onClick={() => submitFeedback("up")}
                  className={cn(
                    "rounded-md p-1 transition-colors cursor-pointer",
                    message.feedback === "up"
                      ? "bg-green-100 text-green-600"
                      : "text-slate-400 hover:bg-slate-100 hover:text-green-600",
                  )}
                >
                  <ThumbsUp size={14} />
                </button>
                <button
                  type="button"
                  aria-label="回答无用"
                  title="回答无用"
                  onClick={() => submitFeedback("down")}
                  className={cn(
                    "rounded-md p-1 transition-colors cursor-pointer",
                    message.feedback === "down"
                      ? "bg-red-100 text-red-600"
                      : "text-slate-400 hover:bg-slate-100 hover:text-red-600",
                  )}
                >
                  <ThumbsDown size={14} />
                </button>
              </span>
            )}
          </div>
        )}
        {message.status === "pending_confirm" && (
          <p className="text-xs text-amber-600">等待工具调用确认…</p>
        )}
        {message.status === "aborted" && (
          <p className="text-xs text-slate-400">已停止生成</p>
        )}
      </div>
    </div>
  );
}
