import { Loader2, Lock, Plus, Save, ShieldCheck, Trash2, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { z } from "zod";

import { del, get, patch, post } from "../../api/client";
import { PermissionSchema, RoleSchema, type Permission, type Role } from "../../api/schemas";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";

/** 权限点按模块分组（code 前缀，如 document:create → 文档） */
const MODULE_LABELS: Record<string, string> = { document: "文档", admin: "管理" };

function groupPermissions(perms: Permission[]): [string, Permission[]][] {
  const map = new Map<string, Permission[]>();
  for (const p of perms) {
    const module = p.code.split(":")[0] ?? "other";
    map.set(module, [...(map.get(module) ?? []), p]);
  }
  return [...map.entries()].map(([module, items]) => [MODULE_LABELS[module] ?? module, items]);
}

export default function RolesTab() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftPerms, setDraftPerms] = useState<Set<string>>(new Set());
  const [draftDesc, setDraftDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Role | null>(null);
  const [deleting, setDeleting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [roleList, permList] = await Promise.all([
        get("/admin/roles", z.array(RoleSchema)),
        get("/admin/permissions", z.array(PermissionSchema)),
      ]);
      setRoles(roleList);
      setPermissions(permList);
      setSelectedId((prev) => prev ?? roleList[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const selected = useMemo(() => roles.find((r) => r.id === selectedId) ?? null, [roles, selectedId]);

  // 切换选中角色时重置草稿
  useEffect(() => {
    if (!selected) return;
    setDraftPerms(new Set(selected.permissions));
    setDraftDesc(selected.description);
    setCreating(false);
  }, [selected]);

  const locked = selected?.name === "admin";
  const dirty = useMemo(() => {
    if (!selected) return false;
    if (draftDesc !== selected.description) return true;
    if (draftPerms.size !== selected.permissions.length) return true;
    return selected.permissions.some((p) => !draftPerms.has(p));
  }, [selected, draftPerms, draftDesc]);

  const togglePerm = (code: string) => {
    if (locked) return;
    setDraftPerms((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const save = async () => {
    if (!selected) return;
    setSaving(true); setError(null); setMessage(null);
    try {
      await patch(`/admin/roles/${selected.id}`, {
        description: draftDesc,
        ...(locked ? {} : { permissions: [...draftPerms] }),
      }, RoleSchema);
      setMessage("角色已保存");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
    finally { setSaving(false); }
  };

  const createRole = async () => {
    const name = newName.trim();
    if (!name) return;
    setSaving(true); setError(null); setMessage(null);
    try {
      const created = await post("/admin/roles", { name, description: "", permissions: [] }, RoleSchema);
      setNewName(""); setCreating(false);
      setMessage("角色已创建，请勾选权限点后保存");
      await refresh();
      setSelectedId(created.id);
    } catch (e) { setError(e instanceof Error ? e.message : "创建失败"); }
    finally { setSaving(false); }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true); setError(null);
    try {
      await del(`/admin/roles/${deleteTarget.id}`);
      setMessage("角色已删除");
      setDeleteTarget(null);
      setSelectedId(null);
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
    finally { setDeleting(false); }
  };

  const groups = groupPermissions(permissions);

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      {/* 左栏：角色列表 */}
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2"><ShieldCheck size={18} />角色</CardTitle>
          <Button size="sm" variant="ghost" aria-label="新建角色" onClick={() => { setCreating(true); setSelectedId(null); setDraftPerms(new Set()); setDraftDesc(""); }}>
            <Plus size={15} />
          </Button>
        </CardHeader>
        <CardContent className="space-y-1.5">
          {creating && (
            <div className="flex items-center gap-2 rounded-lg border border-brand/40 bg-brand/10 p-2">
              <Input autoFocus placeholder="角色名，如 ops" value={newName} onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void createRole(); }} className="h-8 text-sm" />
              <Button size="sm" disabled={saving || !newName.trim()} onClick={() => void createRole()}>创建</Button>
            </div>
          )}
          {roles.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelectedId(r.id)}
              className={`flex w-full cursor-pointer items-center justify-between rounded-lg border px-3 py-2.5 text-left text-sm transition-colors ${
                selectedId === r.id ? "border-brand/50 bg-brand/10 text-theme-text" : "border-transparent text-theme-sub hover:bg-white/5 hover:text-theme-text"
              }`}
            >
              <span className="flex items-center gap-2">
                <span className="font-medium">{r.name}</span>
                {r.is_builtin && <span className="rounded bg-slate-500/20 px-1.5 py-0.5 text-[10px] text-theme-sub">内置</span>}
              </span>
              <span className="flex items-center gap-1 text-xs text-theme-sub"><Users size={12} />{r.member_count}</span>
            </button>
          ))}
        </CardContent>
      </Card>

      {/* 右栏：权限点勾选矩阵 */}
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle>
            {creating ? "新角色" : selected ? `权限配置：${selected.name}` : "选择左侧角色"}
            {locked && <span className="ml-2 inline-flex items-center gap-1 text-xs font-normal text-amber-400"><Lock size={12} />admin 角色权限锁定，防锁死</span>}
          </CardTitle>
          {selected && !creating && (
            <div className="flex items-center gap-2">
              {!selected.is_builtin && (
                <Button size="sm" variant="ghost" className="text-red-400 hover:bg-red-500/10" aria-label={`删除角色 ${selected.name}`} onClick={() => setDeleteTarget(selected)}>
                  <Trash2 size={14} />
                </Button>
              )}
              <Button size="sm" disabled={saving || !dirty} onClick={() => void save()}>
                {saving ? <Loader2 className="animate-spin" size={14} /> : <Save size={14} />}保存{dirty ? "（未保存）" : ""}
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-5">
          {(message || error) && (
            <div role="status" className={`rounded-lg border px-3 py-2 text-sm ${error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{error ?? message}</div>
          )}
          {!selected && !creating && <p className="py-8 text-center text-sm text-theme-sub">选择左侧角色查看与编辑权限点，或点击 + 新建角色</p>}
          {(selected || creating) && (
            <>
              {selected && (
                <label className="block space-y-1.5 text-sm font-medium">描述
                  <Input value={draftDesc} onChange={(e) => setDraftDesc(e.target.value)} placeholder="角色用途说明" />
                </label>
              )}
              <div className="space-y-4">
                {groups.map(([module, perms]) => (
                  <section key={module}>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-theme-sub">{module}</h3>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {perms.map((p) => {
                        const checked = creating ? false : draftPerms.has(p.code);
                        return (
                          <label
                            key={p.code}
                            className={`flex items-start gap-2.5 rounded-lg border border-theme-line px-3 py-2.5 text-sm transition-colors ${
                              locked || creating ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:border-brand/40"
                            } ${checked ? "border-brand/50 bg-brand/10" : ""}`}
                          >
                            <input
                              type="checkbox"
                              className="mt-0.5 accent-brand"
                              checked={checked}
                              disabled={locked || creating}
                              onChange={() => togglePerm(p.code)}
                            />
                            <span>
                              <span className="block font-mono text-xs text-theme-text">{p.code}</span>
                              <span className="block text-xs text-theme-sub">{p.description}</span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
              {creating && <p className="text-xs text-theme-sub">创建后在角色列表中选中新角色，即可勾选权限点。</p>}
            </>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除角色"
        description={deleteTarget ? `删除角色 ${deleteTarget.name}？其成员将失去该角色带来的权限（现有 ${deleteTarget.member_count} 名成员）。` : ""}
        confirmText="删除"
        destructive
        loading={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
