/**
 * 文档管理页视图偏好：列表 / 导图 二选一（两者占同一块内容区，互斥切换）。
 * 持久化在 localStorage（非敏感数据），与主题偏好同一套做法；默认列表。
 */
export type DocView = "list" | "map";

const STORAGE_KEY = "web-agent-doc-view";

export function getDocView(): DocView {
  try {
    return localStorage.getItem(STORAGE_KEY) === "map" ? "map" : "list";
  } catch {
    return "list";
  }
}

export function setDocView(view: DocView): void {
  try {
    localStorage.setItem(STORAGE_KEY, view);
  } catch {
    // 隐私模式等场景下 localStorage 不可用：仅本次会话生效
  }
}
