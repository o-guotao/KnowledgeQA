import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: ReactNode;
  confirmText?: string;
  cancelText?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 全局统一确认弹窗（替代 window.confirm）：深炭黑主题、ESC/遮罩关闭、危险操作红色确认 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmText = "确认",
  cancelText = "取消",
  destructive = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onClose={onCancel}>
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-base font-semibold text-theme-text">
          <AlertTriangle size={20} className={destructive ? "text-red-400" : "text-amber-400"} />
          {title}
        </div>
        {description && <div className="text-sm leading-6 text-theme-sub">{description}</div>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={loading} onClick={onCancel}>
            {cancelText}
          </Button>
          <Button variant={destructive ? "destructive" : "default"} disabled={loading} onClick={onConfirm}>
            {loading ? "处理中…" : confirmText}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
