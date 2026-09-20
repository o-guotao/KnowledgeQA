import { BookOpenText, Database, Gauge, Quote, ShieldCheck } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { get } from "../api/client";
import { VersionInfoSchema } from "../api/schemas";

const FEATURES = [
  { icon: Database, title: "检索增强生成", desc: "基于内部文档的 RAG 问答" },
  { icon: Quote, title: "引用可溯", desc: "每条答案点回原文出处" },
  { icon: Gauge, title: "配额与留痕", desc: "用量可控、操作可审计" },
];

/** 登录/注册共用外壳：左品牌区（lg 起）+ 移动端 logo + 右侧表单容器。
 *  此前两页整块复制约 80 行品牌区/特性列表/版本号逻辑，现收拢到一处。 */
export function AuthLayout({ children }: { children: ReactNode }) {
  // 应用版本号（单一来源：后端 /api/meta/version ↔ 根 VERSION 文件），不再硬编码
  const [appVersion, setAppVersion] = useState("");
  useEffect(() => {
    get("/meta/version", VersionInfoSchema)
      .then((r) => setAppVersion(r.version))
      .catch(() => setAppVersion(""));
  }, []);

  return (
    <div className="flex min-h-screen bg-theme-deep text-theme-text">
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

      {/* 右半表单区：精细边框卡片 + 渐入动效（卡片内容与状态由各页注入） */}
      <div className="flex flex-1 items-center justify-center bg-theme-bg p-6">
        <div className="w-full max-w-sm animate-fade-up">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dark text-white">
              <BookOpenText size={18} />
            </span>
            <span className="text-lg font-semibold">内知 · KnowledgeQA</span>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}
