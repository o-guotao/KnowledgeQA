import { ChevronDown, LogOut, Settings2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { QuotaBadge } from "./QuotaBadge";

interface UserMenuUser {
  username: string;
  display_name: string;
  role: string;
}

interface UserMenuProps {
  user: UserMenuUser | null;
  onLogout: () => void;
  /** 传入则在菜单内显示本月配额（与聊天页用量刷新联动） */
  quotaRefreshKey?: number;
}

/**
 * 右上角账号菜单：头像（名称首字）+ 名称 + 下拉（账号信息 / 配额 / 账号设置 / 退出登录）。
 * 点击外部或 Escape 关闭。
 */
export function UserMenu({ user, onLogout, quotaRefreshKey }: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const name = user?.display_name || user?.username || "未登录";
  const initial = name.slice(0, 1).toUpperCase();

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        aria-label="账号菜单"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex cursor-pointer items-center gap-2 rounded-full border border-theme-line bg-theme-card py-1 pl-1 pr-3 transition-colors hover:bg-theme-input"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-brand-dark text-xs font-semibold text-white">
          {initial}
        </span>
        <span className="max-w-28 truncate text-sm text-theme-text">{name}</span>
        <ChevronDown size={14} className={`shrink-0 text-theme-sub transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-60 rounded-xl border border-theme-line bg-theme-card p-2 shadow-pop"
        >
          <div className="flex items-center gap-3 border-b border-theme-line px-2 pb-3 pt-1">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-brand-dark text-sm font-semibold text-white">
              {initial}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-theme-text">{name}</p>
              <p className="truncate text-xs text-theme-sub">
                @{user?.username} · {user?.role}
              </p>
              {quotaRefreshKey !== undefined && (
                <div className="mt-1.5">
                  <QuotaBadge refreshKey={quotaRefreshKey} />
                </div>
              )}
            </div>
          </div>
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false);
              navigate("/settings/models");
            }}
            className="mt-1 flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-sm text-theme-text transition-colors hover:bg-white/5"
          >
            <Settings2 size={15} />
            账号设置
          </button>
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
            className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/10"
          >
            <LogOut size={15} />
            退出登录
          </button>
        </div>
      )}
    </div>
  );
}
