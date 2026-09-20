/** 评测中心（Admin 第三 Tab）：数据集/评测运行管理 + 召回质量与线上延迟可视化。
 * 选择模型：勾选 run（最多 2 个）驱动下方全部面板 —— 选 1 个看单 run 明细，
 * 选 2 个进入对比模式（按组双系列柱状 + 同组跨 run K 曲线 + 逐题双列对比 + 指标表）。
 * recharts 静态引入本文件，由 AdminPage 经 React.lazy 动态加载（独立 chunk，不进主包）。
 */
import { FlaskConical, Loader2, Play, Plus, Trash2, Upload, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { z } from "zod";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { del, get, post, postForm, withQuery } from "../../api/client";
import {
  EvalDatasetSchema,
  EvalRunDetailSchema,
  EvalRunSchema,
  OnlineStatsSchema,
  pageSchema,
  type EvalDataset,
  type EvalRun,
  type EvalRunDetail,
  type OnlineStats,
} from "../../api/schemas";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Pagination } from "../../components/ui/pagination";
import { SearchInput } from "../../components/ui/search-input";
import { usePaginatedQuery } from "../../hooks/usePaginatedQuery";

interface GroupSummary {
  recall_at_k: Record<string, number>;
  mrr: number;
  answer_hit_rate?: number;
  llm_available?: boolean;
  llm_error?: string;
  latency_ms: Record<string, number>;
}
interface RankEntry {
  rank: number;
  hit: boolean;
  cited?: string[];
  answer_hit?: boolean;
  latency_ms?: Record<string, number>;
}

