import { ArrowLeft, CheckCircle2, Loader2, Pencil, Plus, Save, Settings2, Trash2, Wifi, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { del, get, patch, post } from "../api/client";
import { ModelConfigSchema, ModelConfigTestResultSchema, type ModelConfig } from "../api/schemas";
import { ThemeToggle } from "../components/ThemeToggle";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";

type Draft = {
  name: string; base_url: string; model_name: string; api_key: string; timeout_seconds: string;
  temperature: string; top_p: string; max_tokens: string;
  price_input_per_million: string; price_output_per_million: string;
};

const emptyDraft = (): Draft => ({
  name: "", base_url: "https://api.deepseek.com", model_name: "deepseek-chat", api_key: "",
  timeout_seconds: "60", temperature: "", top_p: "", max_tokens: "",
  price_input_per_million: "", price_output_per_million: "",
});

const optionalNumber = (raw: string) => (raw.trim() === "" ? null : Number(raw));

function payload(draft: Draft) {
  return {
    name: draft.name, base_url: draft.base_url, model_name: draft.model_name, api_key: draft.api_key,
    timeout_seconds: Number(draft.timeout_seconds),
    temperature: optionalNumber(draft.temperature),
    top_p: optionalNumber(draft.top_p),
    max_tokens: optionalNumber(draft.max_tokens),
    price_input_per_million: optionalNumber(draft.price_input_per_million),
    price_output_per_million: optionalNumber(draft.price_output_per_million),
  };
}

export function ModelSettingsPage() {
  const navigate = useNavigate();
  const [configs, setConfigs] = useState<ModelConfig[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    get("/model-configs", z.array(ModelConfigSchema)).then(setConfigs).catch((err) => setError(err instanceof Error ? err.message : "无法加载模型配置"));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const update = <K extends keyof Draft>(field: K, value: Draft[K]) => setDraft((current) => ({ ...current, [field]: value }));

  const save = async () => {
    setSaving(true); setError(null); setMessage(null);
    try {
      if (editingId) {
        const { api_key, ...rest } = payload(draft);
        await patch(`/model-configs/${editingId}`, api_key ? { ...rest, api_key } : rest, ModelConfigSchema);
        setMessage("模型配置已更新");
      } else {
        await post("/model-configs", payload(draft), ModelConfigSchema);
        setMessage("模型配置已保存并加密");
      }
      setDraft(emptyDraft()); setEditingId(null); refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
    finally { setSaving(false); }
  };

  const edit = (config: ModelConfig) => {
    setEditingId(config.id);
    setDraft({ name: config.name, base_url: config.base_url, model_name: config.model_name, api_key: "", timeout_seconds: String(config.timeout_seconds), temperature: config.temperature === null ? "" : String(config.temperature), top_p: config.top_p === null ? "" : String(config.top_p), max_tokens: config.max_tokens === null ? "" : String(config.max_tokens), price_input_per_million: config.price_input_per_million === null ? "" : String(config.price_input_per_million), price_output_per_million: config.price_output_per_million === null ? "" : String(config.price_output_per_million) });
    setError(null); setMessage(null); window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const activate = async (id: string) => {
    setError(null);
    try { await post(`/model-configs/${id}/activate`, {}, ModelConfigSchema); setMessage("已切换当前问答模型"); refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "切换失败"); }
  };
  const test = async (id: string) => {
    setError(null); setMessage(null);
    try { const result = await post(`/model-configs/${id}/test`, {}, ModelConfigTestResultSchema); (result.ok ? setMessage : setError)(result.message); }
    catch (err) { setError(err instanceof Error ? err.message : "测试失败"); }
  };
  const remove = async (id: string) => {
    if (!window.confirm("删除该模型配置？此操作无法恢复。")) return;
    try { await del(`/model-configs/${id}`); setMessage("模型配置已删除"); refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "删除失败"); }
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-theme-bg via-theme-bg to-theme-deep px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" aria-label="返回问答" onClick={() => navigate("/")}><ArrowLeft size={18} /></Button>
            <div><p className="text-sm font-medium text-brand">个人设置</p><h1 className="text-2xl font-semibold tracking-tight text-theme-text">模型配置</h1></div>
          </div>
          <ThemeToggle />
        </header>
        <p className="max-w-3xl text-sm leading-6 text-theme-sub">每个配置使用 OpenAI Chat Completions 兼容接口。API Key 仅在保存时提交、由服务端加密，之后只显示脱敏值。</p>
        {(message || error) && <div role="status" className={`rounded-lg border px-4 py-3 text-sm ${error ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{error ?? message}</div>}
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2">{editingId ? <Pencil size={18} /> : <Plus size={18} />}{editingId ? "编辑模型配置" : "添加模型配置"}</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm font-medium">配置名称<Input value={draft.name} placeholder="例如：DeepSeek 工作模型" onChange={(e) => update("name", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium">模型名称<Input value={draft.model_name} onChange={(e) => update("model_name", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium sm:col-span-2">Base URL（仅 HTTPS 公网地址）<Input value={draft.base_url} placeholder="https://api.example.com/v1" onChange={(e) => update("base_url", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium sm:col-span-2">API Key<Input type="password" autoComplete="off" value={draft.api_key} placeholder={editingId ? "留空以保留当前密钥" : "仅保存时使用"} onChange={(e) => update("api_key", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium">超时（秒）<Input type="number" min="1" max="300" value={draft.timeout_seconds} onChange={(e) => update("timeout_seconds", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium">采样温度（0–2，可选）<Input type="number" min="0" max="2" step="0.1" placeholder="服务端默认" value={draft.temperature} onChange={(e) => update("temperature", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium">核采样 top_p（0–1，可选）<Input type="number" min="0" max="1" step="0.05" placeholder="服务端默认" value={draft.top_p} onChange={(e) => update("top_p", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium">最大输出 tokens（可选）<Input type="number" min="1" step="1" placeholder="服务端默认，如 2048" value={draft.max_tokens} onChange={(e) => update("max_tokens", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium">输入单价（元/百万 tokens，可选）<Input type="number" min="0" value={draft.price_input_per_million} onChange={(e) => update("price_input_per_million", e.target.value)} /></label>
            <label className="space-y-1.5 text-sm font-medium">输出单价（元/百万 tokens，可选）<Input type="number" min="0" value={draft.price_output_per_million} onChange={(e) => update("price_output_per_million", e.target.value)} /></label>
            <div className="flex gap-2 sm:col-span-2"><Button disabled={saving || !draft.name || !draft.base_url || !draft.model_name || (!editingId && !draft.api_key)} onClick={() => void save()}>{saving ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}{saving ? "保存中…" : editingId ? "保存修改" : "加密保存配置"}</Button>{editingId && <Button variant="ghost" onClick={() => { setEditingId(null); setDraft(emptyDraft()); }}><X size={16} />取消编辑</Button>}</div>
          </CardContent>
        </Card>
        <section className="space-y-3"><h2 className="text-lg font-semibold">已保存的配置</h2>
          {configs.length === 0 ? <Card><CardContent className="flex flex-col items-center gap-2 py-10 text-center"><Settings2 size={22} className="text-theme-sub" /><p className="text-sm text-theme-sub">尚未配置模型。添加并保存后即可用于问答。</p></CardContent></Card> : configs.map((config) => (
            <Card key={config.id} className={config.is_active ? "border-brand/40 ring-1 ring-brand/10" : ""}><CardContent className="flex flex-col gap-4 py-5 sm:flex-row sm:items-center sm:justify-between">
              <div><div className="flex items-center gap-2 font-medium text-theme-text">{config.name}{config.is_active && <span className="inline-flex items-center gap-1 rounded-full bg-brand/10 px-2 py-0.5 text-xs text-brand"><CheckCircle2 size={12} />当前使用</span>}</div><p className="mt-1 text-sm text-theme-sub">{config.model_name} · {config.base_url}</p>{(config.temperature !== null || config.top_p !== null || config.max_tokens !== null) && <p className="mt-1 text-xs text-slate-400">温度 {config.temperature ?? "默认"} · top_p {config.top_p ?? "默认"} · max_tokens {config.max_tokens ?? "默认"}</p>}<p className="mt-1 font-mono text-xs text-slate-400">{config.api_key_masked}</p></div>
              <div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => void test(config.id)}><Wifi size={14} />测试</Button><Button size="sm" variant="outline" onClick={() => edit(config)}><Pencil size={14} />编辑</Button>{!config.is_active && <Button size="sm" onClick={() => void activate(config.id)}>设为当前</Button>}<Button size="sm" variant="ghost" className="text-red-600 hover:bg-red-50 hover:text-red-700" aria-label={`删除 ${config.name}`} onClick={() => void remove(config.id)}><Trash2 size={15} /></Button></div>
            </CardContent></Card>
          ))}
        </section>
      </div>
    </main>
  );
}
