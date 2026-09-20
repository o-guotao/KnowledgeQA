import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "../lib/utils";

interface CopyButtonProps {
  text: string;
  size?: number;
  label?: string;
  className?: string;
}

/** 一键复制按钮：复制成功后切换为对勾 1.5s 再复原。
 * 剪贴板 API 不可用（http 非安全上下文等）时降级 execCommand。 */
export function CopyButton({ text, size = 14, label = "复制", className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const copy = async () => {
    if (!text) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // 剪贴板权限被拒等场景静默失败，不打断交互
    }
  };

  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => void copy()}
      className={cn(
        "cursor-pointer rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-theme-text",
        className,
      )}
    >
      {copied ? <Check size={size} className="text-green-600" /> : <Copy size={size} />}
    </button>
  );
}
