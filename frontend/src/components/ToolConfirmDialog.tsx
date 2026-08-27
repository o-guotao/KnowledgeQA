import { ShieldAlert } from "lucide-react";
import { useState } from "react";

import { post } from "../api/client";
import { ToolConfirmResponseSchema, type ToolCallEventSchema } from "../api/schemas";
import type { z } from "zod";
import { Button } from "./ui/button";
import { Dialog } from "./ui/dialog";

type ToolCallEvent = z.infer<typeof ToolCallEventSchema>;

interface ToolConfirmDialogProps {
  toolCall: ToolCallEvent | null;
  onResolved: (result: string, approved: boolean) => void;
  onClose: () => void;
}

/** 工具确认弹窗：模型发起的敏感工具调用，必须人工确认/拒绝后才执行 */
export function ToolConfirmDialog({ toolCall, onResolved, onClose }: ToolConfirmDialogProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (approved: boolean) => {
    if (!toolCall) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await post(
        "/tools/confirm",
        { message_id: toolCall.message_id, approved },
        ToolConfirmResponseSchema,
      );
      onResolved(res.result, approved);
    } catch (err) {
      console.error("tool confirm failed", err);
      setError("操作提交失败，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={toolCall !== null} onClose={onClose}>
      {toolCall && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-base font-semibold">
            <ShieldAlert className="text-amber-500" size={20} />
            工具调用待确认
          </div>
          <p className="text-sm text-slate-600">
            助手请求执行敏感操作 <code className="rounded bg-slate-100 px-1">{toolCall.name}</code>
            ，确认后才会真正执行，操作将全程留痕。
          </p>
          <pre className="max-h-48 overflow-auto scrollbar-thin rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
            {JSON.stringify(toolCall.args, null, 2)}
          </pre>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={submitting} onClick={() => decide(false)}>
              拒绝
            </Button>
            <Button variant="destructive" disabled={submitting} onClick={() => decide(true)}>
              {submitting ? "提交中…" : "确认执行"}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
