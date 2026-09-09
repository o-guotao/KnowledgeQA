import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { z } from "zod";

import { get, post, setToken } from "../api/client";
import { TokenResponseSchema, UserSchema, type User } from "../api/schemas";

interface AuthState {
  user: User | null;
  /** 首次挂载正在用 Cookie 调 /auth/me 恢复会话 */
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // 刷新后内存 token 已丢失：凭 HttpOnly Cookie 调 /auth/me 恢复会话
  useEffect(() => {
    get("/auth/me", UserSchema)
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  // 任意请求 401 时清空用户态（路由守卫据此跳回登录页）
  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await post("/auth/login", { username, password }, TokenResponseSchema);
    // 登录响应已写入 HttpOnly Cookie；内存 token 仅供跨域 Bearer 场景使用
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const logout = useCallback(() => {
    // HttpOnly Cookie 只能由服务端清除；失败也照常清空本地态
    void post("/auth/logout", {}, z.unknown()).catch(() => undefined);
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}
