import { Folder, FolderOpen, Layers, Network } from "lucide-react";

import type { OverviewDoc } from "./DocMindmap";
import { DocMindmap, UNGROUPED } from "./DocMindmap";

interface FolderNavProps {
  docs: OverviewDoc[];
  activeFolder: string | null;
  onPickFolder: (folder: string | null) => void;
  /** 导图开合（提升到页面级：默认开） */
  mapOpen: boolean;
  onToggleMap: () => void;
}

interface Group {
  key: string;
  label: string;
  count: number;
  failed: number;
  busy: number;
}

/** 文档管理页左侧复合导航（桌面端常驻）：
 * 上半区 = 文件夹列表（紧凑行），下半区 = 分类思维导图（默认展开）。
 * 导图限高内部滚动：文件夹再多也不挤压右栏列表的第一屏位置。
 * 头部三个分段按钮（列表 / 导图 / 两者）收纳超长内容。 */
export function FolderNav({ docs, activeFolder, onPickFolder, mapOpen, onToggleMap }: FolderNavProps) {
  const collate = new Intl.Collator("zh-CN");
  const groups = new Map<string, Group>();
  for (const d of docs) {
    const fk = d.folder || UNGROUPED;
    let g = groups.get(fk);
    if (!g) {
      g = { key: fk, label: fk === UNGROUPED ? "未分组" : d.folder, count: 0, failed: 0, busy: 0 };
      groups.set(fk, g);
    }
    g.count += 1;
    if (d.status === "failed") g.failed += 1;
    if (d.status === "uploaded" || d.status === "processing") g.busy += 1;
  }
  const items = [...groups.values()].sort((a, b) => {
    if ((a.key === UNGROUPED) !== (b.key === UNGROUPED)) return a.key === UNGROUPED ? 1 : -1;
    return collate.compare(a.label, b.label);
  });

  return (
    <nav
      aria-label="文件夹导航"
      className="flex max-h-[calc(100dvh-9rem)] w-64 shrink-0 flex-col rounded-xl border border-theme-line bg-theme-card p-2 shadow-soft scrollbar-thin lg:sticky lg:top-6"
    >
      <p className="px-2 pb-1.5 pt-1 text-xs font-medium text-theme-sub">文件夹</p>
      <ul className="space-y-0.5 overflow-y-auto scrollbar-thin" style={{ maxHeight: 240 }}>
        <li>
          <button
            type="button"
            onClick={() => onPickFolder(null)}
            aria-current={activeFolder === null ? "true" : undefined}
            className={`flex w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-colors ${
              activeFolder === null
                ? "bg-brand/15 font-medium text-brand-light"
                : "text-theme-text hover:bg-white/5"
            }`}
          >
            <Layers size={14} className="shrink-0 opacity-70" />
            <span className="flex-1">全部文档</span>
            <span className="text-xs text-theme-sub">{docs.length}</span>
          </button>
        </li>
        {items.map((g) => {
          const active = activeFolder === g.key;
          return (
            <li key={g.key}>
              <button
                type="button"
                onClick={() => onPickFolder(active ? null : g.key)}
                aria-current={active ? "true" : undefined}
                title={g.label}
                className={`flex w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-colors ${
                  active
                    ? "bg-brand/15 font-medium text-brand-light"
                    : "text-theme-text hover:bg-white/5"
                }`}
              >
                {active ? (
                  <FolderOpen size={14} className="shrink-0 text-brand-light" />
                ) : (
                  <Folder size={14} className="shrink-0 opacity-70" />
                )}
                <span className="flex-1 truncate">{g.label}</span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-theme-sub">
                  {g.failed > 0 && <span className="h-1.5 w-1.5 rounded-full bg-red-400" title={`${g.failed} 份失败`} />}
                  {g.busy > 0 && <span className="h-1.5 w-1.5 rounded-full bg-amber-400" title={`${g.busy} 份处理中`} />}
                  {g.count}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="mt-1 border-t border-theme-line pt-1">
        <button
          type="button"
          onClick={onToggleMap}
          aria-pressed={mapOpen}
          className={`flex w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-colors ${
            mapOpen ? "bg-brand/15 font-medium text-brand-light" : "text-theme-text hover:bg-white/5"
          }`}
        >
          <Network size={14} className="shrink-0 opacity-70" />
          <span className="flex-1">分类导图</span>
          <span className="text-xs text-theme-sub">{mapOpen ? "收起" : "展开"}</span>
        </button>
      </div>
      {mapOpen && (
        <div className="mt-2 min-h-0 flex-1 overflow-y-auto border-t border-theme-line pt-2 scrollbar-thin">
          <DocMindmap docs={docs} activeFolder={activeFolder} onPickFolder={onPickFolder} compact />
        </div>
      )}
    </nav>
  );
}
