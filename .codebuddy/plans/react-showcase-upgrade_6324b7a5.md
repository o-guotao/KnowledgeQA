---
name: react-showcase-upgrade
overview: 将 frontend/public/showcase 的滚动叙事作品集用 React+TS 重写为门面首页（/），现有 KnowledgeQA 全部路由迁移到 /app 前缀并在「作品预览」节以 iframe + 三卡片接入；叙事文案保留设计师版本，main.mp4 缺失时用静态图+滚动视差替代（保留视频接口），重写验证后删除原静态版。
design:
  architecture:
    framework: react
  styleKeywords:
    - 电影化滚动叙事
    - 编辑排版（Editorial）
    - 青灰暗调摄影底
    - HUD 工业风
    - Impact 风格大写标题
    - 互斥淡入淡出
    - 鼠标擦洗交互
    - reduced-motion 降级
  fontSystem:
    fontFamily: system-ui
    heading:
      size: clamp(48px, 9vw, 128px)
      weight: 900
    subheading:
      size: clamp(20px, 3vw, 32px)
      weight: 700
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#2E362F"
      - "#3A4438"
    background:
      - "#2E362F"
      - "#1F251C"
    text:
      - "#EDEAE3"
      - "#B9B5A9"
    functional:
      - "#D9772B"
      - "#E8B25C"
todos:
  - id: foundation-math-assets
    content: 迁移媒体素材（git mv public/showcase/media → public/media），创建 showcaseMath.ts（移植全部纯函数 + typed CONFIG）与 showcase.css（改 /media/ 路径 + 视差变量）
    status: completed
  - id: interaction-hooks
    content: 实现 useScrollProgress（scrollDirty/阻尼 seek/pendingSeek/时长重算）与 useIntroScrub（跟手/回正/tiltY/iOS unlock），保留原性能纪律（ref 直写、值没变不写）
    status: completed
    dependencies:
      - foundation-math-assets
  - id: showcase-components
    content: 实现 Backdrop/StageVideo/Topbar/Hero/CopyLayer/Hud/Ripple 展示组件，节切换与背景同键同刻
    status: completed
    dependencies:
      - interaction-hooks
  - id: folder-workpreview
    content: 实现 Folder 面板（封面→真 DOM 三卡片内页、ESC/空白栏收起、焦点管理）与 WorkPreview（iframe 嵌 /app + 三张可点卡片，RAG 跳 /app）
    status: completed
    dependencies:
      - interaction-hooks
  - id: showcase-page-assembly
    content: 装配 ShowcasePage（rAF 主循环、layoutTrack、首帧就位、视差降级）并接入路由 /；用 [skill:ui-ux-pro-max] 审查视觉与动效规格
    status: completed
    dependencies:
      - showcase-components
      - folder-workpreview
  - id: app-route-migration
    content: 迁移应用路由到 /app 前缀，全量 grep 更新站内跳转（RequireAuth/Login/Register/各页 Link），登录后默认进 /app
    status: completed
    dependencies:
      - showcase-page-assembly
  - id: verify-cleanup
    content: tsc + vite build 通过后，用 [skill:playwright-cli] 实测 showcase 五节叙事与 /app 全路由回归，验证通过后删除 public/showcase 并更新 CHANGELOG
    status: completed
    dependencies:
      - app-route-migration
---

## 产品概述

将现有 `frontend/public/showcase`（滚动叙事作品集静态页）用 React + TypeScript 重写，作为整个前端的门面首页（`/`）；现有 KnowledgeQA 应用（问答/文档/管理/模型设置/更新日志）整体迁移至 `/app` 前缀，并作为「作品」接入 showcase 的「作品预览」节。视觉与交互效果全面升级为 showcase 的电影化滚动叙事风格。

## 核心功能

