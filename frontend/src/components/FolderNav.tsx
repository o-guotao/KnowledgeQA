import { Folder, FolderOpen, Layers } from "lucide-react";

import type { OverviewDoc } from "./DocMindmap";
import { UNGROUPED } from "./DocMindmap";

interface FolderNavProps {
  docs: OverviewDoc[];
  activeFolder: string | null;
  onPickFolder: (folder: string | null) => void;
}

interface Group {
  key: string;
  label: string;
  count: number;
  failed: number;
  busy: number;
}

/** 文档管理页左侧文件夹导航（桌面端常驻，仅「列表」视图显示）。
 * 文件夹多时列内滚动：不挤压右栏列表的第一屏位置。
 * 分类导图不在此内嵌——它是与列表互斥的独立视图（见 DocumentsPage 的视图切换），
 * 免得挤在 256px 窄栏里。 */
export function FolderNav({ docs, activeFolder, onPickFolder }: FolderNavProps) {
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
      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto scrollbar-thin">
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
    </nav>
  );
}
