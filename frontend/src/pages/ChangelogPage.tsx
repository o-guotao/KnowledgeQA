import { ArrowLeft, History, Tag } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { get } from "../api/client";
import { ChangelogEntrySchema, VersionInfoSchema, type ChangelogEntry } from "../api/schemas";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { ThemeToggle } from "../components/ThemeToggle";

/** 版本与迭代记录：数据来自后端 /api/meta/*（单一来源：根 VERSION 与 CHANGELOG.md）。 */
export function ChangelogPage() {
  const navigate = useNavigate();
  const [version, setVersion] = useState<string>("");
  const [entries, setEntries] = useState<ChangelogEntry[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    get("/meta/version", VersionInfoSchema)
      .then((r) => setVersion(r.version))
      .catch(() => setVersion(""));
    get("/meta/changelog", z.array(ChangelogEntrySchema))
      .then(setEntries)
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"));
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-b from-theme-bg via-theme-bg to-theme-deep px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <header className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" aria-label="返回问答" onClick={() => navigate("/")}>
              <ArrowLeft size={18} />
            </Button>
            <div>
              <p className="text-sm font-medium text-brand">版本</p>
              <h1 className="text-2xl font-semibold tracking-tight text-theme-text">更新日志</h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {version && (
              <Badge variant="success">
                <Tag size={12} className="mr-1" />
                v{version}
              </Badge>
            )}
            <ThemeToggle />
          </div>
        </header>

        {error && <p className="text-sm text-red-400">{error}</p>}

        {!error && entries.length === 0 && (
          <div className="flex flex-col items-center rounded-2xl border border-dashed border-theme-line bg-theme-card/60 px-6 py-16 text-center">
            <History size={22} className="text-theme-sub" />
            <p className="mt-4 text-sm text-theme-sub">暂无迭代记录</p>
          </div>
        )}

        {entries.map((e) => (
          <Card key={e.version}>
            <CardContent className="space-y-4 py-5">
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/15 text-brand-light">
                  <Tag size={15} />
                </span>
                <div>
                  <p className="font-semibold text-theme-text">v{e.version}</p>
                  <p className="text-xs text-theme-sub">{e.date}</p>
                </div>
                {e.version === version && <Badge variant="success">当前版本</Badge>}
              </div>
              {e.groups.map((g) => (
                <div key={g.title}>
                  <p className="text-sm font-medium text-brand-light">{g.title}</p>
                  <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-6 text-theme-sub">
                    {g.items.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
