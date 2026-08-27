import { BookOpenText, Loader2 } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
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
    <div className="flex min-h-screen">
      {/* 品牌区 */}
      <div className="hidden flex-1 flex-col justify-between bg-gradient-to-br from-ink via-brand-dark to-brand p-12 text-white lg:flex">
        <div className="flex items-center gap-2 text-lg font-semibold">
          <BookOpenText size={22} />
          内知 · KnowledgeQA
        </div>
        <div className="space-y-4">
          <h1 className="text-3xl font-semibold leading-snug">
            让内部文档
            <br />
            成为可追问的知识
          </h1>
          <p className="max-w-md text-sm leading-relaxed text-white/70">
            上传制度、手册与 FAQ，基于 RAG 检索增强生成回答，每条答案都可点回原文出处。
            流式输出、用量配额、操作留痕，开箱即生产态。
          </p>
        </div>
        <p className="text-xs text-white/40">v0.1.0 · SSE · RAG · pgvector</p>
      </div>

      {/* 表单区 */}
      <div className="flex flex-1 items-center justify-center bg-surface p-6">
        <Card className={`w-full max-w-sm ${shake ? "animate-shake" : ""}`}>
          <CardHeader>
            <CardTitle className="text-xl">登录</CardTitle>
            <p className="text-sm text-muted">使用内部账号访问知识库</p>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="username" className="text-sm font-medium">用户名</label>
                <Input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="password" className="text-sm font-medium">密码</label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 size={16} className="animate-spin" />}
                {loading ? "登录中…" : "登录"}
              </Button>
              <p className="rounded-md bg-brand/5 px-3 py-2 text-xs text-muted">
                演示账号：demo / demo1234（由后端 seed 脚本创建）
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
