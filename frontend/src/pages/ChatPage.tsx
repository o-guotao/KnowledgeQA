import { BookOpenText, Files, History, LayoutDashboard, Loader2, Menu, MessageSquare, Quote, Settings2, ShieldCheck, X, Zap } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useLocation, useNavigate } from "react-router-dom";

import { del, get, post, withQuery } from "../api/client";
import {
  MessageSchema,
  SessionSchema,
  VersionInfoSchema,
  pageSchema,
  type ChatEvent,
  type Message,
  type Session,
} from "../api/schemas";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/button";
import { ChatInput } from "../components/ChatInput";
import { CitationPanel } from "../components/CitationPanel";
import { MessageItem, type DisplayMessage } from "../components/MessageItem";
import { SessionList } from "../components/SessionList";
import { UserMenu } from "../components/UserMenu";
import { ThemeToggle } from "../components/ThemeToggle";
import { ToolConfirmDialog } from "../components/ToolConfirmDialog";
import { useChatStream } from "../hooks/useChatStream";
import { usePaginatedQuery } from "../hooks/usePaginatedQuery";

type PendingToolCall = Extract<ChatEvent, { type: "tool_call" }>;

let localId = 0;
const nextLocalId = () => `local-${++localId}`;

/** 历史消息每页条数：与服务端 MessagePageParams 默认值一致 */
const MESSAGE_PAGE_SIZE = 50;

/** 服务端消息 → 展示模型（过滤流式残留行：后端读取时会把 streaming 清理为 aborted） */
function toDisplayMessages(rows: Message[]): DisplayMessage[] {
  return rows
    .filter((m) => m.status !== "streaming")
    .map((m) => ({
      id: m.id,
      serverId: m.id,
      role: m.role,
      content: m.content,
      status: m.status,
      citations: (m.citations ?? undefined) as DisplayMessage["citations"],
      error: m.error,
      traceId: m.trace_id,
      feedback: m.feedback ?? null,
    }));
}

