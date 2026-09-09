import { ArrowLeft, Cpu, Loader2, Pencil, Plus, Save, Trash2, TrendingUp, Users, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { del, get, patch, post } from "../api/client";
import {
  AdminUserSchema,
  DailyUsageSchema,
  ModelUsageSchema,
  UserUsageSchema,
  type AdminUser,
  type DailyUsage,
  type ModelUsage,
  type UserUsage,
} from "../api/schemas";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Input } from "../components/ui/input";

const fmtTokens = (n: number) => (n >= 10000 ? `${(n / 10000).toFixed(1)}万` : String(n));
const fmtCost = (n: number) => `¥${n.toFixed(4)}`;

type Draft = { username: string; password: string; display_name: string; role: string; limit_tokens: string };
const emptyDraft = (): Draft => ({ username: "", password: "", display_name: "", role: "user", limit_tokens: "" });

export function AdminPage() {
  const navigate = useNavigate();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [byModel, setByModel] = useState<ModelUsage[]>([]);
  const [byUser, setByUser] = useState<UserUsage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(() => {
    get("/admin/users", z.array(AdminUserSchema))
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : "加载用户失败"));
    get("/admin/usage/daily?days=30", z.array(DailyUsageSchema)).then(setDaily).catch(() => {});
    get("/admin/usage/by-model?days=30", z.array(ModelUsageSchema)).then(setByModel).catch(() => {});
    get("/admin/usage/by-user?days=30", z.array(UserUsageSchema)).then(setByUser).catch(() => {});
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const summary = useMemo(
    () => ({
      tokens: daily.reduce((s, d) => s + d.total_tokens, 0),
      cost: daily.reduce((s, d) => s + d.cost_cny, 0),
      calls: daily.reduce((s, d) => s + d.calls, 0),
    }),
    [daily],
  );
  const maxDaily = useMemo(() => Math.max(1, ...daily.map((d) => d.total_tokens)), [daily]);

  const resetDraft = () => { setEditingId(null); setDraft(emptyDraft()); };

  const save = async () => {
    setSaving(true); setError(null); setMessage(null);
    try {
      if (editingId) {
        const body: Record<string, unknown> = {};
        if (draft.display_name) body.display_name = draft.display_name;
        if (draft.role) body.role = draft.role;
        if (draft.password) body.password = draft.password;
        if (draft.limit_tokens) body.limit_tokens = Number(draft.limit_tokens);
        await patch(`/admin/users/${editingId}`, body, AdminUserSchema);
        setMessage("用户已更新");
      } else {
        await post(
          "/admin/users",
          { username: draft.username, password: draft.password, display_name: draft.display_name, role: draft.role },
          AdminUserSchema,
        );
        setMessage("用户已创建");
      }
      resetDraft(); refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
    finally { setSaving(false); }
  };

  const edit = (u: AdminUser) => {
    setEditingId(u.id);
    setDraft({ username: u.username, password: "", display_name: u.display_name, role: u.role, limit_tokens: String(u.month.limit_tokens) });
    setError(null); setMessage(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleting, setDeleting] = useState(false);
  const confirmRemove = async () => {
    if (!deleteTarget) return;
    setDeleting(true); setError(null);
    try {
      await del(`/admin/users/${deleteTarget.id}`);
      setMessage("用户已删除");
      setDeleteTarget(null);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
    finally { setDeleting(false); }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-theme-bg via-theme-bg to-theme-deep px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex items-center gap-3">
          <Button variant="ghost" size="icon" aria-label="返回问答" onClick={() => navigate("/")}><ArrowLeft size={18} /></Button>
          <div><p className="text-sm font-medium text-brand">管理后台</p><h1 className="text-2xl font-semibold tracking-tight text-theme-text">用量与用户管理</h1></div>
        </header>
        {(message || error) && (
          <div role="status" className={`rounded-lg border px-4 py-3 text-sm ${error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{error ?? message}</div>
        )}

        <section className="grid gap-4 sm:grid-cols-3">
          {[
            { label: "近30天 Tokens", value: fmtTokens(summary.tokens) },
            { label: "近30天成本", value: fmtCost(summary.cost) },
            { label: "近30天调用", value: `${summary.calls} 次` },
          ].map((c) => (
            <Card key={c.label}><CardContent className="py-5"><p className="text-sm text-theme-sub">{c.label}</p><p className="mt-1 text-2xl font-semibold text-theme-text">{c.value}</p></CardContent></Card>
          ))}
        </section>

        <Card>
          <CardHeader><CardTitle>按日用量（近30天）</CardTitle></CardHeader>
          <CardContent>
            {daily.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-8 text-center">
                <TrendingUp size={22} className="text-theme-sub" />
                <p className="text-sm text-theme-sub">暂无调用记录，发起一次对话后这里会展示用量趋势</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {daily.map((d) => (
                  <div key={d.date} className="flex items-center gap-3 text-xs">
                    <span className="w-16 shrink-0 font-mono text-slate-500">{d.date.slice(5)}</span>
                    <div className="h-4 flex-1 rounded bg-slate-100">
                      <div className="h-4 rounded bg-brand/70" style={{ width: `${(d.total_tokens / maxDaily) * 100}%` }} />
                    </div>
                    <span className="w-14 shrink-0 text-right text-slate-600">{fmtTokens(d.total_tokens)}</span>
                    <span className="w-20 shrink-0 text-right text-slate-500">{fmtCost(d.cost_cny)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle>模型使用分布</CardTitle></CardHeader>
            <CardContent>
              {byModel.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-center">
                  <Cpu size={22} className="text-theme-sub" />
                  <p className="text-sm text-theme-sub">暂无模型调用数据</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-theme-sub"><th className="pb-2">模型</th><th className="pb-2 text-right">调用</th><th className="pb-2 text-right">Tokens</th><th className="pb-2 text-right">成本</th></tr></thead>
                  <tbody>{byModel.map((m) => <tr key={m.model} className="border-t border-slate-100"><td className="py-2 font-mono text-xs">{m.model}</td><td className="py-2 text-right">{m.calls}</td><td className="py-2 text-right">{fmtTokens(m.total_tokens)}</td><td className="py-2 text-right">{fmtCost(m.cost_cny)}</td></tr>)}</tbody>
                </table>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>按用户用量</CardTitle></CardHeader>
            <CardContent>
              {byUser.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-center">
                  <Users size={22} className="text-theme-sub" />
                  <p className="text-sm text-theme-sub">暂无用户用量数据</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead><tr className="text-left text-xs text-theme-sub"><th className="pb-2">用户</th><th className="pb-2 text-right">调用</th><th className="pb-2 text-right">Tokens</th><th className="pb-2 text-right">成本</th></tr></thead>
                  <tbody>{byUser.map((u) => <tr key={u.user_id} className="border-t border-slate-100"><td className="py-2">{u.username}</td><td className="py-2 text-right">{u.calls}</td><td className="py-2 text-right">{fmtTokens(u.total_tokens)}</td><td className="py-2 text-right">{fmtCost(u.cost_cny)}</td></tr>)}</tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2">{editingId ? <Pencil size={18} /> : <Plus size={18} />}{editingId ? "编辑用户" : "新建用户"}</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <label className="space-y-1.5 text-sm font-medium">用户名<Input value={draft.username} disabled={!!editingId} onChange={(e) => setDraft({ ...draft, username: e.target.value })} /></label>
            <label className="space-y-1.5 text-sm font-medium">显示名<Input value={draft.display_name} onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} /></label>
            <label className="space-y-1.5 text-sm font-medium">密码<Input type="password" autoComplete="off" placeholder={editingId ? "留空不修改" : ""} value={draft.password} onChange={(e) => setDraft({ ...draft, password: e.target.value })} /></label>
            <label className="space-y-1.5 text-sm font-medium">角色
              <select className="w-full rounded-md border border-input border-theme-line bg-theme-input px-3 py-2 text-sm" value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })}>
                <option value="user">user</option><option value="admin">admin</option>
              </select>
            </label>
            {editingId && <label className="space-y-1.5 text-sm font-medium">当月配额(tokens)<Input type="number" min="0" value={draft.limit_tokens} onChange={(e) => setDraft({ ...draft, limit_tokens: e.target.value })} /></label>}
            <div className="flex gap-2 sm:col-span-2 lg:col-span-5">
              <Button disabled={saving || (!editingId && (!draft.username || !draft.password))} onClick={() => void save()}>
                {saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}{editingId ? "保存修改" : "创建用户"}
              </Button>
              {editingId && <Button variant="ghost" onClick={resetDraft}><X size={16} />取消</Button>}
            </div>
          </CardContent>
        </Card>

        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><Users size={18} />用户列表</h2>
          <Card><CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-100 text-left text-xs text-theme-sub"><th className="px-4 py-3">用户名</th><th className="px-4 py-3">角色</th><th className="px-4 py-3 text-right">当月Tokens</th><th className="px-4 py-3 text-right">当月成本</th><th className="px-4 py-3 text-right">配额</th><th className="px-4 py-3 text-right">操作</th></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-slate-50 last:border-0">
                    <td className="px-4 py-3"><div className="font-medium text-theme-text">{u.username}</div>{u.display_name && <div className="text-xs text-theme-sub">{u.display_name}</div>}</td>
                    <td className="px-4 py-3"><span className={`rounded-full px-2 py-0.5 text-xs ${u.role === "admin" ? "bg-brand/10 text-brand" : "bg-slate-100 text-slate-600"}`}>{u.role}</span></td>
                    <td className="px-4 py-3 text-right">{fmtTokens(u.month.total_tokens)}</td>
                    <td className="px-4 py-3 text-right">{fmtCost(u.month.cost_cny)}</td>
                    <td className="px-4 py-3 text-right text-slate-500">{fmtTokens(u.month.limit_tokens)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" aria-label={`编辑 ${u.username}`} onClick={() => edit(u)}><Pencil size={14} /></Button>
                        <Button size="sm" variant="ghost" className="text-red-400 hover:bg-red-500/10" aria-label={`删除 ${u.username}`} onClick={() => setDeleteTarget(u)}><Trash2 size={14} /></Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent></Card>
        </section>

        <ConfirmDialog
          open={deleteTarget !== null}
          title="删除用户"
          description={deleteTarget ? `删除用户 ${deleteTarget.username}？其会话与数据将一并删除，无法恢复。` : ""}
          confirmText="删除"
          destructive
          loading={deleting}
          onConfirm={() => void confirmRemove()}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </main>
  );
}
