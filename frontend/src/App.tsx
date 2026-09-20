import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./auth/AuthContext";
import { IcpFooter } from "./components/IcpFooter";
import { AdminPage } from "./pages/AdminPage";
import { ChangelogPage } from "./pages/ChangelogPage";
import { ChatPage } from "./pages/ChatPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { LoginPage } from "./pages/LoginPage";
import { ModelSettingsPage } from "./pages/ModelSettingsPage";
import { RegisterPage } from "./pages/RegisterPage";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  // 会话恢复中（/auth/me 未返回）先等待，避免刷新瞬间误判未登录闪跳登录页
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        {/* 全站纵向骨架：固定视口高（h-dvh），内容区 flex-1 内部各自滚动，
            页脚恒定可见且不被内容撑跑 —— 否则消息多时整页向下延伸。 */}
        <div className="flex h-dvh flex-col overflow-hidden bg-theme-deep">
          <div className="flex min-h-0 flex-1 flex-col">
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route
                path="/"
                element={
                  <RequireAuth>
                    <ChatPage />
                  </RequireAuth>
                }
              />
              <Route path="/settings/models" element={<RequireAuth><ModelSettingsPage /></RequireAuth>} />
              <Route path="/documents" element={<RequireAuth><DocumentsPage /></RequireAuth>} />
              <Route path="/admin" element={<RequireAuth><AdminPage /></RequireAuth>} />
              <Route path="/changelog" element={<RequireAuth><ChangelogPage /></RequireAuth>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
          <IcpFooter />
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
