import { forwardRef } from "react";
import type { TextareaHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "flex min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm",
      "placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:border-brand",
      "disabled:cursor-not-allowed disabled:opacity-50 resize-none transition-shadow",
      className,
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";
