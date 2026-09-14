import { Search, X } from "lucide-react";

import { cn } from "../../lib/utils";
import { Input } from "./input";

export interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
}

/**
 * 列表搜索框（纯受控）：防抖在 usePaginatedQuery 里，本组件不持有定时器。
 * 有值时右侧显示清除按钮。
 */
export function SearchInput({
  value,
  onChange,
  placeholder = "搜索…",
  ariaLabel = "搜索",
  className,
}: SearchInputProps) {
  return (
    <div className={cn("relative", className)}>
      <Search
        size={15}
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-theme-sub"
      />
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className="h-9 pl-9 pr-9"
      />
      {value !== "" && (
        <button
          type="button"
          aria-label="清除搜索"
          onClick={() => onChange("")}
          className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer rounded p-1 text-theme-sub transition-colors hover:bg-white/10 hover:text-theme-text"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
