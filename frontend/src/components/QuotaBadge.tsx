import { Coins } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { get } from "../api/client";
import { QuotaSchema, type Quota } from "../api/schemas";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** 配额角标：展示本月 token 用量与费用，30s 轮询 + 暴露手动刷新 */
export function QuotaBadge({ refreshKey }: { refreshKey: number }) {
  const [quota, setQuota] = useState<Quota | null>(null);

  const refresh = useCallback(() => {
    get("/quotas/me", QuotaSchema)
      .then(setQuota)
      .catch((err) => console.error("quota fetch failed", err));
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30_000);
    return () => clearInterval(timer);
  }, [refresh, refreshKey]);

  if (!quota) return null;
  const ratio = quota.limit_tokens > 0 ? quota.total_tokens / quota.limit_tokens : 0;
  const variant = quota.exhausted ? "destructive" : ratio > 0.8 ? "warning" : "default";

  return (
    <Badge
      variant={variant}
      title={`本月 ${quota.period}：输入 ${quota.prompt_tokens} / 输出 ${quota.completion_tokens} tokens，累计 ¥${quota.cost_cny.toFixed(4)}`}
      className={cn("cursor-default select-none")}
    >
      <Coins size={12} />
      {formatTokens(quota.total_tokens)}/{formatTokens(quota.limit_tokens)}
      <span className="opacity-70">¥{quota.cost_cny.toFixed(4)}</span>
    </Badge>
  );
}
