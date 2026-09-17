import {
  BookOpenText,
  Database,
  Eye,
  EyeOff,
  Gauge,
  Loader2,
  Quote,
  ShieldCheck,
} from "lucide-react";

import { FormEvent, useEffect, useState } from "react";

import { Link, useNavigate } from "react-router-dom";
import { get, post } from "../api/client";
import { UserSchema, VersionInfoSchema } from "../api/schemas";

import { Button } from "../components/ui/button";

import { Input } from "../components/ui/input";

const FEATURES = [
  { icon: Database, title: "检索增强生成", desc: "基于内部文档的 RAG 问答" },
  { icon: Quote, title: "引用可溯", desc: "每条答案点回原文出处" },
  { icon: Gauge, title: "配额与留痕", desc: "用量可控、操作可审计" },
];

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
  // 应用版本号（单一来源：后端 /api/meta/version ↔ 根 VERSION 文件）
  const [appVersion, setAppVersion] = useState("");
  useEffect(() => {
    get("/meta/version", VersionInfoSchema)
      .then((r) => setAppVersion(r.version))
      .catch(() => setAppVersion(""));
  }, []);

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
      navigate("/login", { replace: true, state: { registered: true } });
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
    <div className="flex min-h-screen bg-theme-deep text-theme-text">
      {/* 左半品牌区：与登录页一致的深墨底 + 网格纹理 + 品牌光晕 */}
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
              上传制度、手册与 FAQ，基于 RAG
              检索增强生成回答，每条答案都可点回原文出处。
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

      {/* 右半表单区 */}
      <div className="flex flex-1 items-center justify-center bg-theme-bg p-6">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dark text-white">
              <BookOpenText size={18} />
            </span>
            <span className="text-lg font-semibold">内知 · KnowledgeQA</span>
          </div>

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
                to="/login"
                className="ml-1 text-brand-light hover:underline"
              >
                去登录
              </Link>
            </p>
          </div>

          <p className="mt-6 text-center text-xs text-theme-sub">
            企业级内部知识库 · 数据不出内网
          </p>
        </div>
      </div>
    </div>
  );
}
