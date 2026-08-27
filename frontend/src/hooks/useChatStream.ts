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
  send: (sessionId: string, content: string, handlers: StreamHandlers) => Promise<void>;
  stop: () => void;
}

export function useChatStream(): ChatStream {
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(
    async (sessionId: string, content: string, handlers: StreamHandlers) => {
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
          body: JSON.stringify({ session_id: sessionId, content }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          handlers.onError?.(`请求失败（${response.status}）`);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        const processBlocks = (text: string) => {
          for (const line of text.split("\n")) {
            if (!line.startsWith("data:")) continue;
            let raw: unknown;
            try {
              raw = JSON.parse(line.slice(5).trim());
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
          // SSE 事件以空行分隔，data: 前缀承载 JSON
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";
          for (const block of blocks) {
            processBlocks(block);
          }
        }
        // 流结束后处理残留 buffer（最后一个事件可能没有结尾的 \n\n）
        if (buffer.trim()) {
          processBlocks(buffer);
        }
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