- **门面首页（/）**：五节滚动叙事——初次见遇（首屏鼠标擦洗视线跟踪）/ 个人简历 / 作品文件夹（开合面板）/ 作品预览 / 无限可能；滚动进度驱动画面与文案互斥切换，HUD 进度条 + 分节刻度 + 时间码 + 暂停互动
- **作品预览节接入真实应用**：iframe 实时内嵌 `/app`（未登录显示登录页，所见即所得）+ 三张可点卡片（card-rag/web/agent），RAG 卡跳转 `/app`，另两张占位待补
- **作品文件夹内页真 DOM 化**：封面（folder.png）→ 翻开为三张真卡片（可选中、可搜索的文字 + card-rag/web/agent.png 配图），键盘可达（开合/ESC/空白栏收起）
- **无视频叙事降级**：main.mp4 缺失时以静态分镜图 + 滚动驱动视差位移呈现，保留视频接口（放入 main.mp4 即自动接管）
- **应用路由迁移**：登录/注册成功默认进 `/app`；站内全部跳转改 `/app` 前缀；旧静态 showcase 验证后删除，媒体素材迁至 `public/media`
- **可访问性保留**：reduced-motion 与触屏降级、aria 属性、键盘可达、sr-only 文本

## Tech Stack

- 前端框架：现有 Vite + React + TypeScript（复用，不引入新依赖）
- 样式：showcase 原生 CSS 体系（881 行自成一体，原样迁入并改媒体路径，不强行 Tailwind 化）；应用侧继续 Tailwind
- 路由：react-router-dom 现有 BrowserRouter

## Implementation Approach

核心策略：**逐层等价移植**而非重造——showcase.js（865 行）的纯函数区无 DOM 依赖，直接 TS 化；交互纪律（不从 currentTime 读回控制量、值没变不写 DOM、seek 就绪前挂起）在 React 版完整保留，高频值（进度/时间码/滑轨）走 **ref + 直接写 style**，绝不进 React state 避免 rAF 循环触发 rerender。

关键决策：

1. **状态归属**：滚动进度、applied/introApplied 等全部为 ref 内 mutable 状态；React state 只承载低频互斥态（当前节序号、文件夹开合、暂停互动）
2. **视差降级**：无 main.mp4 时按 p 给 scene 层写 CSS 变量（scale/translate 缓动），`<video data-role="main">` 与全部 seek 逻辑保留
3. **iframe 同源**：`/` 与 `/app` 同源，HttpOnly Cookie 自动携带，无需 CORS 改动

## Directory Structure

```
frontend/
├── public/
│   ├── media/                          # [NEW] git mv 自 public/showcase/media（10 个媒体文件，含 intro-loop.mp4）
│   └── showcase/                       # [DELETE] 验证通过后整目录删除
├── src/
│   ├── showcase/                       # [NEW] React+TS 重写区
│   │   ├── ShowcasePage.tsx            # 容器：装配各层 + rAF 主循环 + 启动时序（layoutTrack/首帧就位）
│   │   ├── showcaseMath.ts             # 移植全部纯函数（typed）：segmentOf/progressToTime/beatIndexAt/formatTime/sectionTicks/sectionSpans/sectionTarget/gazeLabel/sceneDropY/mouseToIntroTime/shouldWriteIntro + CONFIG 常量
│   │   ├── showcase.css                # 原 881 行 CSS 迁入，媒体路径改 /media/，补视差 transform 变量
│   │   ├── useScrollProgress.ts        # scrollDirty 标记（scroll/resize/orientationchange/ResizeObserver）、main 阻尼 seek、pendingSeek 挂起、loadedmetadata 重算
│   │   ├── useIntroScrub.ts            # 首屏鼠标擦洗：精确指针门控、跟手/回正分支、tiltY、iOS unlock
│   │   └── components/
│   │       ├── Backdrop.tsx            # 恒定底图 + 按节 scene 层（与 CopyLayer 同键同刻切换）+ data-drop 下坠层
│   │       ├── StageVideo.tsx          # intro/main 视频台：poster 回退、is-missing、canplay 补写
│   │       ├── Topbar.tsx              # logo + 五节导航（落点 sectionTarget 现算，data-en 单源进 TS 常量）
│   │       ├── Hero.tsx                # 首屏四块文案 + 八向视线读数
│   │       ├── CopyLayer.tsx           # data-copy 互斥淡入淡出
│   │       ├── Folder.tsx              # 作品文件夹：封面/内页按钮、空白栏/ESC 收起、焦点管理；内页真 DOM 三卡片（card-rag/web/agent.png + 可选中正文）
│   │       ├── WorkPreview.tsx         # iframe src="/app" + 三张可点卡片（RAG 跳 /app，web/agent 占位禁用）
│   │       ├── Hud.tsx                 # 滚动提示 + 刻度滑轨 + 时间码 + 暂停互动
│   │       └── Ripple.tsx              # 鼠标波纹画布（reduced-motion/触屏不创建）
│   ├── App.tsx                         # [MODIFY] / → ShowcasePage（公开）；/app/login、/app、/app/settings/models、/app/documents、/app/admin、/app/changelog（RequireAuth 不变）；* → /app
│   └── pages/
│       ├── LoginPage.tsx               # [MODIFY] 登录成功 navigate("/app")
│       ├── RegisterPage.tsx            # [MODIFY] 同上
│       ├── ChatPage.tsx                # [MODIFY] 侧栏导航等站内跳转加 /app 前缀
│       ├── DocumentsPage.tsx           # [MODIFY] 「返回问答」等跳转加前缀
│       ├── AdminPage.tsx              # [MODIFY] 跳转加前缀
│       ├── ModelSettingsPage.tsx      # [MODIFY] 跳转加前缀
│       └── ChangelogPage.tsx          # [MODIFY] 跳转加前缀
└── CHANGELOG.md                        # [MODIFY] [未发布] 补条目
```

