import { BookOpenText, Files, LogOut, Menu, MessageSquare, Settings2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useLocation, useNavigate } from "react-router-dom";

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
  const navigate = useNavigate();
  const location = useLocation();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [toolCall, setToolCall] = useState<PendingToolCall | null>(null);
  const [quotaRefreshKey, setQuotaRefreshKey] = useState(0);
  const [quotaExhausted, setQuotaExhausted] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
      // abort 路径：仍处本地流式态则标记已停止
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantLocalId && m.status === "local_streaming"
            ? { ...m, status: "aborted" }
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
    <div className="flex h-dvh overflow-hidden bg-slate-50">
      {sidebarOpen && <button type="button" aria-label="关闭导航" onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-20 bg-slate-950/40 lg:hidden" />}
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-80 -translate-x-full flex-col gap-5 overflow-y-auto border-r border-white/10 bg-ink p-4 shadow-2xl transition-transform lg:static lg:w-72 lg:translate-x-0 lg:shadow-none ${sidebarOpen ? "translate-x-0" : ""}`}>
        <div className="flex items-center justify-between px-1 text-white"><div className="flex items-center gap-2 text-lg font-semibold"><BookOpenText size={21} className="text-brand-light" />内知</div><button type="button" className="rounded-md p-1 text-slate-400 hover:bg-white/10 lg:hidden" aria-label="关闭导航" onClick={() => setSidebarOpen(false)}><X size={18} /></button></div>
        <p className="-mt-3 px-1 text-xs text-slate-500">KnowledgeQA · 内部知识助手</p>
        <nav className="flex flex-col gap-1 border-b border-white/10 pb-3" aria-label="主导航">
          {[
            { label: "对话", to: "/", icon: MessageSquare },
            { label: "文档库", to: "/documents", icon: Files },
            { label: "模型设置", to: "/settings/models", icon: Settings2 },
          ].map(({ label, to, icon: Icon }) => {
            const active = location.pathname === to;
            return (
              <button
                key={to}
                type="button"
                onClick={() => {
                  setSidebarOpen(false);
                  navigate(to);
                }}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm cursor-pointer transition-colors ${active ? "bg-white/10 font-medium text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}
              >
                <Icon size={16} className="shrink-0" />
                {label}
              </button>
            );
          })}
        </nav>
        <SessionList
          sessions={sessions}
          activeId={activeId}
          onSelect={setActiveId}
          onCreate={() => void createSession()}
          onDelete={(id) => void deleteSession(id)}
        />
        <div className="mt-auto flex items-center justify-between border-t border-white/10 px-1 pt-3">
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
      </aside>

      {/* 对话主区 */}
      <main className="flex min-w-0 flex-1 flex-col bg-slate-50">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/80 px-4 backdrop-blur-xl sm:px-6">
          <div className="flex items-center gap-3"><button type="button" aria-label="打开导航" onClick={() => setSidebarOpen(true)} className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden"><Menu size={20} /></button><div><p className="text-sm font-semibold text-ink">知识问答</p><p className="hidden text-xs text-slate-400 sm:block">基于已入库文档生成带引用的回答</p></div></div>
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">服务就绪</span>
        </header>
        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.length === 0 && (
              <div className="mt-16 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-400 shadow-sm sm:mt-24">
                <p className="text-xl font-semibold text-ink">从知识库中找到可靠答案</p>
                <p className="mx-auto mt-2 max-w-md leading-6">上传制度、手册或 FAQ 后直接提问。每条回答都会标出可回溯的原文引用。</p>
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
