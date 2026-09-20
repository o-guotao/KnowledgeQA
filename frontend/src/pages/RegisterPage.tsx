import { Eye, EyeOff, Loader2 } from "lucide-react";

import { FormEvent, useState } from "react";

import { Link, useNavigate } from "react-router-dom";
import { post } from "../api/client";
import { UserSchema } from "../api/schemas";

import { AuthLayout } from "../components/AuthLayout";
import { Button } from "../components/ui/button";

import { Input } from "../components/ui/input";

export function RegisterPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    if (password.length < 8) {
      setError("密码至少 8 位");
      return;
    }
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await post(
        "/auth/register",
        {
          username: username.trim(),
          password,
          display_name: displayName.trim(),
        },
        UserSchema,
      );
      navigate("/app/login", { replace: true, state: { registered: true } });
    } catch (err) {
      console.error("register failed", err);
      setError(err instanceof Error ? err.message : "注册失败");
      setShake(true);
      setTimeout(() => setShake(false), 350);
    } finally {
      setLoading(false);
    }
  };
  return (
    <AuthLayout>
      <div
        className={`rounded-2xl border border-theme-line bg-theme-card p-8 shadow-card ${shake ? "animate-shake" : ""}`}
      >
        <h2 className="text-xl font-semibold tracking-tight">注册</h2>
        <p className="mt-1 text-sm text-theme-sub">
          创建内部账号，注册后请登录
        </p>

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="username"
              className="text-sm font-medium text-theme-text"
            >
              用户名
            </label>
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
            <label
              htmlFor="displayName"
              className="text-sm font-medium text-theme-text"
            >
              显示名{" "}
              <span className="text-xs font-normal text-theme-sub">
                （可选）
              </span>
            </label>
            <Input
              id="displayName"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="用于界面展示的名字"
              autoComplete="nickname"
            />
          </div>
          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="text-sm font-medium text-theme-text"
            >
              密码
            </label>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="至少 8 位"
                autoComplete="new-password"
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
          <div className="space-y-1.5">
            <label
              htmlFor="confirmPassword"
              className="text-sm font-medium text-theme-text"
            >
              确认密码
            </label>
            <Input
              id="confirmPassword"
              type={showPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="再次输入密码"
              autoComplete="new-password"
              required
            />
          </div>
          {error && (
            <p
              role="alert"
              className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400"
            >
              {error}
            </p>
          )}
          <Button
            type="submit"
            className="w-full shadow-soft"
            disabled={loading}
          >
            {loading && <Loader2 size={16} className="animate-spin" />}
            {loading ? "注册中…" : "注册"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-theme-sub">
          已有账号？
          <Link
            to="/app/login"
            className="ml-1 text-brand-light hover:underline"
          >
            去登录
          </Link>
        </p>
      </div>

      <p className="mt-6 text-center text-xs text-theme-sub">
        企业级内部知识库 · 数据不出内网
      </p>
    </AuthLayout>
  );
}