const GROUP_COLORS = ["#94a3b8", "#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6"];
const RUN_COLORS = ["#6366f1", "#f59e0b"];
const DEFAULT_CMP_GROUP = "hybrid_bm25_rerank";
const pct = (v: number | undefined) => (v === undefined ? "-" : `${(v * 100).toFixed(1)}%`);
const fmtMs = (v: number | null | undefined) => (v == null ? "-" : v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${Math.round(v)}ms`);

// 状态：小圆点 + 文字（紧凑、不换行）
const STATUS_DOT: Record<string, { label: string; dot: string; text: string }> = {
  pending: { label: "排队中", dot: "bg-slate-400", text: "text-slate-500" },
  running: { label: "运行中", dot: "bg-amber-500", text: "text-amber-500" },
  done: { label: "完成", dot: "bg-emerald-500", text: "text-emerald-500" },
  failed: { label: "失败", dot: "bg-red-500", text: "text-red-400" },
};
const GROUP_SHORT: Record<string, string> = {
  baseline: "base",
  hybrid: "hybrid",
  hybrid_bm25: "bm25",
  hybrid_bm25_rerank: "rerank",
};
const runLabel = (name: string) => (name.length > 14 ? `${name.slice(0, 14)}…` : name);

export default function EvalCenterTab() {
  const [online, setOnline] = useState<OnlineStats | null>(null);
  const [showNewRun, setShowNewRun] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 选择模型：勾选（≤2，驱动全部面板）；点行 = 单选
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EvalRunDetail | null>(null);
  const [compareRuns, setCompareRuns] = useState<EvalRunDetail[]>([]);
  const [cmpGroup, setCmpGroup] = useState<string>(DEFAULT_CMP_GROUP);

  const datasetsQuery = usePaginatedQuery<EvalDataset>(
    useCallback(
      (params) => get(withQuery("/admin/eval/datasets", params), pageSchema(EvalDatasetSchema)),
      [],
    ),
    { pageSize: 10 },
  );
  // 运行列表按 created_at 倒序：page=1 即最新一页。pageSize=10（>2 即可）仍足够覆盖
  // 「最新 done run」的查找（并发闸保证同刻最多 1 个在途 run，故最新 done 必在前 2 条内）。
  const runsQuery = usePaginatedQuery<EvalRun>(
    useCallback(
      (params) => get(withQuery("/admin/eval/runs", params), pageSchema(EvalRunSchema)),
      [],
    ),
    { pageSize: 10 },
  );
  const datasets = datasetsQuery.items;
  const runs = runsQuery.items;

  const refreshOnline = useCallback(() => {
    get("/admin/eval/online-stats?days=14", OnlineStatsSchema).then(setOnline).catch(() => {});
  }, []);
  useEffect(() => { refreshOnline(); }, [refreshOnline]);

  const refresh = useCallback(() => {
    datasetsQuery.refresh();
    runsQuery.refresh();
    refreshOnline();
  }, [datasetsQuery.refresh, runsQuery.refresh, refreshOnline]); // eslint-disable-line react-hooks/exhaustive-deps

  // 运行中 run 5s 轮询（终态即停）
  const activeCount = runs.filter((r) => r.status === "pending" || r.status === "running").length;
  useEffect(() => {
    if (activeCount === 0) return;
    const timer = setInterval(refresh, 5_000);
    return () => clearInterval(timer);
  }, [activeCount, refresh]);

  const doneRuns = useMemo(() => runs.filter((r) => r.status === "done"), [runs]);
  const latestDoneId = doneRuns[0]?.id;
  // 新 run 完成时，若用户未手动选择则自动跟随最新
  useEffect(() => {
    if (latestDoneId && !activeRunId && selectedIds.length === 0) setActiveRunId(latestDoneId);
  }, [latestDoneId, activeRunId, selectedIds.length]);

  // 视图模式：勾选优先（1=单 run，2=对比，>2=仅批量管理）；无勾选时看 activeRun（点行/自动最新）
  const viewIds = selectedIds.length > 0 ? selectedIds : activeRunId ? [activeRunId] : [];
  const tooManySelected = selectedIds.length > 2;
  const compareMode = viewIds.length === 2;

  useEffect(() => {
    if (compareMode) { setDetail(null); return; }
    const id = viewIds[0];
    if (!id) { setDetail(null); return; }
    get(`/admin/eval/runs/${id}`, EvalRunDetailSchema).then(setDetail).catch(() => setDetail(null));
  }, [viewIds.join(","), compareMode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!compareMode) { setCompareRuns([]); return; }
    Promise.all(viewIds.map((id) => get(`/admin/eval/runs/${id}`, EvalRunDetailSchema)))
      .then(setCompareRuns)
      .catch(() => setCompareRuns([]));
  }, [viewIds.join(","), compareMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // 勾选不限数量：1 个看明细、2 个进入对比、更多仅用于批量删除
  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  // ---- 删除（单个 / 批量）----
  const [deleteTarget, setDeleteTarget] = useState<EvalRun | null>(null);
  const [batchConfirm, setBatchConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const afterDelete = (ids: string[]) => {
    setSelectedIds((prev) => prev.filter((x) => !ids.includes(x)));
    if (activeRunId && ids.includes(activeRunId)) setActiveRunId(null);
    setDeleteTarget(null);
    setBatchConfirm(false);
    refresh();
  };

  const removeOneRun = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await del(`/admin/eval/runs/${deleteTarget.id}`);
      afterDelete([deleteTarget.id]);
    } catch (e) { setError(e instanceof Error ? e.message : "删除失败"); }
    finally { setDeleting(false); }
  };

  const removeSelectedRuns = async () => {
    setDeleting(true);
    try {
      await post("/admin/eval/runs/batch-delete", { run_ids: selectedIds }, z.object({ deleted: z.number(), failed: z.array(z.string()) }));
      afterDelete(selectedIds);
    } catch (e) { setError(e instanceof Error ? e.message : "批量删除失败"); }
    finally { setDeleting(false); }
  };

  // 对比模式下可选配置组：两 run 交集（无交集则并集）
  const cmpGroups = useMemo(() => {
    if (compareRuns.length !== 2) return [];
    const [a, b] = compareRuns;
    const ga = Object.keys(a?.run.summary ?? {});
    const gb = Object.keys(b?.run.summary ?? {});
    const common = ga.filter((g) => gb.includes(g));
    return common.length > 0 ? common : Array.from(new Set([...ga, ...gb]));
  }, [compareRuns]);
  useEffect(() => {
    if (cmpGroups.length === 0) return;
    if (!cmpGroups.includes(cmpGroup)) setCmpGroup(cmpGroups.includes(DEFAULT_CMP_GROUP) ? DEFAULT_CMP_GROUP : cmpGroups[0]!);
  }, [cmpGroups, cmpGroup]);

  // ---- 数据派生 ----
  const summary = (detail?.run.summary ?? {}) as Record<string, GroupSummary>;
  const groups = Object.keys(summary);
  const groupAt = (g: string): GroupSummary => summary[g] ?? { recall_at_k: {}, mrr: 0, latency_ms: {} };

  const latest = doneRuns[0];
  const latestSummary = (latest?.summary ?? {}) as Record<string, GroupSummary>;
  const bestRecall5 = Math.max(0, ...Object.values(latestSummary).map((g) => g.recall_at_k?.["5"] ?? 0));
  const bestMrr = Math.max(0, ...Object.values(latestSummary).map((g) => g.mrr ?? 0));

  // ① 配置对比柱状：单 run = 各组 Recall@5/MRR；对比 = 按组双 run 系列
  const barData = useMemo(() => {
    if (!compareMode) {
      return groups.map((g) => ({
        group: g,
        "Recall@5": (groupAt(g).recall_at_k?.["5"] ?? 0) * 100,
        MRR: groupAt(g).mrr * 100,
      }));
    }
    const [a, b] = compareRuns;
    if (!a || !b) return [];
    const sa = a.run.summary as Record<string, GroupSummary>;
    const sb = b.run.summary as Record<string, GroupSummary>;
    const allGroups = Array.from(new Set([...Object.keys(sa), ...Object.keys(sb)]));
    return allGroups.map((g) => ({
      group: g,
      [runLabel(a.run.name)]: (sa[g]?.recall_at_k?.["5"] ?? 0) * 100,
      [runLabel(b.run.name)]: (sb[g]?.recall_at_k?.["5"] ?? 0) * 100,
    }));
  }, [compareMode, compareRuns, detail]); // eslint-disable-line react-hooks/exhaustive-deps

  // ② Recall@K 曲线：单 run = 各组线；对比 = 选定组跨 run 双线
  const topkData = useMemo(() => {
    if (!compareMode) {
      if (groups.length === 0) return [];
      const ks = Object.keys(groupAt(groups[0]!).recall_at_k ?? {}).map(Number).sort((a, b) => a - b);
      return ks.map((k) => {
        const point: Record<string, number> = { k };
        for (const g of groups) point[g] = (groupAt(g).recall_at_k?.[String(k)] ?? 0) * 100;
        return point;
      });
    }
    const [a, b] = compareRuns;
    if (!a || !b) return [];
    const sa = a.run.summary as Record<string, GroupSummary>;
    const sb = b.run.summary as Record<string, GroupSummary>;
    const ks = Object.keys(sa[cmpGroup]?.recall_at_k ?? sb[cmpGroup]?.recall_at_k ?? {})
      .map(Number)
      .sort((x, y) => x - y);
    return ks.map((k) => ({
      k,
      [runLabel(a.run.name)]: (sa[cmpGroup]?.recall_at_k?.[String(k)] ?? 0) * 100,
      [runLabel(b.run.name)]: (sb[cmpGroup]?.recall_at_k?.[String(k)] ?? 0) * 100,
    }));
  }, [compareMode, compareRuns, detail, cmpGroup]); // eslint-disable-line react-hooks/exhaustive-deps

  // ④ 指标对比表（对比模式）：run × 组 的精确数值
  const metricRows = useMemo(() => {
    if (!compareMode) return [];
    return compareRuns.flatMap((d) => {
      const s = d.run.summary as Record<string, GroupSummary>;
      return Object.keys(s).map((g) => ({
        run: d.run.name,
        group: g,
        r1: s[g]?.recall_at_k?.["1"] ?? 0,
        r5: s[g]?.recall_at_k?.["5"] ?? 0,
        r10: s[g]?.recall_at_k?.["10"] ?? 0,
        mrr: s[g]?.mrr ?? 0,
        ans: s[g]?.answer_hit_rate,
      }));
    });
  }, [compareMode, compareRuns]);

  const removeDataset = async (datasetId: string) => {
    try {
      await del(`/admin/eval/datasets/${datasetId}`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  };

  return (
    <div className="space-y-6">
      {error && (
        <div role="status" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>
      )}

      {/* KPI 卡条 */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "最佳 Recall@5（最近 run）", value: pct(bestRecall5) },
          { label: "最佳 MRR（最近 run）", value: pct(bestMrr) },
          { label: "线上点踩率（14 天）", value: online?.down_rate == null ? "-" : pct(online.down_rate) },
          { label: "评测运行总数", value: String(runsQuery.total) },
        ].map((c) => (
          <Card key={c.label}><CardContent className="py-4"><p className="text-xs text-theme-sub">{c.label}</p><p className="mt-1 text-xl font-semibold text-theme-text">{c.value}</p></CardContent></Card>
        ))}
      </section>

      {/* 数据集 + 发起 */}
      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2"><FlaskConical size={18} />数据集</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => setShowNewRun(true)} disabled={datasets.length === 0}>
              <Play size={14} />运行新评测
            </Button>
            <ImportButtons onDone={refresh} onError={setError} />
            <SearchInput value={datasetsQuery.query} onChange={datasetsQuery.setQuery} placeholder="搜索数据集名称" ariaLabel="搜索数据集" className="ml-auto w-full sm:w-56" />
          </div>
          {datasetsQuery.error && <p className="text-sm text-red-400">数据集加载失败：{datasetsQuery.error}</p>}
          {datasets.length === 0 ? (
            <p className="py-4 text-sm text-theme-sub">{datasetsQuery.query !== "" ? `没有匹配「${datasetsQuery.query}」的数据集。` : <>还没有数据集：导入内置样例或上传 jsonl（每行 {"{"}"q","gold_doc","gold_keywords"{"}"}）。</>}</p>
          ) : (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-theme-sub"><th className="pb-2">名称</th><th className="pb-2">来源</th><th className="pb-2 text-right">题数</th><th className="pb-2 text-right">操作</th></tr></thead>
              <tbody>
                {datasets.map((d) => (
                  <tr key={d.id} className="border-t border-slate-100">
                    <td className="py-2">{d.name}</td>
                    <td className="py-2 text-theme-sub">{d.source === "builtin" ? "内置" : "上传"}</td>
                    <td className="py-2 text-right">{d.item_count}</td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="ghost" aria-label={`删除 ${d.name}`} onClick={() => void removeDataset(d.id)}>
                        <Trash2 size={14} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Pagination page={datasetsQuery.page} pages={datasetsQuery.pages} total={datasetsQuery.total} onPageChange={datasetsQuery.setPage} disabled={datasetsQuery.loading} />
        </CardContent>
      </Card>

      {/* 运行列表：勾选驱动下方面板；勾选数量不限（批量删除用） */}
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center justify-between gap-2">
            <span>评测运行（勾选 1 个看明细，2 个进入对比）</span>
            <SearchInput value={runsQuery.query} onChange={runsQuery.setQuery} placeholder="搜索运行名称" ariaLabel="搜索评测运行" className="w-full sm:w-56" />
            {selectedIds.length > 0 && (
              <span className="flex items-center gap-2 text-sm font-normal">
                <span className="text-theme-sub">已选 {selectedIds.length} 项</span>
                <Button size="sm" variant="destructive" onClick={() => setBatchConfirm(true)}>
                  <Trash2 size={14} />删除选中
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setSelectedIds([])}>清空选择</Button>
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {runsQuery.error && <p className="mb-2 text-sm text-red-400">评测运行加载失败：{runsQuery.error}</p>}
          {runs.length === 0 ? (
            <p className="py-4 text-sm text-theme-sub">{runsQuery.query !== "" ? `没有匹配「${runsQuery.query}」的评测运行。` : "还没有评测运行。选择数据集后点击「运行新评测」。"}</p>
          ) : (
            <table className="w-full table-auto text-sm">
              <thead><tr className="text-left text-xs text-theme-sub"><th className="w-8 pb-2"></th><th className="pb-2">名称</th><th className="whitespace-nowrap pb-2">状态</th><th className="whitespace-nowrap pb-2">配置组</th><th className="whitespace-nowrap pb-2 text-right">耗时</th><th className="whitespace-nowrap pb-2 text-right">时间</th><th className="w-10 pb-2"></th></tr></thead>
              <tbody>
                {runs.map((r) => {
                  const st = STATUS_DOT[r.status] ?? { label: r.status, dot: "bg-slate-400", text: "text-slate-500" };
                  const groupList = (r.config as { groups?: string[] }).groups ?? [];
                  const gs = groupList.map((g) => GROUP_SHORT[g] ?? g).join("/");
                  const isActive = selectedIds.length > 0 ? selectedIds.includes(r.id) : activeRunId === r.id;
                  return (
                    <tr
                      key={r.id}
                      className={`cursor-pointer border-t border-slate-100 ${isActive ? "bg-brand/5" : "hover:bg-white/5"}`}
                      onClick={() => { setSelectedIds([]); setActiveRunId(r.id); }}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedIds([]);
                          setActiveRunId(r.id);
                        }
                      }}
                    >
                      <td className="py-2 pr-1" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          className="accent-brand"
                          aria-label={`选择 ${r.name}`}
                          checked={selectedIds.includes(r.id)}
                          disabled={r.status !== "done"}
                          onChange={() => toggleSelect(r.id)}
                        />
                      </td>
                      <td className="max-w-0 py-2">
                        <p className="truncate" title={r.name}>{r.name}</p>
                        {r.error && <p className="max-w-72 truncate text-xs text-red-400" title={r.error}>{r.error}</p>}
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3">
                        <span className={`inline-flex items-center gap-1.5 text-xs ${st.text}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} />
                          {st.label}
                        </span>
                      </td>
                      <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs text-theme-sub" title={groupList.join(" / ")}>{gs}</td>
                      <td className="whitespace-nowrap py-2 text-right">{fmtMs(r.duration_ms)}</td>
                      <td className="whitespace-nowrap py-2 pl-3 text-right text-xs text-theme-sub">
                        {new Date(r.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}
                      </td>
                      <td className="py-2 pl-2 text-right" onClick={(e) => e.stopPropagation()}>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={`删除 ${r.name}`}
                          className="text-red-400 hover:bg-red-500/10"
                          onClick={() => setDeleteTarget(r)}
                        >
                          <Trash2 size={14} />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          <Pagination page={runsQuery.page} pages={runsQuery.pages} total={runsQuery.total} onPageChange={runsQuery.setPage} disabled={runsQuery.loading} className="mt-3" />
        </CardContent>
      </Card>

      {tooManySelected && (
        <div role="status" className="rounded-lg border border-theme-line bg-theme-card px-4 py-3 text-sm text-theme-sub">
          已选 {selectedIds.length} 项（仅用于批量删除）。勾选 1 个查看明细，勾选 2 个进入对比模式。
        </div>
      )}

      {/* 选中 run 的状态面板：failed 显示错误，pending/running 显示进度 */}
      {!compareMode && !tooManySelected && detail && detail.run.status === "failed" && (
        <div role="status" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          「{detail.run.name}」运行失败：{detail.run.error ?? "未知错误"}
        </div>
      )}
      {!compareMode && !tooManySelected && detail && (detail.run.status === "pending" || detail.run.status === "running") && (
        <div role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
          「{detail.run.name}」正在{detail.run.status === "pending" ? "排队" : "运行"}中，完成后自动展示数据…
        </div>
      )}
      {!compareMode && !tooManySelected && detail && detail.run.status === "done" && groups.some((g) => groupAt(g).llm_error) && (
        <div role="status" className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
          LLM 答案评测已降级：{groups.map((g) => groupAt(g).llm_error).find(Boolean)}
          （召回指标不受影响；请检查「模型设置」中的 key 或 DEEPSEEK_API_KEY 后重发）
        </div>
      )}
      {compareMode && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-theme-line bg-theme-card px-4 py-3 text-sm">
          <span className="text-theme-sub">对比模式：</span>
          <span className="font-medium text-theme-text">{compareRuns[0]?.run.name ?? "加载中…"}</span>
          <span className="text-theme-sub">vs</span>
          <span className="font-medium text-theme-text">{compareRuns[1]?.run.name ?? "加载中…"}</span>
          <label className="ml-auto flex items-center gap-2 text-theme-sub">
            对比配置组
            <select
              className="rounded-md border border-theme-line bg-theme-input px-2 py-1 text-sm"
              value={cmpGroup}
              onChange={(e) => setCmpGroup(e.target.value)}
            >
              {cmpGroups.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          </label>
          <Button size="sm" variant="ghost" onClick={() => setSelectedIds([])}><X size={14} />退出对比</Button>
        </div>
      )}

      {/* 图表区：① 配置对比 + ② Recall@K 曲线 */}
      {!tooManySelected && ((!compareMode && detail?.run.status === "done" && groups.length > 0) || (compareMode && compareRuns.length === 2)) && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{compareMode ? "配置组对比（Recall@5，双 run）" : `配置组对比 · ${detail?.run.name ?? ""}`}</CardTitle>
            </CardHeader>
            <CardContent className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="group" fontSize={11} />
                  <YAxis unit="%" fontSize={12} domain={[0, 100]} />
                  <Tooltip formatter={(v: unknown) => `${Number(v).toFixed(1)}%`} />
                  <Legend />
                  {compareMode ? (
                    barData.length > 0 &&
                    Object.keys(barData[0]!).filter((k) => k !== "group").map((k, i) => (
                      <Bar key={k} dataKey={k} fill={RUN_COLORS[i % RUN_COLORS.length]} label={{ position: "top", fontSize: 10, formatter: (v: unknown) => `${Number(v).toFixed(0)}` }} />
                    ))
                  ) : (
                    <>
                      <Bar dataKey="Recall@5" fill="#6366f1" label={{ position: "top", fontSize: 10, formatter: (v: unknown) => `${Number(v).toFixed(0)}` }} />
                      <Bar dataKey="MRR" fill="#22c55e" label={{ position: "top", fontSize: 10, formatter: (v: unknown) => `${Number(v).toFixed(0)}` }} />
                    </>
                  )}
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{compareMode ? `Recall@K 曲线（同组：${cmpGroup}）` : "Recall@K 曲线"}</CardTitle>
            </CardHeader>
            <CardContent className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={topkData}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                  <XAxis dataKey="k" fontSize={12} label={{ value: "K", position: "insideBottomRight", fontSize: 11 }} />
                  <YAxis unit="%" fontSize={12} domain={[0, 100]} />
                  <Tooltip formatter={(v: unknown) => `${Number(v).toFixed(1)}%`} />
                  <Legend />
                  {(compareMode ? Object.keys(topkData[0] ?? {}).filter((k) => k !== "k") : groups).map((key, i) => (
                    <Line
                      key={key}
                      dataKey={key}
                      stroke={compareMode ? RUN_COLORS[i % RUN_COLORS.length] : GROUP_COLORS[i % GROUP_COLORS.length]}
                      strokeDasharray={!compareMode && i % 2 === 1 ? "6 3" : undefined}
                      strokeWidth={2}
                      dot={{ r: 2 }}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ④ 指标对比表（对比模式的精确数值，替代原对比图） */}
      {compareMode && metricRows.length > 0 && (
        <Card>
          <CardHeader><CardTitle>指标对比（精确数值）</CardTitle></CardHeader>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs text-theme-sub">
                  <th className="px-4 py-2">运行</th><th className="px-4 py-2">配置组</th>
                  <th className="px-4 py-2 text-right">Recall@1</th><th className="px-4 py-2 text-right">Recall@5</th>
                  <th className="px-4 py-2 text-right">Recall@10</th><th className="px-4 py-2 text-right">MRR</th>
                  <th className="px-4 py-2 text-right">答案正确率</th>
                </tr>
              </thead>
              <tbody>
                {metricRows.map((row) => (
                  <tr key={`${row.run}-${row.group}`} className="border-b border-slate-50 last:border-0">
                    <td className="max-w-56 truncate px-4 py-2" title={row.run}>{row.run}</td>
                    <td className="whitespace-nowrap px-4 py-2 font-mono text-xs">{row.group}</td>
                    <td className="px-4 py-2 text-right">{pct(row.r1)}</td>
                    <td className="px-4 py-2 text-right font-medium">{pct(row.r5)}</td>
                    <td className="px-4 py-2 text-right">{pct(row.r10)}</td>
                    <td className="px-4 py-2 text-right">{pct(row.mrr)}</td>
                    <td className="px-4 py-2 text-right">{row.ans == null ? "-" : pct(row.ans)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* ③ 逐题明细：单 run = 各组；对比 = 选定组跨 run 双列 + 变化 */}
      {!compareMode && !tooManySelected && detail && detail.run.status === "done" && detail.items.length > 0 && (
        <Card>
          <CardHeader><CardTitle>逐题明细（rank 相对 baseline 变化）</CardTitle></CardHeader>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs text-theme-sub">
                  <th className="px-4 py-2">#</th><th className="px-4 py-2">问题</th><th className="px-4 py-2">gold_doc</th>
                  {groups.map((g) => <th key={g} className="px-4 py-2 text-right">{g}</th>)}
                </tr>
              </thead>
              <tbody>
                {detail.items.map((it) => {
                  const ranks = it.ranks as Record<string, RankEntry>;
                  const baseRank = ranks["baseline"]?.rank ?? 0;
                  return (
                    <tr key={it.id} className="border-b border-slate-50 last:border-0">
                      <td className="px-4 py-2 text-theme-sub">{it.idx}</td>
                      <td className="max-w-64 truncate px-4 py-2" title={it.question}>{it.question}</td>
                      <td className="px-4 py-2 text-xs text-theme-sub">{it.gold_doc}</td>
                      {groups.map((g) => {
                        const e = ranks[g];
                        if (!e) return <td key={g} className="px-4 py-2 text-right text-theme-sub">-</td>;
                        const diff = g !== "baseline" && baseRank > 0 && e.rank > 0 ? baseRank - e.rank : 0;
                        return (
                          <td key={g} className="px-4 py-2 text-right">
                            {e.hit ? <span className="text-emerald-500">✓{e.rank}</span> : <span className="text-red-400">✗</span>}
                            {diff > 0 && <span className="ml-1 text-xs text-emerald-500">↑{diff}</span>}
                            {diff < 0 && <span className="ml-1 text-xs text-red-400">↓{-diff}</span>}
                            {"answer_hit" in e && (
                              <span className={`ml-1 text-xs ${e.answer_hit ? "text-emerald-500" : "text-red-400"}`} title="答案关键词命中">
                                {e.answer_hit ? "答✓" : "答✗"}
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {compareMode && compareRuns.length === 2 && (compareRuns[0]?.items.length ?? 0) > 0 && (
        <Card>
          <CardHeader><CardTitle>逐题明细对比（配置组：{cmpGroup}）</CardTitle></CardHeader>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs text-theme-sub">
                  <th className="px-4 py-2">#</th><th className="px-4 py-2">问题</th><th className="px-4 py-2">gold_doc</th>
                  <th className="px-4 py-2 text-right">{runLabel(compareRuns[0]!.run.name)}</th>
                  <th className="px-4 py-2 text-right">{runLabel(compareRuns[1]!.run.name)}</th>
                  <th className="px-4 py-2 text-right">变化</th>
                </tr>
              </thead>
              <tbody>
                {compareRuns[0]!.items.map((it, i) => {
                  const other = compareRuns[1]!.items[i];
                  const ra = (it.ranks as Record<string, RankEntry>)[cmpGroup];
                  const rb = (other?.ranks as Record<string, RankEntry> | undefined)?.[cmpGroup];
                  const diff = (ra?.rank ?? 0) > 0 && (rb?.rank ?? 0) > 0 ? (ra!.rank - rb!.rank) : 0;
                  const cell = (e: RankEntry | undefined) =>
                    !e ? <span className="text-theme-sub">-</span>
                      : e.hit ? <span className="text-emerald-500">✓{e.rank}</span>
                      : <span className="text-red-400">✗</span>;
                  return (
                    <tr key={it.id} className="border-b border-slate-50 last:border-0">
                      <td className="px-4 py-2 text-theme-sub">{it.idx}</td>
                      <td className="max-w-64 truncate px-4 py-2" title={it.question}>{it.question}</td>
                      <td className="px-4 py-2 text-xs text-theme-sub">{it.gold_doc}</td>
                      <td className="px-4 py-2 text-right">{cell(ra)}</td>
                      <td className="px-4 py-2 text-right">{cell(rb)}</td>
                      <td className="px-4 py-2 text-right">
                        {diff > 0 && <span className="text-xs text-emerald-500">↑{diff}</span>}
                        {diff < 0 && <span className="text-xs text-red-400">↓{-diff}</span>}
                        {diff === 0 && <span className="text-xs text-theme-sub">-</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* 线上延迟趋势 */}
      <Card>
        <CardHeader><CardTitle>线上延迟趋势（近 14 天，按日）</CardTitle></CardHeader>
        <CardContent className="h-72">
          {!online || online.points.length === 0 ? (
            <p className="py-8 text-center text-sm text-theme-sub">暂无带耗时采集的线上请求（需新版本后的真实问答产生）。</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={online.points}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="date" fontSize={11} tickFormatter={(d: string) => d.slice(5)} />
                <YAxis unit="ms" fontSize={12} />
                <Tooltip formatter={(v: unknown) => fmtMs(Number(v))} />
                <Legend />
                <Line dataKey="p50_total_ms" name="p50 总耗时" stroke="#6366f1" strokeWidth={2} dot={{ r: 2 }} />
                <Line dataKey="p95_total_ms" name="p95 总耗时" stroke="#f59e0b" strokeWidth={2} strokeDasharray="6 3" dot={{ r: 2 }} />
                <Line dataKey="p50_ttft_ms" name="p50 首token" stroke="#22c55e" strokeWidth={2} strokeDasharray="2 2" dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {showNewRun && (
        <NewRunDialog datasets={datasets} onClose={() => setShowNewRun(false)} onCreated={() => { setShowNewRun(false); refresh(); }} />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除评测运行"
        description={deleteTarget ? `删除「${deleteTarget.name}」及其逐题明细？无法恢复。` : ""}
        confirmText="删除"
        destructive
        loading={deleting}
        onConfirm={() => void removeOneRun()}
        onCancel={() => setDeleteTarget(null)}
      />
      <ConfirmDialog
        open={batchConfirm}
        title="批量删除评测运行"
        description={`删除选中的 ${selectedIds.length} 条评测运行及其逐题明细？无法恢复。`}
        confirmText={`删除 ${selectedIds.length} 条`}
        destructive
        loading={deleting}
        onConfirm={() => void removeSelectedRuns()}
        onCancel={() => setBatchConfirm(false)}
      />
    </div>
  );
}

/** 内置导入 + 上传 jsonl */
function ImportButtons({ onDone, onError }: { onDone: () => void; onError: (m: string) => void }) {
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const importBuiltin = async (file: string) => {
    setBusy(true);
    try {
      await post("/admin/eval/datasets/import-builtin", { file }, EvalDatasetSchema);
      onDone();
    } catch (e) { onError(e instanceof Error ? e.message : "导入失败"); }
    finally { setBusy(false); }
  };
  const upload = async (f: File) => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", f);
      await postForm("/admin/eval/datasets", form, EvalDatasetSchema);
      onDone();
    } catch (e) { onError(e instanceof Error ? e.message : "上传失败"); }
    finally { setBusy(false); }
  };
  return (
    <>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => void importBuiltin("questions.jsonl")}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}导入内置样例
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}>
        <Upload size={14} />上传 jsonl
      </Button>
      <input
        ref={fileRef}
        type="file"
        accept=".jsonl"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void upload(f);
          e.target.value = "";
        }}
      />
    </>
  );
}

/** 发起评测弹窗：数据集 + 语料模式 + 配置组 + top_k + with_llm（含 token 成本提示） */
function NewRunDialog({ datasets, onClose, onCreated }: { datasets: EvalDataset[]; onClose: () => void; onCreated: () => void }) {
  const ALL = ["baseline", "hybrid", "hybrid_bm25", "hybrid_bm25_rerank"];
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? "");
  const [groups, setGroups] = useState<string[]>(ALL);
  const [topKMax, setTopKMax] = useState(10);
  const [withLlm, setWithLlm] = useState(false);
  const [kbMode, setKbMode] = useState<"sample" | "online">("sample");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ds = datasets.find((d) => d.id === datasetId);
  const estCalls = withLlm && ds ? groups.length * ds.item_count : 0;

  const submit = async () => {
    setBusy(true); setError(null);
    try {
      await post("/admin/eval/runs", { dataset_id: datasetId, groups, top_k_max: topKMax, with_llm: withLlm, kb_mode: kbMode }, EvalRunSchema);
      onCreated();
    } catch (e) { setError(e instanceof Error ? e.message : "发起失败"); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/50 p-4" role="dialog" aria-modal="true" aria-label="运行新评测">
      <Card className="w-full max-w-md">
        <CardHeader><CardTitle className="flex items-center justify-between">运行新评测<Button variant="ghost" size="icon" aria-label="关闭" onClick={onClose}><X size={16} /></Button></CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {error && <p className="text-sm text-red-400">{error}</p>}
          <label className="block space-y-1.5 text-sm font-medium">数据集
            <select className="w-full rounded-md border border-theme-line bg-theme-input px-3 py-2 text-sm" value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
              {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}（{d.item_count} 题）</option>)}
            </select>
          </label>
          <fieldset className="space-y-1.5 text-sm font-medium">评测语料
            <div className="mt-1 space-y-1.5">
              <label className="flex cursor-pointer items-start gap-2 text-sm font-normal">
                <input type="radio" name="kb_mode" className="mt-1 accent-brand" checked={kbMode === "sample"} onChange={() => setKbMode("sample")} />
                <span>内置样例语料（4 篇样例文档）<span className="block text-xs text-theme-sub">gold_doc 须为样例库文件名（员工手册.md 等）</span></span>
              </label>
              <label className="flex cursor-pointer items-start gap-2 text-sm font-normal">
                <input type="radio" name="kb_mode" className="mt-1 accent-brand" checked={kbMode === "online"} onChange={() => setKbMode("online")} />
                <span>我的线上知识库<span className="block text-xs text-theme-sub">gold_doc 匹配线上文档名，检索范围 = 我的文档 + 团队空间</span></span>
              </label>
            </div>
          </fieldset>
          <fieldset className="space-y-1.5 text-sm font-medium">配置组
            <div className="mt-1 grid grid-cols-2 gap-2">
              {ALL.map((g) => (
                <label key={g} className="flex cursor-pointer items-center gap-2 text-sm font-normal">
                  <input
                    type="checkbox"
                    className="accent-brand"
                    checked={groups.includes(g)}
                    onChange={(e) => setGroups((prev) => (e.target.checked ? [...prev, g] : prev.filter((x) => x !== g)))}
                  />
                  <span className="font-mono text-xs">{g}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <label className="block space-y-1.5 text-sm font-medium">top_k 上限（Recall@1..K）
            <input type="number" min={1} max={20} className="w-full rounded-md border border-theme-line bg-theme-input px-3 py-2 text-sm" value={topKMax} onChange={(e) => setTopKMax(Number(e.target.value))} />
          </label>
          <label className="flex cursor-pointer items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1 accent-brand" checked={withLlm} onChange={(e) => setWithLlm(e.target.checked)} />
            <span>
              启用 LLM 答案正确率（gold_keywords 命中）
              {withLlm && estCalls > 0 && (
                <span className="mt-0.5 block text-xs text-amber-500">预计 {estCalls} 次模型调用（{groups.length} 组 × {ds?.item_count} 题），将产生 token 费用</span>
              )}
            </span>
          </label>
          <div className="flex gap-2">
            <Button disabled={busy || !datasetId || groups.length === 0} onClick={() => void submit()}>
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}发起评测
            </Button>
            <Button variant="ghost" onClick={onClose}>取消</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
