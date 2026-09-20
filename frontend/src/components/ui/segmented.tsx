import type { LucideIcon } from "lucide-react";

import { cn } from "../../lib/utils";

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: LucideIcon;
}

export interface SegmentedProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: readonly SegmentedOption<T>[];
  ariaLabel: string;
  className?: string;
}

/**
 * 分段控件（受控）：一组互斥选项，选中项高亮。
 * 用 `role="group"` + `aria-pressed` 而非 `role="tablist"`——后者按 ARIA 要求方向键导航，
 * 这里只做点击/Enter/Space 切换，按钮组语义完整且更简单。
 */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}: SegmentedProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg border border-theme-line bg-theme-card p-0.5 shadow-soft",
        className,
      )}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        const Icon = opt.icon;
        return (
          <button
            key={opt.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              "inline-flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] transition-colors",
              active
                ? "bg-brand font-medium text-white"
                : "text-theme-sub hover:bg-white/5 hover:text-theme-text",
            )}
          >
            {Icon && <Icon size={14} className="shrink-0" aria-hidden />}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
