import { X } from "lucide-react";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

/** 轻量玻璃拟态弹窗（ESC 关闭、遮罩点击关闭） */
export function Dialog({ open, onClose, children, className }: DialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-up"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        className={cn("glass relative w-full max-w-md rounded-2xl p-6", className)}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="absolute right-4 top-4 rounded-md p-1 text-theme-sub hover:bg-white/10 hover:text-theme-text cursor-pointer"
        >
          <X size={16} />
        </button>
        {children}
      </div>
    </div>
  );
}
