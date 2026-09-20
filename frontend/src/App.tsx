import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { IcpFooter } from "./components/IcpFooter";
import { AdminPage } from "./pages/AdminPage";
import { ChangelogPage } from "./pages/ChangelogPage";
import { ChatPage } from "./pages/ChatPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelSettingsPage } from "./pages/ModelSettingsPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ShowcasePage } from "./showcase/ShowcasePage";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  // 会话恢复中（/auth/me 未返回）先等待，避免刷新瞬间误判未登录闪跳登录页
  if (loading) return null;
  if (!user) return <Navigate to="/app/login" replace />;
  return <>{children}</>;
}

/** 路由外壳：备案页脚只在应用侧渲染。
 *  门面首页（/）底部是 HUD 滑轨 + 时间码 + 暂停按钮（fixed bottom，z-index 7），
 *  备案页脚同为 fixed bottom，两者矩形实测相交 —— 首页不渲染，避免压住 HUD 与卡片。 */
function Shell() {
  const { pathname } = useLocation();
  const isShowcase = pathname === "/";

  return (
    <>
      <Routes>
        {/* 门面首页：滚动叙事作品集（公开，作品预览节内嵌 /app） */}
        <Route path="/" element={<ShowcasePage />} />

        {/* KnowledgeQA 应用：/app 前缀 */}
        <Route path="/app/login" element={<LoginPage />} />
        <Route path="/app/register" element={<RegisterPage />} />
        <Route
          path="/app"
          element={
            <RequireAuth>
              <ChatPage />
            </RequireAuth>
          }
        />
        <Route path="/app/settings/models" element={<RequireAuth><ModelSettingsPage /></RequireAuth>} />
        <Route path="/app/documents" element={<RequireAuth><DocumentsPage /></RequireAuth>} />
        <Route path="/app/admin" element={<RequireAuth><AdminPage /></RequireAuth>} />
        <Route path="/app/changelog" element={<RequireAuth><ChangelogPage /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Routes>
      {isShowcase ? null : <IcpFooter />}
    </>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </AuthProvider>
  );
}