export function ChatPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  // 历史消息分页：page=1 为最新一页，向前「加载更早」时累加页码并 prepend
  const [historyPage, setHistoryPage] = useState(1);
  const [hasOlder, setHasOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [activeCitation, setActiveCitation] = useState<string | null>(null);
  const [toolCall, setToolCall] = useState<PendingToolCall | null>(null);
  const [quotaRefreshKey, setQuotaRefreshKey] = useState(0);
  const [quotaExhausted, setQuotaExhausted] = useState(false);
  // 检索片段数模式：auto=按问题复杂度自适应（默认）；三档为手动指定 top_k（精确 3 / 均衡 5 / 广泛 10）
  const [topKMode, setTopKMode] = useState<"auto" | number>("auto");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // 应用版本号（单一来源：后端 /api/meta/version ↔ 根 VERSION 文件）
  const [appVersion, setAppVersion] = useState("");
  // 正在本地流式作答的会话 id：activeId 切换会触发历史加载，需据此跳过以免清掉乐观消息
  const turnSessionRef = useRef<string | null>(null);
  // 该在途会话的乐观消息当前是否正显示在列表中（中途切走再切回时已非乐观列表，须走真实历史加载）
  const turnVisibleRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { streaming, send, stop } = useChatStream();

  // 会话侧栏：服务端搜索 + 累加式分页（「加载更多」而非页码）
  const sessionsQuery = usePaginatedQuery<Session>(
    useCallback((params) => get(withQuery("/sessions", params), pageSchema(SessionSchema)), []),
    { pageSize: 30, append: true },
  );
  const sessions = sessionsQuery.items;
  const setSessions = sessionsQuery.setItems;
  const refreshSessions = sessionsQuery.refresh;

  // loadOlder 的响应落地前用于确认会话未切换
  const activeIdRef = useRef<string | null>(null);
  activeIdRef.current = activeId;

  useEffect(() => {
    get("/meta/version", VersionInfoSchema)
      .then((r) => setAppVersion(r.version))
      .catch(() => setAppVersion(""));
  }, []);

  // 选中会话时加载最新一页历史消息（page=1）
  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      setHistoryPage(1);
      setHasOlder(false);
      return;
    }
    // 刚新建会话并首次提问：assistant 尚未落库（服务端先以 streaming 态写入），
    // 此时用服务端历史覆盖乐观列表会把占位条清掉/过滤掉，导致首轮回答不显示。
    // 仅当该会话的乐观列表正显示在屏上时以它为准跳过；中途切走再切回则走真实历史。
    if (turnSessionRef.current === activeId && turnVisibleRef.current) return;
    turnVisibleRef.current = false; // 将用服务端历史替换当前列表
    let cancelled = false;
    get(
      withQuery(`/sessions/${activeId}/messages`, { page: 1, page_size: MESSAGE_PAGE_SIZE }),
      pageSchema(MessageSchema),
    )
      .then((page) => {
        if (cancelled) return;
        // 服务端按 created_at 倒序返回（page=1 为最新一页）：需反转成正序再展示
        setMessages(toDisplayMessages(page.items).reverse());
        setHistoryPage(1);
        setHasOlder(page.pages > 1);
      })
      .catch((err) => {
        if (!cancelled) console.error("messages fetch failed", err);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  /** 加载更早的历史消息：取下一页（更早），反转后 prepend —— 只动头部，不碰流式追加的尾部。 */
  const loadOlder = useCallback(async () => {
    const sessionId = activeId;
    if (!sessionId || loadingOlder || !hasOlder) return;
    setLoadingOlder(true);
    try {
      const next = historyPage + 1;
      const page = await get(
        withQuery(`/sessions/${sessionId}/messages`, { page: next, page_size: MESSAGE_PAGE_SIZE }),
        pageSchema(MessageSchema),
      );
      // 响应期间用户可能已切换会话：丢弃过期结果
      if (activeIdRef.current !== sessionId) return;
      setMessages((prev) => [...toDisplayMessages(page.items).reverse(), ...prev]);
      setHistoryPage(next);
      setHasOlder(next < page.pages);
    } catch (err) {
      console.error("older messages fetch failed", err);
    } finally {
      setLoadingOlder(false);
    }
  }, [activeId, historyPage, hasOlder, loadingOlder]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 答案反馈：调后端并更新本地消息的 feedback 态（再点同值=取消）
  const handleFeedback = useCallback(
    async (messageId: string, feedback: "up" | "down" | null) => {
      try {
        await post(`/messages/${messageId}/feedback`, { feedback }, z.object({
          message_id: z.string(),
          feedback: z.enum(["up", "down"]).nullable(),
        }));
        setMessages((prev) =>
          prev.map((m) => (m.serverId === messageId ? { ...m, feedback } : m)),
        );
      } catch (err) {
        console.error("feedback failed", err);
      }
    },
    [],
  );

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
        sessionId = session.id;
      }
      // 先登记在途会话，再切 activeId/追加乐观消息：历史加载 effect 据此跳过，不覆盖本轮
      turnSessionRef.current = sessionId;
      if (!activeId) setActiveId(sessionId);
      const assistantLocalId = nextLocalId();
      setMessages((prev) => [
        ...prev,
        { id: nextLocalId(), role: "user", content },
        { id: assistantLocalId, role: "assistant", content: "", status: "local_streaming" },
      ]);
      turnVisibleRef.current = true;
      try {
        await send(sessionId, content, {
          onEvent: (event) => handleEvent(assistantLocalId, event),
          onError: (message) =>
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantLocalId ? { ...m, status: "failed", error: message } : m,
              ),
            ),
        }, topKMode === "auto" ? undefined : topKMode);
      } finally {
        if (turnSessionRef.current === sessionId) turnSessionRef.current = null;
      }
      // abort 路径：仍处本地流式态则标记已停止
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantLocalId && m.status === "local_streaming"
            ? { ...m, status: "aborted" }
            : m,
        ),
      );
    },
    [activeId, send, handleEvent, topKMode],
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
    <div className="flex min-h-0 flex-1 overflow-hidden bg-theme-deep">
      {sidebarOpen && <button type="button" aria-label="关闭导航" onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-20 bg-slate-950/40 lg:hidden" />}
      <aside className={`fixed inset-y-0 left-0 z-30 flex w-80 -translate-x-full flex-col gap-5 overflow-y-auto border-r border-white/5 bg-gradient-to-b from-theme-deep via-theme-deep to-theme-bg p-4 shadow-2xl transition-transform lg:static lg:w-72 lg:translate-x-0 lg:shadow-none ${sidebarOpen ? "translate-x-0" : ""}`}>
        <div className="flex items-center justify-between px-1 text-theme-text"><div className="flex items-center gap-2 text-lg font-semibold"><BookOpenText size={21} className="text-brand-light" />内知</div><button type="button" className="rounded-md p-1 text-slate-400 hover:bg-white/10 lg:hidden" aria-label="关闭导航" onClick={() => setSidebarOpen(false)}><X size={18} /></button></div>
        <p className="-mt-3 px-1 text-xs text-slate-500">
          KnowledgeQA · 内部知识助手{appVersion && (
            <button
              type="button"
              onClick={() => navigate("/changelog")}
              className="ml-2 cursor-pointer rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] text-brand-light hover:bg-white/15"
              title="查看更新日志"
            >
              v{appVersion}
            </button>
          )}
        </p>
        <nav className="flex flex-col gap-1 border-b border-white/10 pb-3" aria-label="主导航">
          {[
            { label: "对话", to: "/", icon: MessageSquare },
            { label: "文档库", to: "/documents", icon: Files },
            { label: "模型设置", to: "/settings/models", icon: Settings2 },
            ...(user?.role === "admin" ? [{ label: "管理后台", to: "/admin", icon: LayoutDashboard }] : []),
            { label: "更新日志", to: "/changelog", icon: History },
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
                className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm cursor-pointer transition-colors ${active ? "bg-white/10 font-medium text-theme-text" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}
              >
                <Icon size={16} className="shrink-0" />
                {label}
              </button>
            );
          })}
        </nav>
        <div className="border-b border-white/5 pb-3">
          <p className="px-1 text-xs font-medium text-slate-400">知识库设置</p>
          <div className="mt-2.5 px-1">
            <p className="text-xs text-slate-500">检索范围</p>
            <div className="mt-1.5 grid grid-cols-4 gap-1" role="radiogroup" aria-label="检索范围">
              {([
                { value: "auto" as const, label: "自动", desc: "按问题复杂度自适应" },
                { value: 3, label: "精确", desc: "3 块，单点事实" },
                { value: 5, label: "均衡", desc: "5 块，常规问题" },
                { value: 10, label: "广泛", desc: "10 块，列举/对比" },
              ]).map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  role="radio"
                  aria-checked={topKMode === opt.value}
                  title={opt.desc}
                  onClick={() => setTopKMode(opt.value)}
                  className={`cursor-pointer rounded-md border px-1.5 py-1.5 text-xs transition-colors ${
                    topKMode === opt.value
                      ? "border-brand/40 bg-brand/15 font-medium text-brand-light"
                      : "border-theme-line bg-theme-input text-theme-sub hover:border-brand/30 hover:text-theme-text"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <SessionList
          sessions={sessions}
          activeId={activeId}
          onSelect={setActiveId}
          onCreate={() => void createSession()}
          onDelete={(id) => void deleteSession(id)}
          query={sessionsQuery.query}
          onQueryChange={sessionsQuery.setQuery}
          hasMore={sessionsQuery.page < sessionsQuery.pages}
          loadingMore={sessionsQuery.loading}
          onLoadMore={() => sessionsQuery.setPage(sessionsQuery.page + 1)}
          error={sessionsQuery.error}
        />
      </aside>

      {/* 对话主区 */}
      <main className="flex min-w-0 flex-1 flex-col bg-gradient-to-b from-theme-bg via-theme-bg to-theme-deep">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-theme-line bg-theme-bg/70 px-4 backdrop-blur-xl sm:px-6">
          <div className="flex items-center gap-3"><button type="button" aria-label="打开导航" onClick={() => setSidebarOpen(true)} className="rounded-lg p-2 text-slate-300 hover:bg-white/10 lg:hidden"><Menu size={20} /></button><div><p className="text-sm font-semibold tracking-tight text-theme-text">知识问答</p><p className="hidden text-xs text-slate-500 sm:block">基于已入库文档生成带引用的回答</p></div></div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <span className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />服务就绪</span>
            <UserMenu user={user} onLogout={logout} quotaRefreshKey={quotaRefreshKey} />
          </div>
        </header>
        <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 sm:px-6">
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.length === 0 && (
              <div className="mt-16 flex flex-col items-center px-6 sm:mt-24">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand to-brand-dark text-white shadow-pop">
                  <BookOpenText size={26} />
                </div>
                <p className="mt-6 text-2xl font-semibold tracking-tight text-theme-text">从知识库中找到可靠答案</p>
                <p className="mx-auto mt-3 max-w-md text-center text-sm leading-6 text-theme-sub">上传制度、手册或 FAQ 后直接提问。每条回答都会标出可回溯的原文引用。</p>
                <div className="mt-10 grid w-full max-w-2xl gap-3 sm:grid-cols-3">
                  {[
                    { icon: Quote, title: "引用可溯", desc: "答案点回原文出处" },
                    { icon: Zap, title: "流式输出", desc: "逐字生成、可随时停止" },
                    { icon: ShieldCheck, title: "安全留痕", desc: "用量配额、操作可审计" },
                  ].map((f) => (
                    <div key={f.title} className="rounded-xl border border-theme-line bg-theme-card p-4 text-left shadow-soft">
                      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/15 text-brand-light">
                        <f.icon size={15} />
                      </span>
                      <p className="mt-3 text-sm font-medium text-theme-text">{f.title}</p>
                      <p className="mt-1 text-xs leading-5 text-theme-sub">{f.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {hasOlder && (
              <div className="flex justify-center">
                {/* 流式作答中禁用：避免历史分页与乐观流式消息交叉 */}
                <Button variant="outline" size="sm" disabled={loadingOlder || streaming} onClick={() => void loadOlder()}>
                  {loadingOlder ? <Loader2 size={14} className="animate-spin" /> : <History size={14} />}
                  {loadingOlder ? "加载中…" : "加载更早的消息"}
                </Button>
              </div>
            )}
            {messages.map((m, idx) => (
              <MessageItem
                key={m.id}
                message={m}
                streaming={m.status === "local_streaming"}
                onCitationClick={setActiveCitation}
                onRetry={
                  m.status === "failed"
                    ? () => {
                        // 用该失败回复之前最近的用户提问重试：lastQuestionRef 在页面刷新后丢失，
                        // 会以空 content 触发 422；且多轮失败时无法对应各自提问。
                        const question = messages
                          .slice(0, idx)
                          .reverse()
                          .find((x) => x.role === "user")?.content;
                        if (question) void ask(question);
                      }
                    : undefined
                }
                onFeedback={handleFeedback}
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
