import { SendHorizonal, Square } from "lucide-react";
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
    <div className="border-t border-slate-200 bg-white/80 backdrop-blur-xl p-4">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={disabled ? "本月配额已用尽，无法继续提问" : "输入问题，Enter 发送，Shift+Enter 换行"}
          disabled={disabled}
          rows={2}
          className="flex-1"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {streaming ? (
          <Button variant="destructive" size="icon" onClick={onStop} aria-label="停止生成">
            <Square size={16} />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={submit}
            disabled={disabled || !value.trim()}
            aria-label="发送"
          >
            <SendHorizonal size={16} />
          </Button>
        )}
      </div>
    </div>
  );
}
