import { AlertCircle, RotateCcw } from "lucide-react";

import { Button } from "./ui/button";

interface ErrorCardProps {
  message: string;
  traceId?: string;
  onRetry?: () => void;
}

/** 失败态内联卡片：红色提示 + 可选重试 + traceId 展示 */
export function ErrorCard({ message, traceId, onRetry }: ErrorCardProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-3 animate-fade-up">
      <AlertCircle size={18} className="mt-0.5 shrink-0 text-red-600" />
      <div className="flex-1 space-y-1">
        <p className="text-sm text-red-700">{message}</p>
        {traceId && <p className="text-xs text-red-400">traceId: {traceId}</p>}
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="shrink-0">
          <RotateCcw size={14} />
          重试
        </Button>
      )}
    </div>
  );
}
