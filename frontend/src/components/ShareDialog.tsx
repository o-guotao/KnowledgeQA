import { Loader2, UserRound, UsersRound, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { z } from "zod";

import { del, get, put, withQuery } from "../api/client";
import {
  GrantSchema,
  PrincipalSearchSchema,
  type Grant,
  type KnowledgeDocument,
  type PrincipalSearch,
} from "../api/schemas";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";
import { SearchInput } from "./ui/search-input";

interface ShareDialogProps {
  document: KnowledgeDocument;
  onClose: () => void;
}

type Candidate = { type: "user" | "group"; id: string; label: string; sub?: string };

/** 文档共享弹窗：搜索用户/用户组 → 授予 read/write → 列表管理（改级别/撤销） */
export function ShareDialog({ document: doc, onClose }: ShareDialogProps) {
  const [grants, setGrants] = useState<Grant[]>([]);
  const [q, setQ] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setGrants(await get(`/documents/${doc.id}/grants`, z.array(GrantSchema)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "授权列表加载失败");
    }
  }, [doc.id]);

  useEffect(() => { void refresh(); }, [refresh]);

  // 主体搜索（防抖 300ms）：用户与组合并展示，已授权的过滤掉
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const res: PrincipalSearch = await get(withQuery("/directory/principals", { q }), PrincipalSearchSchema);
        setCandidates([
          ...res.users.map((u) => ({ type: "user" as const, id: u.id, label: u.username, sub: u.display_name || undefined })),
          ...res.groups.map((g) => ({ type: "group" as const, id: g.id, label: g.name })),
        ]);
      } catch { setCandidates([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const grant = async (c: Candidate, permission: "read" | "write" = "read") => {
    setBusyId(`${c.type}:${c.id}`); setError(null);
    try {
      await put(`/documents/${doc.id}/grants`, { grantee_type: c.type, grantee_id: c.id, permission }, GrantSchema);
      setQ("");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "授权失败"); }
    finally { setBusyId(null); }
  };

  const changeLevel = async (g: Grant, permission: "read" | "write") => {
    setBusyId(g.id); setError(null);
    try {
      await put(`/documents/${doc.id}/grants`, { grantee_type: g.grantee_type, grantee_id: g.grantee_id, permission }, GrantSchema);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "更新失败"); }
    finally { setBusyId(null); }
  };

  const revoke = async (g: Grant) => {
    setBusyId(g.id); setError(null);
    try {
      await del(`/documents/${doc.id}/grants/${g.id}`);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "撤销失败"); }
    finally { setBusyId(null); }
  };

  const grantedKeys = new Set(grants.map((g) => `${g.grantee_type}:${g.grantee_id}`));

  return (
    <Dialog open onClose={onClose} className="max-w-lg">
      <div className="space-y-4">
        <div>
          <h3 className="text-base font-semibold text-theme-text">共享文档</h3>
          <p className="mt-1 truncate text-sm text-theme-sub" title={doc.filename}>{doc.filename}</p>
        </div>
        {error && <p role="status" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        <SearchInput value={q} onChange={setQ} placeholder="搜索用户或用户组，回车前点击结果授权" ariaLabel="搜索用户或用户组" />
        {q && (
          <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-theme-line p-2">
            {candidates.length === 0 && <p className="py-2 text-center text-xs text-theme-sub">无匹配结果</p>}
            {candidates.map((c) => {
              const key = `${c.type}:${c.id}`;
              const already = grantedKeys.has(key);
              return (
                <div key={key} className="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm hover:bg-white/5">
                  <span className="flex items-center gap-2">
                    {c.type === "user" ? <UserRound size={14} className="text-brand-light" /> : <UsersRound size={14} className="text-emerald-400" />}
                    <span>{c.label}</span>
                    {c.sub && <span className="text-xs text-theme-sub">{c.sub}</span>}
                    <span className="rounded bg-slate-500/20 px-1.5 py-0.5 text-[10px] text-theme-sub">{c.type === "user" ? "用户" : "用户组"}</span>
                  </span>
                  {already ? (
                    <span className="text-xs text-theme-sub">已授权</span>
                  ) : (
                    <span className="flex gap-1">
                      <Button size="sm" variant="ghost" disabled={busyId === key} onClick={() => void grant(c, "read")}>可读</Button>
                      <Button size="sm" variant="ghost" disabled={busyId === key} onClick={() => void grant(c, "write")}>可写</Button>
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-sub">已授权（{grants.length}）</p>
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {grants.length === 0 && <p className="py-4 text-center text-sm text-theme-sub">尚未授权给任何人，搜索上方添加</p>}
            {grants.map((g) => (
              <div key={g.id} className="flex items-center justify-between rounded-lg border border-theme-line px-3 py-2 text-sm">
                <span className="flex items-center gap-2">
                  {g.grantee_type === "user" ? <UserRound size={14} className="text-brand-light" /> : <UsersRound size={14} className="text-emerald-400" />}
                  <span>{g.grantee_name || g.grantee_id}</span>
                </span>
                <span className="flex items-center gap-1">
                  {busyId === g.id && <Loader2 size={13} className="animate-spin text-theme-sub" />}
                  <select
                    aria-label="权限级别"
                    className="h-8 cursor-pointer rounded-md border border-theme-line bg-theme-input px-2 text-xs text-theme-text"
                    value={g.permission}
                    disabled={busyId === g.id}
                    onChange={(e) => void changeLevel(g, e.target.value as "read" | "write")}
                  >
                    <option value="read">可读</option>
                    <option value="write">可写</option>
                  </select>
                  <Button size="sm" variant="ghost" className="text-red-400 hover:bg-red-500/10" aria-label={`撤销 ${g.grantee_name} 的授权`} disabled={busyId === g.id} onClick={() => void revoke(g)}>
                    <X size={13} />
                  </Button>
                </span>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs leading-5 text-theme-sub">可读：检索与预览本文档；可写：额外可更新内容与删除。用户组成员自动继承组的授权。</p>
      </div>
    </Dialog>
  );
}
