import { ArrowLeft, Eye, FileUp, Layers, Loader2, Quote, RefreshCw, Share2, Trash2, Users, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { del, get, patch, post, postForm } from "../api/client";
import { ContentUpdateResultSchema, DocumentSchema, type KnowledgeDocument } from "../api/schemas";
import { useAuth } from "../auth/AuthContext";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DocumentPreviewModal } from "../components/DocumentPreviewModal";
import { ThemeToggle } from "../components/ThemeToggle";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";

const STATUS_META: Record<KnowledgeDocument["status"], { label: string; variant: "muted" | "warning" | "success" | "destructive" }> = {
  uploaded: { label: "排队中", variant: "muted" },
  processing: { label: "切分中", variant: "warning" },
  ready: { label: "已入库", variant: "success" },
  failed: { label: "失败", variant: "destructive" },
  no_text: { label: "不可检索", variant: "muted" },
};
const PENDING_STATUSES: KnowledgeDocument["status"][] = ["uploaded", "processing"];

// 与后端校验保持一致：扩展名白名单、20MB、文件名规则（见 backend/app/api/documents.py）
const ALLOWED_EXTS = [".txt", ".md", ".markdown", ".pdf"];
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const FORBIDDEN_FILENAME_CHARS = /[<>:"/\\|?*]/;
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

type PendingStatus = "pending" | "uploading" | "error";

interface PendingFile {
  id: string;
  file: File;
  status: PendingStatus;
  message?: string;
}

function fileExt(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

/** 文件名规则：与后端 `_normalize_filename` 对齐；返回错误文案，合法返回 null。 */
function filenameError(name: string): string | null {
  if (!name) return "文件名为空";
  if (CONTROL_CHARS.test(name)) return "文件名包含非法控制字符";
  if (FORBIDDEN_FILENAME_CHARS.test(name)) return '文件名包含非法字符：<>:"/\\|?*';
  const n = name.trim().length;
  if (n < 1) return "文件名为空";
  if (n > 255) return "文件名过长（≤255 字符）";
  return null;
}

/** 计算文件 SHA-256 用于前端预检判重。
 * crypto.subtle 仅在安全上下文（HTTPS / localhost）可用；纯 IP HTTP 访问时为 undefined，
 * 此时返回 null 跳过前端判重，由后端权威 content_hash 判重兜底（重复时后端返回 409）。 */
async function sha256Hex(buf: ArrayBuffer): Promise<string | null> {
  if (typeof crypto === "undefined" || !crypto.subtle) return null;
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

let uid = 0;
const nextId = () => `pf-${Date.now()}-${uid++}`;

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

/** 上传文档 + 切分状态管理（独立菜单页）。仅当存在排队/切分中的文档时才轮询。 */
export function DocumentsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [tab, setTab] = useState<"mine" | "team">("mine");
  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [teamDocs, setTeamDocs] = useState<KnowledgeDocument[]>([]);
  const [shareTogglingId, setShareTogglingId] = useState<string | null>(null);
  const [shareTeam, setShareTeam] = useState(false);
  const [queue, setQueue] = useState<PendingFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState<KnowledgeDocument | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // 本批上传的归属（文件夹/标签）与列表过滤
  const [uploadFolder, setUploadFolder] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [filterFolder, setFilterFolder] = useState<string | null>(null);

  const refresh = useCallback(() => {
    get<KnowledgeDocument[]>("/documents", z.array(DocumentSchema))
      .then(setDocs)
      .catch((err) => console.error("documents fetch failed", err));
  }, []);

  const refreshTeam = useCallback(() => {
    get<KnowledgeDocument[]>("/documents/team", z.array(DocumentSchema))
      .then(setTeamDocs)
      .catch((err) => console.error("team documents fetch failed", err));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // 切到团队空间 Tab 时拉取共享文档
  useEffect(() => {
    if (tab === "team") refreshTeam();
  }, [tab, refreshTeam]);

  /** 共享/取消共享到团队空间（owner 或 admin） */
  const toggleShare = async (doc: KnowledgeDocument) => {
    setShareTogglingId(doc.id);
    try {
      const next = doc.visibility === "team" ? "private" : "team";
      await patch(`/documents/${doc.id}`, { visibility: next }, DocumentSchema);
      refresh();
      if (tab === "team") refreshTeam();
    } catch (err) {
      alert(err instanceof Error ? err.message : "操作失败");
    } finally {
      setShareTogglingId(null);
    }
  };

  const pendingCount = docs.filter((d) => PENDING_STATUSES.includes(d.status)).length;

  // 有待处理文档才轮询，全部终态后停止，避免无谓请求
  useEffect(() => {
    if (pendingCount === 0) return;
    const timer = setInterval(refresh, 5_000);
    return () => clearInterval(timer);
  }, [pendingCount, refresh]);

  /** 选择文件后：逐文件本地预检（类型/大小/文件名/内容哈希判重），生成待上传队列。 */
  const onSelectFiles = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const files = Array.from(list);
    const items: PendingFile[] = [];
    const selectionHashes = new Map<string, string>(); // hash -> filename（批内判重）
    const existingByHash = new Map<string, string>();
    for (const d of docs) {
      if (d.content_hash) existingByHash.set(d.content_hash, d.filename);
    }

    for (const file of files) {
      const problems: string[] = [];
      const ext = fileExt(file.name);
      if (!ALLOWED_EXTS.includes(ext)) problems.push("仅支持 .txt/.md/.markdown/.pdf");
      if (file.size === 0) problems.push("文件内容为空");
      if (file.size > MAX_UPLOAD_BYTES) problems.push("超过 20MB 上限");
      const nameErr = filenameError(file.name);
      if (nameErr) problems.push(nameErr);

      let hash: string | null = null;
      if (problems.length === 0) {
        hash = await sha256Hex(await file.arrayBuffer());
        if (hash) {
          const dupName = existingByHash.get(hash) ?? selectionHashes.get(hash);
          if (dupName) problems.push(`内容已存在：${dupName}`);
          else selectionHashes.set(hash, file.name);
        }
      }

      items.push(
        problems.length > 0
          ? { id: nextId(), file, status: "error", message: problems.join("；") }
          : { id: nextId(), file, status: "pending" },
      );
    }

    if (items.length > 0) {
      setQueue((prev) => [...prev, ...items]);
      // 未通过预检的项仍留在队列里展示原因；通过项等用户点「上传」
    }
  };

  /** 对队列中 pending 项逐文件串行上传；成功即入列表并从队列移除，失败保留原因。 */
  const uploadPending = async () => {
    const toUpload = queue.filter((q) => q.status === "pending");
    if (toUpload.length === 0 || uploading) return;
    setUploading(true);
    for (const item of toUpload) {
      setQueue((prev) => prev.map((x) => (x.id === item.id ? { ...x, status: "uploading" } : x)));
      try {
        const form = new FormData();
        form.append("file", item.file);
        if (uploadFolder.trim()) form.append("folder", uploadFolder.trim());
        if (uploadTags.trim()) form.append("tags", uploadTags.trim());
        if (shareTeam) form.append("visibility", "team");
        const created = await postForm<KnowledgeDocument>("/documents", form, DocumentSchema);
        setDocs((prev) => [created, ...prev]);
        setQueue((prev) => prev.filter((x) => x.id !== item.id));
      } catch (err) {
        const msg = err instanceof Error ? err.message : "上传失败";
        setQueue((prev) => prev.map((x) => (x.id === item.id ? { ...x, status: "error", message: msg } : x)));
      }
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const clearQueue = () => setQueue([]);
  const removeQueueItem = (id: string) => setQueue((prev) => prev.filter((x) => x.id !== id));
  const pendingToUpload = queue.filter((q) => q.status === "pending").length;

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [singleConfirm, setSingleConfirm] = useState<KnowledgeDocument | null>(null);
  const [bulkConfirm, setBulkConfirm] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  // 增量更新与失效检测：一键重切 + 就地更新内容
  const [reingestingId, setReingestingId] = useState<string | null>(null);
  const [updateTarget, setUpdateTarget] = useState<KnowledgeDocument | null>(null);
  const [updatingContent, setUpdatingContent] = useState(false);
  const updateFileRef = useRef<HTMLInputElement>(null);

  /** 一键刷新：按当前配置对已存储内容重新切分（stale / failed 文档）。 */
  const reingest = async (doc: KnowledgeDocument) => {
    setReingestingId(doc.id);
    try {
      await post(`/documents/${doc.id}/reingest`, {}, DocumentSchema);
      refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "重新切分失败");
    } finally {
      setReingestingId(null);
    }
  };

  /** 就地更新：选择新文件 → hash 比对 → 替换内容并重切（version+1）。 */
  const onSelectUpdateFile = async (list: FileList | null) => {
    const file = list?.[0];
    const target = updateTarget;
    if (!file || !target) return;
    setUpdatingContent(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await postForm(
        `/documents/${target.id}/content`,
        form,
        ContentUpdateResultSchema,
      );
      if (!result.updated) alert("内容与当前版本相同，无需更新");
      refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "更新内容失败");
    } finally {
      setUpdatingContent(false);
      setUpdateTarget(null);
    }
  };

  const toggleSelect = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const removeOne = async (doc: KnowledgeDocument) => {
    setDeletingId(doc.id);
    try {
      await del(`/documents/${doc.id}`);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
      setTeamDocs((prev) => prev.filter((d) => d.id !== doc.id));
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(doc.id);
        return next;
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeletingId(null);
      setSingleConfirm(null);
    }
  };

  const removeBulk = async () => {
    setBulkDeleting(true);
    for (const id of Array.from(selected)) {
      try {
        await del(`/documents/${id}`);
      } catch (e) {
        console.error("bulk delete failed", id, e);
      }
    }
    setDocs((prev) => prev.filter((d) => !selected.has(d.id)));
    setSelected(new Set());
    setBulkDeleting(false);
    setBulkConfirm(false);
  };

  const readyCount = docs.filter((d) => d.status === "ready").length;
  const failedCount = docs.filter((d) => d.status === "failed").length;
  const noTextCount = docs.filter((d) => d.status === "no_text").length;
  const busy = uploading;

  // 文件夹过滤：全部非空 folder 去重排序；filterFolder 为 null 表示不过滤
  const folders = Array.from(new Set(docs.map((d) => d.folder).filter((f) => f))).sort();
  const filteredDocs = filterFolder === null ? docs : docs.filter((d) => d.folder === filterFolder);
  const allSelected = filteredDocs.length > 0 && filteredDocs.every((d) => selected.has(d.id));
  const toggleSelectAll = () =>
    setSelected(allSelected ? new Set() : new Set(filteredDocs.map((d) => d.id)));

  return (
    <main className="min-h-screen bg-gradient-to-b from-theme-bg via-theme-bg to-theme-deep px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" aria-label="返回问答" onClick={() => navigate("/")}>
              <ArrowLeft size={18} />
            </Button>
            <div>
              <p className="text-sm font-medium text-brand">知识库</p>
              <h1 className="text-2xl font-semibold tracking-tight text-theme-text">文档管理</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
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
              disabled={busy}
              onClick={() => fileRef.current?.click()}
              className="cursor-pointer"
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <FileUp size={15} />}
              {busy ? "上传中…" : "上传文档"}
            </Button>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".txt,.md,.markdown,.pdf"
              className="hidden"
              onChange={(e) => {
                void onSelectFiles(e.target.files);
                e.target.value = "";
              }}
            />
            {/* 就地更新内容用：单选文件，目标文档由 updateTarget 暂存 */}
            <input
              ref={updateFileRef}
              type="file"
              accept=".txt,.md,.markdown,.pdf"
              className="hidden"
              onChange={(e) => {
                void onSelectUpdateFile(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
        </header>

        {/* 空间切换：我的文档 | 团队空间 */}
        <div className="flex gap-1 border-b border-theme-line">
          {([["mine", "我的文档"], ["team", "团队空间"]] as const).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`-mb-px cursor-pointer border-b-2 px-4 py-2 text-sm transition-colors ${
                tab === key
                  ? "border-brand font-medium text-brand"
                  : "border-transparent text-theme-sub hover:text-theme-text"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "mine" && (
        <p className="max-w-3xl text-sm leading-6 text-theme-sub">
          上传制度、手册或 FAQ（.txt/.md/.pdf，单个 ≤ 20MB，可一次多选）。系统对重复内容/纯图片 PDF 做校验并明确提示；
          合规文档自动切分入库，之后即可在问答中检索并带引用回答。
          {pendingCount > 0 && " 有文档正在处理，将自动刷新直到完成。"}
        </p>
        )}

        {tab === "team" && (
        <p className="max-w-3xl text-sm leading-6 text-theme-sub">
          团队成员共享的文档，全员可检索与预览；管理（取消共享/删除）由文档所有者或管理员操作。
        </p>
        )}

        {/* 本批上传归属：文件夹与标签（可选） */}
        {tab === "mine" && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-theme-line bg-theme-card px-4 py-3 text-sm">
          <label className="flex items-center gap-2 text-theme-sub">
            文件夹
            <input
              value={uploadFolder}
              onChange={(e) => setUploadFolder(e.target.value)}
              placeholder="如：制度/人事"
              className="w-40 rounded-md border border-theme-line bg-theme-input px-2 py-1 text-sm text-theme-text placeholder:text-theme-sub focus:border-brand focus:outline-none"
            />
          </label>
          <label className="flex items-center gap-2 text-theme-sub">
            标签
            <input
              value={uploadTags}
              onChange={(e) => setUploadTags(e.target.value)}
              placeholder="逗号分隔，如：报销,流程"
              className="w-56 rounded-md border border-theme-line bg-theme-input px-2 py-1 text-sm text-theme-text placeholder:text-theme-sub focus:border-brand focus:outline-none"
            />
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-theme-sub">
            <input
              type="checkbox"
              checked={shareTeam}
              onChange={(e) => setShareTeam(e.target.checked)}
              className="accent-brand"
            />
            <Users size={14} />
            上传到团队空间（全员可检索）
          </label>
          <span className="text-xs text-theme-sub">应用于本批上传，便于分类与检索</span>
        </div>
        )}

        {/* 待上传/上传结果面板 */}
        {tab === "mine" && queue.length > 0 && (
          <Card>
            <CardContent className="space-y-2 py-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-theme-text">
                  本次选择 {queue.length} 份
                  {pendingToUpload > 0 ? `，待上传 ${pendingToUpload} 份` : ""}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={clearQueue}
                    disabled={busy}
                    className="cursor-pointer"
                  >
                    清空
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void uploadPending()}
                    disabled={busy || pendingToUpload === 0}
                    className="cursor-pointer"
                  >
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />}
                    {busy ? "上传中…" : `上传 ${pendingToUpload} 份`}
                  </Button>
                </div>
              </div>
              <ul className="divide-y divide-slate-100">
                {queue.map((it) => (
                  <li key={it.id} className="flex items-center justify-between gap-3 py-1.5 text-sm">
                    <div className="min-w-0 flex-1">
                      <p className="truncate" title={it.file.name}>
                        {it.file.name}
                      </p>
                      {it.message && it.status === "error" && (
                        <p className="truncate text-xs text-red-400" title={it.message}>
                          {it.message}
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={
                        it.status === "error" ? "destructive" : it.status === "uploading" ? "warning" : "muted"
                      }
                    >
                      {it.status === "error" ? "未上传" : it.status === "uploading" ? "上传中" : "待上传"}
                    </Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="移出队列"
                      disabled={busy}
                      onClick={() => removeQueueItem(it.id)}
                      className="shrink-0 cursor-pointer text-theme-sub hover:bg-white/10 hover:text-theme-sub"
                    >
                      <X size={15} />
                    </Button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {tab === "mine" && (
        <>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <button
            type="button"
            onClick={() => setFilterFolder(null)}
            className={`rounded-full px-3 py-1 cursor-pointer transition-colors ${filterFolder === null ? "bg-brand text-white" : "bg-white/10 text-theme-sub hover:bg-slate-200"}`}
          >
            全部 {docs.length}
          </button>
          {folders.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilterFolder(filterFolder === f ? null : f)}
              className={`rounded-full px-3 py-1 cursor-pointer transition-colors ${filterFolder === f ? "bg-brand text-white" : "bg-brand/15 text-brand-light hover:bg-indigo-100"}`}
            >
              {f}
            </button>
          ))}
          <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-emerald-400">已入库 {readyCount}</span>
          {pendingCount > 0 && (
            <span className="rounded-full bg-amber-500/15 px-3 py-1 text-amber-400">处理中 {pendingCount}</span>
          )}
          {failedCount > 0 && (
            <span className="rounded-full bg-red-500/15 px-3 py-1 text-red-400">失败 {failedCount}</span>
          )}
          {noTextCount > 0 && (
            <span className="rounded-full bg-white/10 px-3 py-1 text-slate-500">不可检索 {noTextCount}</span>
          )}
        </div>

        {docs.length > 0 && (
          <div className="flex items-center gap-3 text-sm">
            <label className="flex cursor-pointer items-center gap-2 text-theme-sub">
              <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} className="accent-brand" aria-label="全选" />
              全选
            </label>
            {selected.size > 0 && (
              <>
                <span className="text-theme-sub">已选 {selected.size} 份</span>
                <Button size="sm" variant="destructive" onClick={() => setBulkConfirm(true)}>
                  <Trash2 size={14} />
                  批量删除
                </Button>
              </>
            )}
          </div>
        )}
        </>
        )}

        {tab === "team" && (
        <section className="space-y-3">
          {teamDocs.length === 0 ? (
            <div className="flex flex-col items-center rounded-2xl border border-dashed border-theme-line bg-theme-card/60 px-6 py-16 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand/15 text-brand-light">
                <Users size={22} />
              </div>
              <p className="mt-5 font-medium text-theme-text">团队空间还没有共享文档</p>
              <p className="mt-1 text-sm text-theme-sub">在「我的文档」中点击共享按钮，即可把文档共享给全员检索</p>
            </div>
          ) : (
            teamDocs.map((d) => {
              const meta = STATUS_META[d.status];
              return (
                <Card key={d.id} className="transition-shadow hover:shadow-card">
                  <CardContent className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-medium text-theme-text">{d.filename}</p>
                        <Badge variant={meta.variant}>{meta.label}</Badge>
                        {d.stale && (
                          <Badge variant="warning" title={d.stale_reasons.join("\n")}>
                            需刷新
                          </Badge>
                        )}
                        {d.owner_name && (
                          <span className="rounded bg-brand/15 px-1.5 py-0.5 text-xs text-brand-light">
                            {d.owner_name}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-theme-sub">
                        {fmtTime(d.created_at)}
                        {d.status === "ready" && ` · ${d.chunk_count} 个切块`}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`预览 ${d.filename}`}
                        onClick={() => setPreview(d)}
                        className="shrink-0 cursor-pointer text-theme-sub hover:bg-white/10 hover:text-theme-sub"
                      >
                        <Eye size={15} />
                      </Button>
                      {user?.role === "admin" && (
                        <>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`取消共享 ${d.filename}`}
                            title="取消共享（移出团队空间）"
                            disabled={shareTogglingId === d.id}
                            onClick={() => void toggleShare(d)}
                            className="shrink-0 cursor-pointer text-theme-sub hover:bg-white/10 hover:text-theme-sub"
                          >
                            {shareTogglingId === d.id ? (
                              <Loader2 size={15} className="animate-spin" />
                            ) : (
                              <Share2 size={15} />
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`删除 ${d.filename}`}
                            disabled={deletingId === d.id}
                            onClick={() => setSingleConfirm(d)}
                            className="shrink-0 cursor-pointer text-theme-sub hover:bg-red-500/15 hover:text-red-400"
                          >
                            {deletingId === d.id ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                          </Button>
                        </>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </section>
        )}

        {tab === "mine" && (
        <section className="space-y-3">
          {docs.length === 0 ? (
            <div className="flex flex-col items-center rounded-2xl border border-dashed border-theme-line bg-theme-card/60 px-6 py-16 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-brand-dark text-white shadow-pop">
                <FileUp size={22} />
              </div>
              <p className="mt-5 font-medium text-theme-text">还没有上传过文档</p>
              <p className="mt-1 text-sm text-theme-sub">上传制度、手册或 FAQ，即可在问答中检索并带引用回答</p>
              <div className="mt-8 grid w-full max-w-xl gap-3 sm:grid-cols-3">
                {[
                  { icon: FileUp, title: "上传文档", desc: ".txt/.md/.pdf，单个 ≤20MB" },
                  { icon: Layers, title: "自动切分入库", desc: "向量化、可检索" },
                  { icon: Quote, title: "问答带引用", desc: "答案点回原文出处" },
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
              <Button size="sm" onClick={() => fileRef.current?.click()} className="mt-8 cursor-pointer shadow-soft">
                <FileUp size={14} />
                上传第一份文档
              </Button>
            </div>
          ) : (
            filteredDocs.map((d) => {
              const meta = STATUS_META[d.status];
              const sideText =
                d.status === "ready"
                  ? "可用于问答"
                  : d.status === "no_text"
                    ? "纯图片 PDF，无文字层，不可检索"
                    : "处理中…";
              return (
                <Card key={d.id} className="transition-shadow hover:shadow-card">
                  <CardContent className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <input
                      type="checkbox"
                      checked={selected.has(d.id)}
                      onChange={() => toggleSelect(d.id)}
                      aria-label={`选择 ${d.filename}`}
                      className="shrink-0 self-start accent-brand sm:self-center"
                    />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate font-medium text-theme-text">{d.filename}</p>
                        <Badge variant={meta.variant}>{meta.label}</Badge>
                        <span className="text-xs text-theme-sub" title={`内容版本 v${d.version}`}>
                          v{d.version}
                        </span>
                        {d.stale && (
                          <Badge variant="warning" title={d.stale_reasons.join("\n")}>
                            需刷新
                          </Badge>
                        )}
                        {d.visibility === "team" && (
                          <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-xs text-emerald-400" title="已共享到团队空间，全员可检索">
                            团队
                          </span>
                        )}
                        {d.folder && (
                          <span className="rounded bg-brand/15 px-1.5 py-0.5 text-xs text-brand-light">{d.folder}</span>
                        )}
                        {d.tags.map((t) => (
                          <span key={t} className="rounded bg-white/10 px-1.5 py-0.5 text-xs text-slate-500">
                            #{t}
                          </span>
                        ))}
                      </div>
                      <p className="mt-1 text-xs text-theme-sub">
                        {fmtTime(d.created_at)}
                        {d.status === "ready" && ` · ${d.chunk_count} 个切块`}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3 text-right">
                      <div className="text-xs">
                        {d.status === "failed" && d.error ? (
                          <p className="max-w-56 text-red-400" title={d.error}>{d.error}</p>
                        ) : (
                          <p className="text-theme-sub">{sideText}</p>
                        )}
                      </div>
                      {(d.stale || d.status === "failed") && (
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`重新切分 ${d.filename}`}
                          title="按当前配置重新切分"
                          disabled={reingestingId === d.id}
                          onClick={() => void reingest(d)}
                          className="shrink-0 cursor-pointer text-amber-500 hover:bg-amber-500/15 hover:text-amber-400"
                        >
                          {reingestingId === d.id ? (
                            <Loader2 size={15} className="animate-spin" />
                          ) : (
                            <RefreshCw size={15} />
                          )}
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`更新 ${d.filename} 内容`}
                        title="上传新内容（版本 +1）"
                        disabled={updatingContent || PENDING_STATUSES.includes(d.status)}
                        onClick={() => {
                          setUpdateTarget(d);
                          updateFileRef.current?.click();
                        }}
                        className="shrink-0 cursor-pointer text-theme-sub hover:bg-white/10 hover:text-theme-sub"
                      >
                        <FileUp size={15} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={d.visibility === "team" ? `取消共享 ${d.filename}` : `共享 ${d.filename} 到团队空间`}
                        title={d.visibility === "team" ? "取消共享（移出团队空间）" : "共享到团队空间（全员可检索）"}
                        disabled={shareTogglingId === d.id}
                        onClick={() => void toggleShare(d)}
                        className={`shrink-0 cursor-pointer hover:bg-emerald-500/15 hover:text-emerald-400 ${
                          d.visibility === "team" ? "text-emerald-400" : "text-theme-sub"
                        }`}
                      >
                        {shareTogglingId === d.id ? (
                          <Loader2 size={15} className="animate-spin" />
                        ) : (
                          <Share2 size={15} />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`预览 ${d.filename}`}
                        disabled={deletingId === d.id}
                        onClick={() => setPreview(d)}
                        className="shrink-0 cursor-pointer text-theme-sub hover:bg-white/10 hover:text-theme-sub"
                      >
                        <Eye size={15} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`删除 ${d.filename}`}
                        disabled={deletingId === d.id}
                        onClick={() => setSingleConfirm(d)}
                        className="shrink-0 cursor-pointer text-theme-sub hover:bg-red-500/15 hover:text-red-400"
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
        )}

        {preview && (
          <DocumentPreviewModal
            key={preview.id}
            document={preview}
            onClose={() => setPreview(null)}
          />
        )}

        <ConfirmDialog
          open={singleConfirm !== null}
          title="删除文档"
          description={singleConfirm ? `删除「${singleConfirm.filename}」？原始文件与已入库切块（引用数据）将一并删除，无法恢复。` : ""}
          confirmText="删除"
          destructive
          loading={deletingId !== null}
          onConfirm={() => singleConfirm && void removeOne(singleConfirm)}
          onCancel={() => setSingleConfirm(null)}
        />
        <ConfirmDialog
          open={bulkConfirm}
          title="批量删除文档"
          description={`将删除选中的 ${selected.size} 份文档及其入库切块（引用数据），无法恢复。`}
          confirmText={`删除 ${selected.size} 份`}
          destructive
          loading={bulkDeleting}
          onConfirm={() => void removeBulk()}
          onCancel={() => setBulkConfirm(false)}
        />
      </div>
    </main>
  );
}
