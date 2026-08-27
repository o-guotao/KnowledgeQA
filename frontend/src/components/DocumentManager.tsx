import { FileUp, Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { z } from "zod";

import { get, postForm } from "../api/client";
import { DocumentSchema, type KnowledgeDocument } from "../api/schemas";
import { Badge } from "./ui/badge";

const STATUS_META: Record<KnowledgeDocument["status"], { label: string; variant: "muted" | "warning" | "success" | "destructive" }> = {
  uploaded: { label: "排队中", variant: "muted" },
  processing: { label: "切分中", variant: "warning" },
  ready: { label: "已入库", variant: "success" },
  failed: { label: "失败", variant: "destructive" },
};

/** 文档管理：上传（txt/md/pdf）+ 切分状态轮询 */
export function DocumentManager() {
  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    return get("/documents", z.array(DocumentSchema))
      .then(setDocs)
      .catch((err) => console.error("documents fetch failed", err));
  }, []);

  // 首次加载
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // 有未就绪文档时才轮询；全部 ready 后停止（减少无效请求）
  const hasPending = docs.some((d) => d.status === "uploaded" || d.status === "processing");
  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => void refresh(), 3_000);
    return () => clearInterval(timer);
  }, [hasPending, refresh]);

  const upload = async (file: File) => {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      await postForm("/documents", form, DocumentSchema);
      refresh();
    } catch (err) {
      console.error("upload failed", err);
      alert(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">知识库文档</span>
        <button
          type="button"
          disabled={uploading}
          onClick={() => fileRef.current?.click()}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-brand-light hover:bg-white/5 disabled:opacity-50 cursor-pointer"
        >
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />}
          上传
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.md,.markdown,.pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
          }}
        />
      </div>
      <div className="max-h-44 space-y-1 overflow-y-auto scrollbar-thin">
        {docs.map((d) => {
          const meta = STATUS_META[d.status];
          return (
            <div
              key={d.id}
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-slate-300"
              title={d.error ?? d.filename}
            >
              <span className="flex-1 truncate">{d.filename}</span>
              <Badge variant={meta.variant}>
                {meta.label}
                {d.status === "ready" && ` ${d.chunk_count}块`}
              </Badge>
            </div>
          );
        })}
        {docs.length === 0 && (
          <p className="px-2 text-xs text-slate-500">上传文档后即可基于内容提问</p>
        )}
      </div>
    </div>
  );
}
