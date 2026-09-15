import { Loader2, MessageSquare, Plus, Trash2 } from "lucide-react";

import type { Session } from "../api/schemas";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { SearchInput } from "./ui/search-input";

interface SessionListProps {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
  /** 搜索关键词（服务端按标题匹配，防抖在 usePaginatedQuery 内） */
  query: string;
  onQueryChange: (value: string) => void;
  /** 还有更早的会话可分页加载 */
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  /** 加载失败提示（否则侧栏只剩空白，无从排查） */
  error?: string | null;
}

export function SessionList({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  query,
  onQueryChange,
  hasMore,
  loadingMore,
  onLoadMore,
  error,
}: SessionListProps) {
  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={onCreate}
        className="mb-2 flex items-center gap-2 rounded-lg border border-dashed border-slate-600 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-brand-light hover:text-white cursor-pointer"
      >
        <Plus size={16} />
        新建会话
      </button>
      <SearchInput
        value={query}
        onChange={onQueryChange}
        placeholder="搜索会话"
        ariaLabel="搜索会话"
        className="mb-1"
      />
      {sessions.map((s) => (
        <div
          key={s.id}
          className={cn(
            "group flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors cursor-pointer",
            s.id === activeId
              ? "bg-brand/20 text-white"
              : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
          )}
          onClick={() => onSelect(s.id)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && onSelect(s.id)}
        >
          <MessageSquare size={14} className="shrink-0 opacity-60" />
          <span className="flex-1 truncate">{s.title}</span>
          <button
            type="button"
            aria-label="删除会话"
            className="hidden rounded p-0.5 text-slate-500 hover:text-red-400 group-hover:block cursor-pointer"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(s.id);
            }}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      {error && <p className="px-3 py-2 text-xs text-red-400">会话加载失败：{error}</p>}
      {sessions.length === 0 && !error && (
        <p className="px-3 py-2 text-xs text-slate-500">
          {query !== "" ? "没有匹配的会话" : "暂无会话，点击上方新建"}
        </p>
      )}
      {hasMore && (
        <Button
          variant="ghost"
          size="sm"
          disabled={loadingMore}
          onClick={onLoadMore}
          className="mt-1 text-slate-400"
        >
          {loadingMore && <Loader2 size={14} className="animate-spin" />}
          {loadingMore ? "加载中…" : "加载更多"}
        </Button>
      )}
    </div>
  );
}
