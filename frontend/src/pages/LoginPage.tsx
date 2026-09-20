import { BookOpenText, Database, Eye, EyeOff, Gauge, Loader2, Quote, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { get } from "../api/client";
import { VersionInfoSchema } from "../api/schemas";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

const FEATURES = [
  { icon: Database, title: "检索增强生成", desc: "基于内部文档的 RAG 问答" },
  { icon: Quote, title: "引用可溯", desc: "每条答案点回原文出处" },
  { icon: Gauge, title: "配额与留痕", desc: "用量可控、操作可审计" },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // 注册成功后跳回登录页时带的标记，用于展示绿色提示（仅本次导航有效）
  const justRegistered = (location.state as { registered?: boolean } | null)?.registered === true;
  // 应用版本号（单一来源：后端 /api/meta/version ↔ 根 VERSION 文件），不再硬编码
  const [appVersion, setAppVersion] = useState("");
  useEffect(() => {
    get("/meta/version", VersionInfoSchema)
      .then((r) => setAppVersion(r.version))
      .catch(() => setAppVersion(""));
  }, []);
  const [username, setUsername] = useState("demo");
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
      navigate("/", { replace: true });
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
    <div className="flex min-h-0 flex-1 overflow-y-auto bg-theme-deep text-theme-text">
      {/* 左半品牌区：沉稳深墨底 + 网格纹理 + 品牌光晕点缀（克制配色） */}
      <div className="relative hidden flex-1 flex-col justify-between overflow-hidden p-12 lg:flex">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-theme-deep via-theme-bg to-theme-deep" />
        <div className="login-grid pointer-events-none absolute inset-0 opacity-[0.15]" />
        <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-brand/20 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 right-0 h-80 w-80 rounded-full bg-brand/10 blur-3xl" />

        <div className="relative flex items-center gap-2 text-lg font-semibold">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dark text-white shadow-pop">
            <BookOpenText size={18} />
          </span>
          内知 · KnowledgeQA
        </div>

        <div className="relative space-y-8">
          <div className="space-y-4">
            <h1 className="text-4xl font-semibold leading-tight tracking-tight">
              让内部文档
              <br />
              成为可追问的知识
            </h1>
            <p className="max-w-md text-sm leading-relaxed text-theme-sub">
              上传制度、手册与 FAQ，基于 RAG 检索增强生成回答，每条答案都可点回原文出处。
            </p>
          </div>
          <ul className="space-y-4">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-theme-line bg-theme-card text-brand-light">
                  <f.icon size={16} />
                </span>
                <div>
                  <p className="text-sm font-medium">{f.title}</p>
                  <p className="text-xs text-theme-sub">{f.desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex items-center gap-2 text-xs text-theme-sub">
          <ShieldCheck size={14} className="text-emerald-400" />
          数据仅在企业内部可见 · {appVersion ? `v${appVersion} · ` : ""}SSE · RAG · pgvector
        </div>
      </div>

      {/* 右半表单区：精细边框卡片 + 渐入动效 + 完整状态 */}
      <div className="flex flex-1 items-center justify-center bg-theme-bg p-6">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dark text-white">
              <BookOpenText size={18} />
            </span>
            <span className="text-lg font-semibold">内知 · KnowledgeQA</span>
          </div>

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
              <Link to="/register" className="ml-1 text-brand-light hover:underline">
                去注册
              </Link>
            </p>
          </div>

          <p className="mt-6 text-center text-xs text-theme-sub">企业级内部知识库 · 数据不出内网</p>
        </div>
      </div>
    </div>
  );
}
