import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // 注册成功后跳回登录页时带的标记，用于展示绿色提示（仅本次导航有效）
  const justRegistered = (location.state as { registered?: boolean } | null)?.registered === true;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      await login(username.trim(), password);
      navigate("/app", { replace: true });
    } catch (err) {
      console.error("login failed", err);
      setError(err instanceof Error ? err.message : "登录失败");
      setShake(true);
      setTimeout(() => setShake(false), 350);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <div className={`rounded-2xl border border-theme-line bg-theme-card p-8 shadow-card ${shake ? "animate-shake" : ""}`}>
        <h2 className="text-xl font-semibold tracking-tight">登录</h2>
        <p className="mt-1 text-sm text-theme-sub">使用内部账号访问知识库</p>

        {justRegistered && (
          <p role="status" className="mt-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-400">
            注册成功，请登录
          </p>
        )}

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="username" className="text-sm font-medium text-theme-text">用户名</label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              autoComplete="username"
              required
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="password" className="text-sm font-medium text-theme-text">密码</label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                autoComplete="current-password"
                className="pr-10"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "隐藏密码" : "显示密码"}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-theme-sub hover:text-theme-text cursor-pointer"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          {error && (
            <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
              {error}
            </p>
          )}
          <Button type="submit" className="w-full shadow-soft" disabled={loading}>
            {loading && <Loader2 size={16} className="animate-spin" />}
            {loading ? "登录中…" : "登录"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-theme-sub">
          没有账号？
          <Link to="/app/register" className="ml-1 text-brand-light hover:underline">
            去注册
          </Link>
        </p>
      </div>

      <p className="mt-6 text-center text-xs text-theme-sub">企业级内部知识库 · 数据不出内网</p>
    </AuthLayout>
  );
}
