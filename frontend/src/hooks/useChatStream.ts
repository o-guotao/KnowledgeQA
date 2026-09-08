/**
 * SSE 流式对话 hook：fetch + ReadableStream（EventSource 不支持自定义
 * Authorization 头，也无法 AbortController 停止），按 `data:` 行手动解析，
 * 每行 JSON 先经 zod 收窄（unknown -> ChatEvent）再分发。
 */
import { useCallback, useRef, useState } from "react";

import { getToken } from "../api/client";
import { parseChatEvent, type ChatEvent } from "../api/schemas";

export interface StreamHandlers {
  onEvent: (event: ChatEvent) => void;
  onError?: (message: string) => void;
}

export interface ChatStream {
  streaming: boolean;
  send: (sessionId: string, content: string, handlers: StreamHandlers, topK?: number) => Promise<void>;
  stop: () => void;
}

export function useChatStream(): ChatStream {
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(
    async (sessionId: string, content: string, handlers: StreamHandlers, topK?: number) => {
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      try {
        const response = await fetch("/api/chat/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken() ?? ""}`,
          },
          body: JSON.stringify({ session_id: sessionId, content, ...(topK ? { top_k: topK } : {}) }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          handlers.onError?.(`请求失败（${response.status}）`);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        // 事件间以空行分隔；sse-starlette 默认用 CRLF（\r\n\r\n），也兼容 LF。
        // buffer 只保留末尾可能被截断的不完整事件，其余即时分发 → 逐 token 打字机效果。
        let buffer = "";
        const dispatchBlock = (block: string) => {
          for (const line of block.split(/\r?\n/)) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            let raw: unknown;
            try {
              raw = JSON.parse(trimmed.slice(5).trim());
            } catch {
              console.error("SSE line is not JSON", line);
              continue;
            }
            const event = parseChatEvent(raw);
            if (event) handlers.onEvent(event);
          }
        };
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary = buffer.search(/\r?\n\r?\n/);
          while (boundary !== -1) {
            dispatchBlock(buffer.slice(0, boundary));
            buffer = buffer.slice(boundary).replace(/\r?\n\r?\n/, "");
            boundary = buffer.search(/\r?\n\r?\n/);
          }
        }
        // 流结束：flush 最后一个未以空行结尾的事件（done/error 落盘）
        if (buffer.trim()) dispatchBlock(buffer);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // 用户主动停止：正常路径，由调用方落 aborted 态
          return;
        }
        console.error("stream failed", err);
        handlers.onError?.("连接中断，请重试");
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [],
  );

  return { streaming, send, stop };
}
