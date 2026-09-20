import { ChevronDown, ChevronRight, Folder, FolderOpen, Hash, Layers } from "lucide-react";
import {
  AnimatePresence,
  animate,
  motion,
  motionValue,
  useTransform,
  type MotionValue,
} from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "../lib/utils";

/** 导图数据源：后端 /documents/overview 的轻量元数据 */
export interface OverviewDoc {
  id: string;
  filename: string;
  folder: string;
  tags: string[];
  status: string;
}

/** 「未分组」哨兵：与后端 UNGROUPED_SENTINEL 对应（folder 为空串的分组） */
export const UNGROUPED = "__ungrouped__";

interface TreeNode {
  key: string;
  label: string;
  /** 文件夹真实值（depth<=1 的文件夹节点用于过滤回调；未分组为 UNGROUPED） */
  folderValue?: string;
  /** 层级：0=根 1=文件夹 2=标签 3=文件（聚焦模式下整体上移一层） */
  depth: 0 | 1 | 2 | 3;
  doc?: OverviewDoc;
  children: TreeNode[];
}

const STATUS_COLOR: Record<string, string> = {
  ready: "#34d399",
  failed: "#f87171",
  uploaded: "#fbbf24",
  processing: "#fbbf24",
  no_text: "#94a3b8",
};

const ROW_H = 30;
const NODE_H = 24;
const V_PAD = 26; // 画布上下留白：节点框以 y 为中心需半高；取较大值让首末行呼吸感更好
const PAD_X = 10; // 节点框内左右留白
const COL_GAP = 44; // 列间连线长度（列 x 由各列最大节点宽累进 + 此间距）
const FONT = 12;
const ROOT_FONT = 13;

// 弹簧参数：刚度偏高 + 阻尼接近临界 → 快速跟手、无震荡，位移类交互的推荐区间
const SPRING = { type: "spring", stiffness: 340, damping: 32 } as const;

/** 文本像素宽估算：CJK ≈ 字号，ASCII ≈ 字号*0.58。仅用于布局，非精确保证。 */
function textWidth(text: string, size: number): number {
  let w = 0;
  for (const ch of text) w += /[\u2E80-\u9FFF\uF900-\uFDFF\uFF00-\uFFEF]/.test(ch) ? size : size * 0.58;
  return w;
}

/** 构建 根→文件夹→标签→文件 分类树。
 * focus 指定文件夹时进入聚焦模式：根=该文件夹，只含其下内容（层级整体上移一层）。 */
function buildTree(docs: OverviewDoc[], focus: string | null): TreeNode {
  const collate = new Intl.Collator("zh-CN");
  const folderMap = new Map<string, TreeNode>();
  for (const d of docs) {
    const fk = d.folder || UNGROUPED;
    let folderNode = folderMap.get(fk);
    if (!folderNode) {
      folderNode = {
        key: `f:${fk}`,
        label: fk === UNGROUPED ? "未分组" : d.folder,
        folderValue: fk,
        depth: 1,
        children: [],
      };
      folderMap.set(fk, folderNode);
    }
    for (const tag of d.tags.length > 0 ? d.tags : [""]) {
      const tk = `${fk}/${tag}`;
      let tagNode = folderNode.children.find((c) => c.key === `t:${tk}`);
      if (!tagNode) {
        tagNode = { key: `t:${tk}`, label: tag || "未打标", depth: 2, children: [] };
        folderNode.children.push(tagNode);
      }
      tagNode.children.push({
        key: `d:${d.id}:${tag}`, label: d.filename, depth: 3, doc: d, children: [],
      });
    }
  }
  for (const f of folderMap.values()) {
    f.children.sort((a, b) => collate.compare(a.label, b.label));
    for (const t of f.children) t.children.sort((a, b) => collate.compare(a.label, b.label));
  }

  if (focus !== null) {
    // 聚焦模式：选中文件夹提升为根（depth 上移），点击根 = 返回全部。
    // key 保持 f:<folder> 不变 —— 全部→聚焦切换时该节点 motion value 延续，位置平滑迁移。
    const folderNode = folderMap.get(focus);
    if (!folderNode) return { key: "root", label: "全部文档", depth: 0, children: [] };
    const count = folderNode.children.reduce((n, t) => n + t.children.length, 0);
    return {
      key: folderNode.key,
      label: `${folderNode.label} ${count}`,
      folderValue: folderNode.folderValue,
      depth: 0,
      children: folderNode.children.map((t) => ({ ...t, depth: 2 as const, children: t.children })),
    };
  }

  const root: TreeNode = { key: "root", label: `全部文档 ${docs.length}`, depth: 0, children: [] };
  root.children = [...folderMap.values()].sort((a, b) => {
    const au = a.folderValue === UNGROUPED;
    const bu = b.folderValue === UNGROUPED;
    if (au !== bu) return au ? 1 : -1; // 未分组排最后
    return collate.compare(a.label, b.label);
  });
  for (const f of root.children) {
    const count = f.children.reduce((n, t) => n + t.children.length, 0);
    f.label = `${f.label} ${count}`;
  }
  return root;
}

