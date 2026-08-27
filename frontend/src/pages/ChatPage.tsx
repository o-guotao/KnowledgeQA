import { LogOut } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";

import { del, get, post } from "../api/client";
import {
  MessageSchema,
  SessionSchema,
  type ChatEvent,
  type Session,
} from "../api/schemas";
import { useAuth } from "../auth/AuthContext";
import { ChatInput } from "../components/ChatInput";
import { CitationPanel } from "../components/CitationPanel";
import { DocumentManager } from "../components/DocumentManager";
import { MessageItem, type DisplayMessage } from "../components/MessageItem";
import { QuotaBadge } from "../components/QuotaBadge";
import { SessionList } from "../components/SessionList";
import { ToolConfirmDialog } from "../components/ToolConfirmDialog";
import { useChatStream } from "../hooks/useChatStream";

type PendingToolCall = Extract<ChatEvent, { type: "tool_call" }>;

let localId = 0;
const nextLocalId = () => `local-${++localId}`;

export function ChatPage() {
  const { user, logout } = useAuth();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [toolCall, setToolCall] = useState<PendingToolCall | null>(null);
  const [quotaRefreshKey, setQuotaRefreshKey] = useState(0);
  const [quotaExhausted, setQuotaExhausted] = useState(false);
  const lastQuestionRef = useRef<string>("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const { streaming, send, stop } = useChatStream();

  const refreshSessions = useCallback(() => {
    get("/sessions", z.array(SessionSchema))
      .then(setSessions)
      .catch((err) => console.error("sessions fetch failed", err));
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  // 选中会话时加载历史消息
  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    get(`/sessions/${activeId}/messages`, z.array(MessageSchema))
      .then((rows) =>
        setMessages(
          rows
            .filter((m) => m.status !== "streaming")
            .map((m) => ({
              id: m.id,
              role: m.role,
              content: m.content,
              status: m.status,
              citations: (m.citations ?? undefined) as DisplayMessage["citations"],
              error: m.error,
              traceId: m.trace_id,
            })),
        ),
      )
      .catch((err) => console.error("messages fetch failed", err));
  }, [activeId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const createSession = useCallback(async () => {
    const session = await post("/sessions", { title: "新会话" }, SessionSchema);
    setSessions((prev) => [session, ...prev]);
    setActiveId(session.id);
  }, []);

  const deleteSession = useCallback(
    async (id: string) => {
      await del(`/sessions/${id}`);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeId === id) setActiveId(null);
    },
    [activeId],
  );

  const handleEvent = useCallback((localAssistantId: string, event: ChatEvent) => {
    switch (event.type) {
      case "delta":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === localAssistantId ? { ...m, content: m.content + event.content } : m,
          ),
        );
        break;
      case "citation":
        setMessages((prev) =>
          prev.map((m) =>
            m.id === localAssistantId
              ? {
                  ...m,
                  citations: [
                    ...(m.citations ?? []),
                    { chunk_id: event.chunk_id, document_name: event.document_name },
                  ],
                }
              : m,
          ),
        );
        break;
      case "usage":
        setQuotaRefreshKey((k) => k + 1);
        break;
      case "tool_call":
        setToolCall(event);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === localAssistantId
              ? { ...m, serverId: event.message_id, status: "pending_confirm" as const }
              : m,
          ),
        );
        break;
      case "error":
        if (event.code === "QUOTA_EXCEEDED") setQuotaExhausted(true);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === localAssistantId
              ? { ...m, status: "failed", error: event.message, traceId: event.trace_id }
              : m,
          ),
        );
        break;
      case "done":
        // 只更新 serverId 与 status，不替换本地 id（保持 React key 稳定，避免重挂载闪烁）
        setMessages((prev) =>
          prev.map((m) =>
            m.id === localAssistantId && m.status !== "pending_confirm"
              ? { ...m, serverId: event.message_id, status: "complete" as const }
              : m,
          ),
        );
        break;
    }
  }, []);

  const ask = useCallback(
    async (content: string) => {
      let sessionId = activeId;
      if (!sessionId) {
        const session = await post("/sessions", { title: "新会话" }, SessionSchema);
        setSessions((prev) => [session, ...prev]);
        setActiveId(session.id);
        sessionId = session.id;
      }
      lastQuestionRef.current = content;
      const assistantLocalId = nextLocalId();
      setMessages((prev) => [
        ...prev,
        { id: nextLocalId(), role: "user", content },
        { id: assistantLocalId, role: "assistant", content: "", status: "local_streaming" },
      ]);
      await send(sessionId, content, {
        onEvent: (event) => handleEvent(assistantLocalId, event),
        onError: (message) =>
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantLocalId ? { ...m, status: "failed", error: message } : m,
            ),
          ),
      });
      // 流结束后兜底：仍处 local_streaming 态说明没收到 done/error 事件
      // （可能 SSE 流提前关闭或后端异常未发 error），标记为 failed 而非 aborted
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantLocalId && m.status === "local_streaming"
            ? { ...m, status: "failed", error: "回答未正常完成，可能未配置 DEEPSEEK_API_KEY" }
            : m,
        ),
      );
    },
    [activeId, send, handleEvent],
  );

  const onToolResolved = useCallback(
    (result: string, _approved: boolean) => {
      setToolCall(null);
      setMessages((prev) => [
        ...prev.map((m) =>
          m.status === "pending_confirm" ? { ...m, status: "complete" as const } : m,
        ),
        { id: nextLocalId(), role: "tool", content: result },
      ]);
    },
    [],
  );

  return (
    <div className="flex h-screen overflow-hidden">
      {/* 深色侧边栏 */}
      <aside className="flex w-72 shrink-0 flex-col gap-4 overflow-y-auto scrollbar-thin bg-ink p-4">
        <div className="text-lg font-semibold text-white">内知 · KnowledgeQA</div>
        <SessionList
          sessions={sessions}
          activeId={activeId}
          onSelect={setActiveId}
          onCreate={() => void createSession()}
          onDelete={(id) => void deleteSession(id)}
        />
        <div className="mt-auto space-y-4">
          <DocumentManager />
          <div className="flex items-center justify-between border-t border-white/10 pt-3">
            <div className="text-xs text-slate-400">
              {user?.display_name || user?.username}
              <div className="mt-1">
                <QuotaBadge refreshKey={quotaRefreshKey} />
              </div>
            </div>
            <button
              type="button"
              onClick={logout}
              aria-label="退出登录"
              className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white cursor-pointer"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      {/* 对话主区 */}
      <main className="flex flex-1 flex-col bg-surface">
        <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-6">
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.length === 0 && (
              <div className="mt-24 text-center text-sm text-slate-400">
                <p className="text-lg font-medium text-slate-500">开始提问</p>
                <p className="mt-2">上传文档后，回答将附引用角标，点击可回跳原文</p>
              </div>
            )}
            {messages.map((m) => (
              <MessageItem
                key={m.id}
                message={m}
                streaming={m.status === "local_streaming"}
                onCitationClick={setActiveCitation}
                onRetry={m.status === "failed" ? () => void ask(lastQuestionRef.current) : undefined}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        </div>
        <ChatInput
          streaming={streaming}
          disabled={quotaExhausted}
          onSend={(content) => void ask(content)}
          onStop={stop}
        />
      </main>

      <CitationPanel chunkId={activeCitation} onClose={() => setActiveCitation(null)} />
      <ToolConfirmDialog
        toolCall={toolCall}
        onResolved={onToolResolved}
        onClose={() => setToolCall(null)}
      />
    </div>
  );
}
