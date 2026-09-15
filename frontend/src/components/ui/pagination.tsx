import { ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "../../lib/utils";
import { Button } from "./button";

export interface PaginationProps {
  page: number;
  pages: number;
  total: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * 列表分页控件：单页（pages <= 1）时整体不渲染，避免噪音。
 */
export function Pagination({
  page,
  pages,
  total,
  onPageChange,
  disabled = false,
  className,
}: PaginationProps) {
  if (pages <= 1) return null;

  return (
    <nav
      aria-label="分页"
      className={cn("flex flex-wrap items-center justify-between gap-3 text-sm", className)}
    >
      <span className="text-theme-sub">共 {total} 条</span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft size={14} />
          上一页
        </Button>
        <span className="min-w-20 text-center text-theme-sub">
          第 {page} / {pages} 页
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled || page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          下一页
          <ChevronRight size={14} />
        </Button>
      </div>
    </nav>
  );
}
