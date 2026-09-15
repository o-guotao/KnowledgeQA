import { Moon, Sun } from "lucide-react";
import { useState } from "react";

import { getTheme, setTheme, type Theme } from "../lib/theme";

/** 主题切换按钮：太阳=当前深色（点击切浅色），月亮=当前浅色（点击切深色） */
export function ThemeToggle() {
  const [theme, setThemeState] = useState<Theme>(() => getTheme());

  const toggle = () => {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    setThemeState(next);
  };

  const label = theme === "light" ? "切换到深色主题" : "切换到浅色主题";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className="rounded-lg p-2 text-theme-sub transition-colors hover:bg-white/10 hover:text-theme-text cursor-pointer"
    >
      {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
    </button>
  );
}
