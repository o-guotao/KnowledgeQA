import { Loader2, Plus, Trash2, UserPlus, Users, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { z } from "zod";

import { del, get, post, withQuery } from "../../api/client";
import {
  GroupMemberSchema,
  GroupSchema,
  PrincipalSearchSchema,
  type Group,
  type GroupMember,
} from "../../api/schemas";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Dialog } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { SearchInput } from "../../components/ui/search-input";

export default function GroupsTab() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Group | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [memberGroup, setMemberGroup] = useState<Group | null>(null);

  const refresh = useCallback(async () => {
    try {
      setGroups(await get(withQuery("/groups", { q: query }), z.array(GroupSchema)));
    } catch (e) { setError(e instanceof Error ? e.message : "加载失败"); }
  }, [query]);

  useEffect(() => {
    const t = setTimeout(() => void refresh(), 300);
    return () => clearTimeout(t);
  }, [refresh]);

  const createGroup = async () => {
    if (!newName.trim()) return;
    setSaving(true); setError(null); setMessage(null);
    try {
      await post("/groups", { name: newName.trim(), description: newDesc.trim() }, GroupSchema);
      setNewName(""); setNewDesc(""); setCreating(false);
      setMessage("用户组已创建");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "创建失败"); }
    finally { setSaving(false); }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true); setError(null);
    try {
      await del(`/groups/${deleteTarget.id}`);
      setMessage("用户组已删除");
      setDeleteTarget(null);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
    finally { setDeleting(false); }
  };

  return (
    <div className="space-y-4">
      {(message || error) && (
        <div role="status" className={`rounded-lg border px-4 py-3 text-sm ${error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{error ?? message}</div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SearchInput value={query} onChange={setQuery} placeholder="搜索用户组" ariaLabel="搜索用户组" className="w-full sm:w-64" />
        <Button onClick={() => setCreating(true)}><Plus size={16} />新建用户组</Button>
      </div>

      {groups.length === 0 ? (
        <div className="flex flex-col items-center rounded-2xl border border-dashed border-theme-line bg-theme-card/60 px-6 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-brand/15 text-brand-light"><Users size={22} /></div>
          <p className="mt-5 font-medium text-theme-text">{query ? `没有匹配「${query}」的用户组` : "还没有用户组"}</p>
          <p className="mt-1 text-sm text-theme-sub">创建用户组后，可将文档一次性授权给整组成员</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {groups.map((g) => (
            <Card key={g.id} className="transition-shadow hover:shadow-card">
              <CardHeader className="flex-row items-start justify-between gap-2">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">{g.name}</CardTitle>
                  <p className="mt-1 text-xs text-theme-sub">{g.description || "暂无描述"}</p>
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" aria-label={`管理 ${g.name} 成员`} title="成员管理" onClick={() => setMemberGroup(g)}><UserPlus size={14} /></Button>
                  <Button size="sm" variant="ghost" className="text-red-400 hover:bg-red-500/10" aria-label={`删除 ${g.name}`} onClick={() => setDeleteTarget(g)}><Trash2 size={14} /></Button>
                </div>
              </CardHeader>
              <CardContent className="flex items-center gap-4 text-xs text-theme-sub">
                <span className="flex items-center gap-1"><Users size={12} />{g.member_count} 名成员</span>
                {g.owner_name && <span>创建者：{g.owner_name}</span>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 新建组弹窗 */}
      <Dialog open={creating} onClose={() => setCreating(false)}>
        <div className="space-y-4">
          <h3 className="text-base font-semibold text-theme-text">新建用户组</h3>
          <label className="block space-y-1.5 text-sm font-medium">组名
            <Input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="如：人事部" />
          </label>
          <label className="block space-y-1.5 text-sm font-medium">描述
            <Input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="可选" />
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setCreating(false)}>取消</Button>
            <Button disabled={saving || !newName.trim()} onClick={() => void createGroup()}>
              {saving ? <Loader2 className="animate-spin" size={14} /> : <Plus size={14} />}创建
            </Button>
          </div>
        </div>
      </Dialog>

      {memberGroup && (
        <MembersDialog group={memberGroup} onClose={() => { setMemberGroup(null); void refresh(); }} />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除用户组"
        description={deleteTarget ? `删除用户组 ${deleteTarget.name}？组内 ${deleteTarget.member_count} 名成员将失去经该组继承的文档授权。` : ""}
        confirmText="删除"
        destructive
        loading={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

/** 成员管理弹窗：搜索添加 / 移除成员 */
function MembersDialog({ group, onClose }: { group: Group; onClose: () => void }) {
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [q, setQ] = useState("");
  const [candidates, setCandidates] = useState<{ id: string; username: string; display_name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshMembers = useCallback(async () => {
    try {
      setMembers(await get(`/groups/${group.id}/members`, z.array(GroupMemberSchema)));
    } catch (e) { setError(e instanceof Error ? e.message : "成员加载失败"); }
  }, [group.id]);

  useEffect(() => { void refreshMembers(); }, [refreshMembers]);

  // 搜索候选用户（防抖 300ms）
  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const res = await get(withQuery("/directory/principals", { q }), PrincipalSearchSchema);
        setCandidates(res.users);
      } catch { setCandidates([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const memberIds = useMemo(() => new Set(members.map((m) => m.user_id)), [members]);

  const add = async (userId: string) => {
    setBusy(true); setError(null);
    try {
      await post(`/groups/${group.id}/members`, { user_id: userId }, z.array(GroupMemberSchema));
      await refreshMembers();
    } catch (e) { setError(e instanceof Error ? e.message : "添加失败"); }
    finally { setBusy(false); }
  };

  const remove = async (userId: string) => {
    setBusy(true); setError(null);
    try {
      await del(`/groups/${group.id}/members/${userId}`);
      await refreshMembers();
    } catch (e) { setError(e instanceof Error ? e.message : "移除失败"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onClose={onClose} className="max-w-lg">
      <div className="space-y-4">
        <h3 className="text-base font-semibold text-theme-text">成员管理：{group.name}</h3>
        {error && <p role="status" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <SearchInput value={q} onChange={setQ} placeholder="搜索用户名 / 显示名添加成员" ariaLabel="搜索用户" />
        {q && (
          <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-theme-line p-2">
            {candidates.length === 0 && <p className="py-2 text-center text-xs text-theme-sub">无匹配用户</p>}
            {candidates.map((u) => (
              <div key={u.id} className="flex items-center justify-between rounded px-2 py-1.5 text-sm hover:bg-white/5">
                <span>{u.username}{u.display_name && <span className="ml-1 text-xs text-theme-sub">{u.display_name}</span>}</span>
                {memberIds.has(u.id) ? (
                  <span className="text-xs text-theme-sub">已加入</span>
                ) : (
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => void add(u.id)}><Plus size={13} /></Button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="max-h-56 space-y-1 overflow-y-auto">
          {members.length === 0 && <p className="py-4 text-center text-sm text-theme-sub">暂无成员，搜索用户添加</p>}
          {members.map((m) => (
            <div key={m.user_id} className="flex items-center justify-between rounded-lg border border-theme-line px-3 py-2 text-sm">
              <span>{m.username}{m.display_name && <span className="ml-1 text-xs text-theme-sub">{m.display_name}</span>}</span>
              <Button size="sm" variant="ghost" className="text-red-400 hover:bg-red-500/10" aria-label={`移除 ${m.username}`} disabled={busy} onClick={() => void remove(m.user_id)}>
                <X size={13} />
              </Button>
            </div>
          ))}
        </div>
      </div>
    </Dialog>
  );
}
