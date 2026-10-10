import { useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Compass,
  ListTodo,
  Loader2,
  Minus,
  ShieldCheck,
  Wrench,
  X,
} from "lucide-react";

import type { AgentStep } from "../api/schemas";
import { cn } from "../lib/utils";

const TYPE_META = {
  router: { icon: Compass, name: "路由" },
  plan: { icon: ListTodo, name: "计划" },
  tool: { icon: Wrench, name: "执行" },
  review: { icon: ShieldCheck, name: "校验" },
} as const;

function StatusIcon({ status }: { status: AgentStep["status"] }) {
  switch (status) {
    case "running":
      return <Loader2 size={12} className="animate-spin text-brand-light" />;
    case "done":
      return <Check size={12} className="text-emerald-400" />;
    case "failed":
      return <X size={12} className="text-red-400" />;
    case "skipped":
      return <Minus size={12} className="text-slate-500" />;
  }
}

/** 编排步骤时间线：路由分类/计划/工具执行/校验结论，可折叠。
 * 实时（SSE agent_step 事件）与历史（messages.tool_call 留痕恢复）共用。 */
export function AgentStepTimeline({ steps }: { steps: AgentStep[] }) {
  const [open, setOpen] = useState(false);
  if (steps.length === 0) return null;
  const running = steps.some((s) => s.status === "running");
  const failed = steps.some((s) => s.status === "failed");

  return (
    <div className="rounded-lg border border-theme-line bg-theme-card/70 text-xs shadow-soft">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-left text-theme-sub transition-colors hover:text-theme-text"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <span className="font-medium">编排步骤（{steps.length}）</span>
        {running && <Loader2 size={12} className="animate-spin text-brand-light" />}
        {!running && failed && <X size={12} className="text-red-400" />}
        {!open && (
          <span className="truncate text-slate-500">
            {steps[steps.length - 1]?.label}
          </span>
        )}
      </button>
      {open && (
        <ol className="space-y-1 border-t border-theme-line px-2.5 py-2">
          {steps.map((s, i) => {
            const meta = TYPE_META[s.step_type];
            const Icon = meta.icon;
            return (
              <li key={i} className="flex items-center gap-2">
                <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                  <StatusIcon status={s.status} />
                </span>
                <Icon size={12} className="shrink-0 text-slate-500" aria-label={meta.name} />
                <span
                  className={cn(
                    "min-w-0 flex-1 truncate",
                    s.status === "skipped" ? "text-slate-500 line-through" : "text-theme-sub",
                  )}
                  title={s.label}
                >
                  {s.label}
                </span>
                {s.status === "done" && s.duration_ms > 0 && (
                  <span className="shrink-0 text-slate-500">{(s.duration_ms / 1000).toFixed(1)}s</span>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