interface Pos {
  x: number;
  y: number;
  w: number; // 节点框宽（动态）
}

/** 目标布局：tidy tree（叶子按序占行、父取子中点），列 x 按各列最大宽累进。 */
function layoutTarget(tree: TreeNode, collapsed: Set<string>) {
  const pos = new Map<string, Pos>();
  const widthByDepth = new Map<number, number>();
  let cursor = V_PAD;
  const walk = (n: TreeNode): number => {
    const labelSize = n.depth === 0 ? ROOT_FONT : FONT;
    let w = textWidth(n.label, labelSize) + PAD_X * 2;
    const hasChevron = n.depth < 3 && n.children.length > 0;
    if (hasChevron) w += 16;
    if (n.depth === 3 && n.doc) w += 12; // 状态点
    w = Math.min(w, 220);
    widthByDepth.set(n.depth, Math.max(widthByDepth.get(n.depth) ?? 0, w));
    const expanded = n.depth < 3 && !collapsed.has(n.key) && n.children.length > 0;
    let y: number;
    if (!expanded) {
      y = cursor;
      cursor += ROW_H;
    } else {
      const ys = n.children.map(walk);
      y = (ys[0] + ys[ys.length - 1]) / 2;
    }
    pos.set(n.key, { x: 0, y, w });
    return y;
  };
  walk(tree);
  const colX = new Map<number, number>();
  const depths = [...widthByDepth.keys()].sort();
  let x = 0;
  for (const d of depths) {
    colX.set(d, x);
    x += widthByDepth.get(d)! + COL_GAP;
  }
  const assign = (n: TreeNode) => {
    const p = pos.get(n.key);
    if (p) p.x = colX.get(n.depth) ?? 0;
    for (const c of n.children) assign(c);
  };
  assign(tree);
  return { pos, width: x, height: cursor + V_PAD };
}

interface NodeMv {
  x: MotionValue<number>;
  y: MotionValue<number>;
}

/** 连线：path d 由父子节点的 motion value 派生，节点动画时连线每帧自动跟随。 */
function MindmapLink({
  parent,
  parentW,
  child,
  active,
}: {
  parent: NodeMv;
  parentW: number;
  child: NodeMv;
  active: boolean;
}) {
  const d = useTransform([parent.x, parent.y, child.x, child.y], ([px, py, cx, cy]) => {
    const x0 = px + parentW;
    const mx = (x0 + cx) / 2;
    return `M ${x0} ${py} C ${mx} ${py}, ${mx} ${cy}, ${cx} ${cy}`;
  });
  return (
    <motion.path
      d={d}
      fill="none"
      className={cn("stroke-theme-line", active && "stroke-brand/70")}
      strokeWidth={1.5}
      opacity={0.9}
      initial={{ opacity: 0 }}
      animate={{ opacity: 0.9 }}
      exit={{ opacity: 0 }}
    />
  );
}

interface DocMindmapProps {
  docs: OverviewDoc[];
  /** 当前选中的文件夹过滤值（null=全部；UNGROUPED=未分组） */
  activeFolder: string | null;
  onPickFolder: (folder: string | null) => void;
}

/** 全部态：文件夹卡片网格。文件夹多时纵向单列树会变成几十行长蛇，
 * 改为多列网格 —— 紧凑、高度可控（超限内部滚动）、卡片自带数量与状态摘要。 */
