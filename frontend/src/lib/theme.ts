/**
 * 主题切换：深色为默认（保持既有视觉），浅色经 html.light 类切换 CSS 变量。
 * 偏好持久化在 localStorage（非敏感数据）；index.html 内联脚本在首屏前应用，避免闪烁。
 */
export type Theme = "dark" | "light";

const STORAGE_KEY = "web-agent-theme";

export function getTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("light", theme === "light");
}

export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // 隐私模式等场景下 localStorage 不可用：仅本次会话生效
  }
  applyTheme(theme);
}
