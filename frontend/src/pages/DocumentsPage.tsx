import { ArrowLeft, FileUp, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { del, get, postForm } from "../api/client";
import { DocumentSchema, type KnowledgeDocument } from "../api/schemas";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";

const STATUS_META: Record<KnowledgeDocument["status"], { label: string; variant: "muted" | "warning" | "success" | "destructive" }> = {
  uploaded: { label: "排队中", variant: "muted" },
  processing: { label: "切分中", variant: "warning" },
  ready: { label: "已入库", variant: "success" },
  failed: { label: "失败", variant: "destructive" },
};
const PENDING_STATUSES: KnowledgeDocument["status"][] = ["uploaded", "processing"];

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

/** 上传文档 + 切分状态管理（独立菜单页）。仅当存在排队/切分中的文档时才轮询。 */
export function DocumentsPage() {
  const navigate = useNavigate();
  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    get("/documents", z.array(DocumentSchema))
      .then(setDocs)
      .catch((err) => console.error("documents fetch failed", err));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const pendingCount = docs.filter((d) => PENDING_STATUSES.includes(d.status)).length;

  // 有待处理文档才轮询，全部终态后停止，避免无谓请求
  useEffect(() => {
    if (pendingCount === 0) return;
    const timer = setInterval(refresh, 5_000);
    return () => clearInterval(timer);
  }, [pendingCount, refresh]);

  const upload = async (file: File) => {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const created = await postForm("/documents", form, DocumentSchema);
      setDocs((prev) => [created, ...prev]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const removeDocument = async (doc: KnowledgeDocument) => {
    const confirmed = window.confirm(
      `删除「${doc.filename}」？原始文件与已入库切块（引用数据）将一并删除，无法恢复。`,
    );
    if (!confirmed) return;
    setDeletingId(doc.id);
    try {
      await del(`/documents/${doc.id}`);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
    } catch (err) {
      alert(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeletingId(null);
    }
  };

  const readyCount = docs.filter((d) => d.status === "ready").length;
  const failedCount = docs.filter((d) => d.status === "failed").length;

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" aria-label="返回问答" onClick={() => navigate("/")}>
              <ArrowLeft size={18} />
            </Button>
            <div>
              <p className="text-sm font-medium text-brand">知识库</p>
              <h1 className="text-2xl font-semibold text-ink">文档管理</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              aria-label="刷新"
              onClick={() => refresh()}
              className="cursor-pointer"
            >
              <RefreshCw size={14} />
              刷新
            </Button>
            <Button
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="cursor-pointer"
            >
              {uploading ? <Loader2 size={15} className="animate-spin" /> : <FileUp size={15} />}
              {uploading ? "上传中…" : "上传文档"}
            </Button>
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
        </header>

        <p className="max-w-3xl text-sm leading-6 text-muted">
          上传制度、手册或 FAQ（.txt/.md/.pdf，单个 ≤ 20MB），系统自动切分并入库，之后即可在问答中检索并带引用回答。
          {pendingCount > 0 && " 有文档正在处理，将自动刷新直到完成。"}
        </p>

        <div className="flex flex-wrap gap-2 text-sm">
          <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">全部 {docs.length}</span>
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-700">已入库 {readyCount}</span>
          {pendingCount > 0 && (
            <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-700">处理中 {pendingCount}</span>
          )}
          {failedCount > 0 && (
            <span className="rounded-full bg-red-50 px-3 py-1 text-red-700">失败 {failedCount}</span>
          )}
        </div>

        <section className="space-y-3">
          {docs.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
                <p className="text-sm text-muted">还没有上传过文档</p>
                <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()} className="cursor-pointer">
                  <FileUp size={14} />
                  上传第一份文档
                </Button>
              </CardContent>
            </Card>
          ) : (
            docs.map((d) => {
              const meta = STATUS_META[d.status];
              return (
                <Card key={d.id}>
                  <CardContent className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="truncate font-medium text-ink">{d.filename}</p>
                        <Badge variant={meta.variant}>{meta.label}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-slate-400">
                        {fmtTime(d.created_at)}
                        {d.status === "ready" && ` · ${d.chunk_count} 个切块`}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3 text-right">
                      <div className="text-xs">
                        {d.status === "failed" && d.error ? (
                          <p className="max-w-56 text-red-600" title={d.error}>{d.error}</p>
                        ) : (
                          <p className="text-slate-400">{d.status === "ready" ? "可用于问答" : "处理中…"}</p>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`删除 ${d.filename}`}
                        disabled={deletingId === d.id}
                        onClick={() => void removeDocument(d)}
                        className="shrink-0 cursor-pointer text-slate-400 hover:bg-red-50 hover:text-red-600"
                      >
                        {deletingId === d.id ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </section>
      </div>
    </main>
  );
}
