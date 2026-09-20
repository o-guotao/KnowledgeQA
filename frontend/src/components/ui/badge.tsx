import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "bg-brand/15 text-brand-light",
        // 状态色用透明度式（浅亮底在深色主题下是违和的亮盒）：
        // 与站内 banner（bg-*-500/10 + text-*-400）同一套双主题惯用式
        success: "bg-emerald-500/15 text-emerald-400",
        warning: "bg-amber-500/15 text-amber-400",
        destructive: "bg-red-500/15 text-red-400",
        muted: "bg-white/10 text-theme-sub",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