## Implementation Notes

- **实施时全量 grep** `navigate(`/`<Link`/`to="/` 核对每个跳转点（含 RequireAuth 的 `/login` 重定向），漏一处即死链
- **性能红线**：rAF 循环内 setState 会每帧 rerender 整页——进度/滑轨/时间码/下坠位移全部 ref 直写 style（保留原「值没变不写」纪律，备忘键取真正写入的字符串）
- 滚动容器高度 = duration×100vh 在 mount 后设置；main.mp4 缺失时用 fallbackDuration，页面仍可滚动叙事
- 滚动叙事主键 copyKey 与背景 scene 键同一刻切换，避免「文案换了背景没换」的中间帧
- 原展示页脚（IcpFooter）不进 showcase（有独立 topbar/tagline 体系）；`/app` 内保持不变

## 设计方案

以现有 showcase 的电影化滚动叙事为基准做 React 化重写，视觉体系完全沿用原设计（青灰暗调 + 分镜摄影 + 编辑排版 + HUD 工业风），新增部分（作品预览 iframe 框、三张作品卡片、文件夹真 DOM 内页）在同一语言下设计。

页面结构（单页滚动叙事，五节）：

- 顶部栏：logo「Biaoge.」左 / 五节导航中 / 署名右，滚动时固定
- 背景层：恒定底图 + 按节切换分镜图（无限可能节带下坠入画）；无视频时叠加滚动视差
- 首屏：主标题 DESIGN WITH FEELING + 右栏 A CURIOUS MIND + 左下署名 + HELLO YOU 视线读数（鼠标驱动）
- 个人简历：左位眉题 + DESIGN. TEACH. BUILD.
- 作品文件夹：整屏面板，合着的橙色文件夹封面 → 翻开三张真 DOM 作品卡片
- 作品预览：顶部位 PREVIEW 文案 + iframe 实时预览 + 三卡片
- 底部 HUD：SCROLL TO EXPLORE + 分节刻度滑轨 + 时间码 + 暂停互动
- 全局：鼠标波纹层（光标细亮环，点击扩散）

## Agent Extensions

### Skill

- **ui-ux-pro-max**
- Purpose: 审查并打磨 showcase React 版的视觉细节与动效规格（WorkPreview 三卡片布局、文件夹真 DOM 内页、视差缓动曲线、HUD 刻度对齐），确保重写不降低原设计质感
- Expected outcome: 新增组件符合原设计的编辑排版与工业 HUD 语言，动效参数（缓动/时长/淡入节奏）有依据并输出可执行规格
- **playwright-cli**
- Purpose: 浏览器实测重写后的 showcase（五节滚动、首屏擦洗、文件夹开合、iframe 加载 /app、卡片跳转）与 /app 路由回归（登录→各页跳转）
- Expected outcome: 全部交互路径通过截图/流程验证，无死链、无白屏、无控制台错误