function FolderGrid({ docs, onPickFolder }: { docs: OverviewDoc[]; onPickFolder: (f: string) => void }) {
  const collate = new Intl.Collator("zh-CN");
  const groups = new Map<string, { label: string; count: number; failed: number; busy: number }>();
  for (const d of docs) {
    const fk = d.folder || UNGROUPED;
    let g = groups.get(fk);
    if (!g) {
      g = { label: fk === UNGROUPED ? "未分组" : d.folder, count: 0, failed: 0, busy: 0 };
      groups.set(fk, g);
    }
    g.count += 1;
    if (d.status === "failed") g.failed += 1;
    if (d.status === "uploaded" || d.status === "processing") g.busy += 1;
  }
  const items = [...groups.entries()].sort((a, b) => {
    if ((a[0] === UNGROUPED) !== (b[0] === UNGROUPED)) return a[0] === UNGROUPED ? 1 : -1;
    return collate.compare(a[1].label, b[1].label);
  });

  return (
    <div className="overflow-y-auto scrollbar-thin" style={{ maxHeight: 320 }}>
      <motion.div layout className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
        <AnimatePresence initial={false}>
          {items.map(([fk, g]) => (
            <motion.button
              key={fk}
              type="button"
              layout
              initial={{ opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.94 }}
              transition={{ duration: 0.16 }}
              onClick={() => onPickFolder(fk)}
              className="group flex cursor-pointer items-center gap-2.5 rounded-lg border border-theme-line bg-theme-input/60 px-3 py-2.5 text-left transition-colors hover:border-brand/60 hover:bg-brand/10"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand/15 text-brand-light transition-colors group-hover:bg-brand group-hover:text-white">
                <Folder size={14} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-theme-text" title={g.label}>
                  {g.label}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-theme-sub">
                  {g.count} 份
                  {g.busy > 0 && (
                    <span className="flex items-center gap-0.5 text-amber-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                      {g.busy}
                    </span>
                  )}
                  {g.failed > 0 && (
                    <span className="flex items-center gap-0.5 text-red-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
                      {g.failed}
                    </span>
                  )}
                </span>
              </span>
            </motion.button>
          ))}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}

/** 文档分类思维导图（双态）：
 * - 全部态：文件夹卡片网格（多列、高度可控），点击卡片聚焦该文件夹
 * - 聚焦态：文件夹→标签→文件 的横向树（Framer Motion 弹簧动画），点击根节点返回
 * 聚焦与列表过滤共用 activeFolder，导图与列表始终同步。 */
export function DocMindmap({ docs, activeFolder, onPickFolder }: DocMindmapProps) {
  return (
    <div className="rounded-xl border border-theme-line bg-theme-card p-4 shadow-soft">
      <div className="mb-3 flex items-center gap-2 text-xs text-theme-sub">
        {activeFolder === null ? (
          <>
            <Layers size={13} className="text-brand-light" />
            <span>文件夹总览 · 共 {docs.length} 份文档</span>
            <span className="ml-auto flex items-center gap-1">
              <FolderOpen size={12} /> 点击文件夹查看分类导图
            </span>
          </>
        ) : (
          <>
            <FolderOpen size={13} className="text-brand-light" />
            <span>已聚焦文件夹 · 点击根节点返回全部</span>
            <span className="ml-auto flex items-center gap-1">
              <Hash size={12} /> 点击标签折叠
            </span>
          </>
        )}
      </div>
      {activeFolder === null ? (
        <FolderGrid docs={docs} onPickFolder={onPickFolder} />
      ) : (
        <FocusTree docs={docs} activeFolder={activeFolder} onPickFolder={onPickFolder} />
      )}
    </div>
  );
}

/** 聚焦态的树形导图实现：根（聚焦文件夹）→标签→文件，SVG + motion value 弹簧动画。 */
function FocusTree({
  docs,
  activeFolder,
  onPickFolder,
}: {
  docs: OverviewDoc[];
  activeFolder: string;
  onPickFolder: (folder: string | null) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const tree = useMemo(() => buildTree(docs, activeFolder), [docs, activeFolder]);
  const target = useMemo(() => layoutTarget(tree, collapsed), [tree, collapsed]);

  // 节点 motion value 仓：key -> {x, y}。跨渲染持久，切换树时同 key 节点位置平滑过渡
  const mvStore = useRef(new Map<string, NodeMv>());

  // 渲染期惰性建仓：新节点 motion value 以目标位初始化（挂载动画交给 AnimatePresence 的 opacity/scale）
  const getMv = (key: string, pos: Pos): NodeMv => {
    let mv = mvStore.current.get(key);
    if (!mv) {
      mv = { x: motionValue(pos.x), y: motionValue(pos.y) };
      mvStore.current.set(key, mv);
    }
    return mv;
  };

  // 目标变化：所有节点 spring 迁移；清掉已不在树中的 key 防泄漏
  useEffect(() => {
    for (const [key, p] of target.pos) {
      const mv = mvStore.current.get(key);
      if (!mv) continue; // 渲染期已建仓
      animate(mv.x, p.x, SPRING);
      animate(mv.y, p.y, SPRING);
    }
    for (const key of mvStore.current.keys()) {
      if (!target.pos.has(key)) mvStore.current.delete(key);
    }
  }, [target]);

  const toggle = (key: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const nodes: React.ReactNode[] = [];
  const links: React.ReactNode[] = [];
  const render = (n: TreeNode) => {
    const pos = target.pos.get(n.key);
    if (!pos) return;
    const mv = getMv(n.key, pos);
    const expanded = n.depth < 3 && !collapsed.has(n.key) && n.children.length > 0;
    const isFolderRow = n.depth === 1 || (n.depth === 0 && n.folderValue !== undefined); // 聚焦根=文件夹
    const isActive = isFolderRow && activeFolder !== null && n.folderValue === activeFolder;

    for (const c of n.children) {
      const cpos = target.pos.get(c.key);
      if (!cpos) continue;
      const cmv = getMv(c.key, cpos);
      links.push(
        <MindmapLink
          key={`l:${n.key}-${c.key}`}
          parent={mv}
          parentW={pos.w}
          child={cmv}
          active={isActive}
        />,
      );
    }

    const chevronSpace = n.depth < 3 && n.children.length > 0 ? 16 : 0;
    nodes.push(
      <motion.g
        key={n.key}
        style={{ x: mv.x, y: mv.y }}
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.92 }}
        transition={{ duration: 0.18 }}
        className="cursor-pointer"
        onClick={() => {
          if (isFolderRow) onPickFolder(isActive ? null : n.folderValue ?? null);
          else if (n.depth < 3) toggle(n.key);
        }}
      >
        <title>{n.label}</title>
        {/* 命中区比可见框大一圈，满足最小触达尺寸 */}
        <rect x={-6} y={-NODE_H / 2 - 3} width={pos.w + 16} height={NODE_H + 6} fill="transparent" />
        {n.depth === 3 ? (
          <text x={0} y={5} className="text-[12px] fill-theme-sub">
            {n.label}
          </text>
        ) : (
          <>
            <rect
              x={0}
              y={-NODE_H / 2}
              width={pos.w}
              height={NODE_H}
              rx={7}
              className={cn(
                "transition-colors duration-200",
                n.depth === 0
                  ? "fill-brand/20"
                  : isActive
                    ? "fill-brand"
                    : "fill-brand/15 hover:fill-brand/25",
              )}
            />
            <text
              x={PAD_X}
              y={5}
              className={cn(
                n.depth === 0 ? "text-[13px] font-semibold" : "text-[12px]",
                isActive ? "fill-white font-medium" : "fill-brand-light",
              )}
            >
              {n.label}
            </text>
          </>
        )}
        {n.depth === 3 && n.doc && (
          <circle cx={pos.w + 8} cy={0} r={3.5} fill={STATUS_COLOR[n.doc.status] ?? "#94a3b8"} />
        )}
        {n.depth < 3 && n.children.length > 0 && (
          <g transform={`translate(${pos.w - chevronSpace + 2}, -6)`} opacity={0.7}>
            {expanded ? (
              <ChevronDown size={12} className="text-theme-sub" />
            ) : (
              <ChevronRight size={12} className="text-theme-sub" />
            )}
          </g>
        )}
      </motion.g>,
    );
    for (const c of n.children) render(c);
  };
  render(tree);

  return (
    <div className="overflow-x-auto scrollbar-thin py-1">
      <svg width={target.width} height={target.height} className="min-w-full block">
        <AnimatePresence>{links}</AnimatePresence>
        <AnimatePresence>{nodes}</AnimatePresence>
      </svg>
    </div>
  );
}
