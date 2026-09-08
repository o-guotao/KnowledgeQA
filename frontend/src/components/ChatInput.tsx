import { Send, Square } from "lucide-react";
import { useState } from "react";

import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

interface ChatInputProps {
  streaming: boolean;
  disabled?: boolean;
  onSend: (content: string) => void;
  onStop: () => void;
}

export function ChatInput({ streaming, disabled, onSend, onStop }: ChatInputProps) {
  const [value, setValue] = useState("");

  const submit = () => {
    const content = value.trim();
    if (!content || streaming || disabled) return;
    onSend(content);
    setValue("");
  };

  return (
    <div className="border-t border-theme-line bg-theme-deep/80 px-4 py-4 backdrop-blur-xl sm:px-6">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-2xl border border-theme-line bg-theme-input p-2 text-theme-text shadow-card transition-all focus-within:border-brand/50 focus-within:shadow-pop">
          <Textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={disabled ? "本月配额已用尽，无法继续提问" : "输入问题，Enter 发送，Shift+Enter 换行"}
            disabled={disabled}
            rows={2}
            className="flex-1 border-0 bg-transparent shadow-none focus-visible:border-transparent focus-visible:ring-0"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {streaming ? (
            <Button variant="destructive" size="icon" className="rounded-xl shadow-soft" onClick={onStop} aria-label="停止生成">
              <Square size={16} />
            </Button>
          ) : (
            <Button
              size="icon"
              className="rounded-xl shadow-soft"
              onClick={submit}
              disabled={disabled || !value.trim()}
              aria-label="发送"
            >
              <Send size={16} />
            </Button>
          )}
        </div>
      </div>
      <p className="mx-auto mt-2 max-w-3xl px-1 text-center text-[11px] text-slate-500">内容仅用于本次知识库问答；回答可能存在偏差，请核对引用原文。</p>
    </div>
  );
}
