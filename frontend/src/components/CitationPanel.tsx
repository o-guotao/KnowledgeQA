import { FileText, X } from "lucide-react";
import { useEffect, useState } from "react";

import { get } from "../api/client";
import { ChunkSchema, type Chunk } from "../api/schemas";
import { Badge } from "./ui/badge";

interface CitationPanelProps {
  chunkId: string | null;
  onClose: () => void;
}

/** 引用面板：点击角标右侧滑出，展示原文块并高亮（点回原文） */
export function CitationPanel({ chunkId, onClose }: CitationPanelProps) {
  const [chunk, setChunk] = useState<Chunk | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!chunkId) {
      setChunk(null);
      return;
    }
    setError(null);
    get(`/chunks/${chunkId}`, ChunkSchema)
      .then(setChunk)
      .catch((err) => {
        console.error("chunk fetch failed", err);
        setError("引用内容加载失败");
      });
  }, [chunkId]);

  if (!chunkId) return null;

  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md shrink-0 flex-col border-l border-slate-200 bg-white/95 shadow-2xl backdrop-blur-xl animate-fade-up lg:static lg:w-80 lg:bg-white/80 lg:shadow-none">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <FileText size={16} className="text-brand" />
          引用原文
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭引用面板"
          className="rounded-md p-1 text-slate-500 hover:bg-slate-100 cursor-pointer"
        >
          <X size={16} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!error && !chunk && <p className="text-sm text-slate-400">加载中…</p>}
        {chunk && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge>{chunk.document_name}</Badge>
              <span className="text-xs text-slate-400">
                第 {chunk.chunk_index + 1}/{chunk.total_chunks} 块
              </span>
            </div>
            <blockquote className="rounded-lg border-l-4 border-brand bg-brand/5 p-3 text-sm leading-relaxed text-slate-700">
              <mark className="bg-yellow-200/70 rounded-sm px-0.5">{chunk.content}</mark>
            </blockquote>
            <p className="text-xs text-slate-400">
              原文偏移 {chunk.start_offset}–{chunk.end_offset}
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
