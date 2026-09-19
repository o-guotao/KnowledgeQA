# implement.md — 执行计划

> **环境铁律**：本机 Bash 命令**不能含任何非 ASCII 字符**（中文、全角符号一律 exit 127）。
> 所有中文内容用 Write / Edit 工具落盘，命令行只走 ASCII。
> 踩过两次：一次是 `task.py create "滚动叙事…"`，一次是命令里带了个中文的 grep 词。

---

## 步骤

### 1. 建目录 + 移动素材 ✅

```bash
mkdir -p frontend/public/showcase/media
mv frontend/assets/start.jpeg    frontend/public/showcase/media/intro-loop.jpeg
mv frontend/assets/computer.jpeg frontend/public/showcase/media/beat-1.jpeg
mv frontend/assets/card.jpeg     frontend/public/showcase/media/beat-2.jpeg
mv frontend/assets/end.jpeg      frontend/public/showcase/media/beat-3.jpeg
```

- 原本是**移动**而非复制，避免仓库存两份约 2MB。`frontend/assets/示例.jpg` 保持不动（排版参考，运行时不使用）。

### 1b. 派生全站背景 ✅

```bash
python "C:/Users/admin/AppData/Local/Temp/make_wall2.py"
```

从 `beat-1.jpeg` 裁 `(0, 60, 1300, 790)` → 1300×730（约 16:9），`GaussianBlur(1.2)`，`quality=88`，输出 `media/bg-wall.jpeg`（68KB）。

**为什么要裁**：四张分镜都把人物画在右侧，直接拿任一张当背景会与 main 视频里的人物**重影**。裁出的净墙面区正好左暗右亮，与左侧文案天然形成对比。这是本任务**唯一新增**的图片资源。

### 1c. 首屏视频到位 ✅

第 2 轮期间 `media/video.mp4` 落地（1.5MB / 10.08s / 1280×720 / H.264 avc1 + AAC），非本人放入。经用户确认属**首屏**槽位，更名为 `media/intro-loop.mp4`：

```bash
cd frontend/public/showcase/media && mv video.mp4 intro-loop.mp4
```

**零代码改动即生效** —— `index.html` 里首屏本来就指向这个文件名，这正是「把 mp4 丢进 `media/` 就生效」的设计目的。

用 `probe_mp4.py` 解析 box 结构拿到时长/尺寸（本机无 ffmpeg，`imageio` 无 ffmpeg 后端，解不出画面）。

### 2. 写 `index.html` ✅

- **两个** `<video>`（intro / main），`muted playsinline webkit-playsinline preload="auto"`；`src` 指向 `media/*.mp4`
- outro 段**无 `<video>`**，只有一个 `.stage__poster` 静态图（用户决定）
- main 的 `<video>` **不加 `autoplay`**，且**不加 poster**（缺失时要露出 `.backdrop`）
- intro 保留 `autoplay loop` 作**无 JS / 触屏兜底**；JS 进擦洗模式时会摘掉
- `.backdrop`（z 0）+ `.scrim`（z 3）两个独立层
- 4 个 `.copy` 块，各带 `data-pos`（intro/0=`left`、1=`top`、2=`bottom`）
- `<script src="showcase.js">` —— **传统脚本，不要 `type="module"`**（`file://` 下会被 CORS 拦截）

### 3. 写 `showcase.css` ✅

- `:root` 设计令牌（PRD §4.1 色板 / design.md §9）
- `.stage` / `.backdrop` / `.scrim` / `.copy-layer` 一律 `position: fixed`，靠 z-index 分层
- `.stage__inner` 承载 `transform`，**`.stage` 本身绝不能有 `transform` / `filter` / `will-change`**
- 段间切换走 `.is-active` class，`transition: opacity .5s`；隐藏侧 `visibility` 延迟 `--fade` 生效，显示侧立即
- `.copy[data-pos="left|top|bottom"]` 三种落位映射
- 展示体字体栈**窄面排在宽面前**：Impact(≈0.45em/字符) 必须在 "Arial Black"(≈0.72) 之前，否则没装窄面的系统上 `SCROLLING.` 会横向溢出；再叠 `overflow-wrap: break-word` 兜底
- `@media (max-width: 720px)` 双栏堆叠为单列
- `@media (prefers-reduced-motion: reduce)` 关掉动效与 `.stage__inner` 缩放

### 4. 写 `showcase.js` ✅

按 design.md 实现：

- 顶部 `CONFIG`：`fallbackDuration / beatCuts / introAt / outroAt / seekDeadzone / ease / maxStep / intro{...}`
- `init()` 内**全部** DOM 访问；顶层只放纯函数与 `CONFIG`
- 尾部双环境守卫：IIFE 里 `if (typeof document !== 'undefined') { init(); return; }`，否则挂 `module.exports` **并** `globalThis.__showcase`
- 单 rAF 循环内完成：读进度（仅 dirty 时）→ 两路阻尼 seek → 写 `.is-active` → 文案 → HUD
- `error` 事件 → `.is-missing`
- iOS 点火：首个手势里 `main.play().then(() => main.pause())`；**擦洗模式下不点火 intro**，否则会把它误播起来

### 4b. v3 修订（第 3 轮需求）✅

需求原文：「滚轮触发离开首屏后，鼠标将停止对人物视线的控制；表情回到初始状态，再衔接下一段人物动画。」

v2 的做法是**一离开首屏就停写** `intro.currentTime`。这满足「停止控制」，但不满足「回到初始状态」—— 人物会**僵在鼠标最后指到的朝向上**渐渐淡出，观众看到的是半转头的残影接下一段。

四处改动：

1. **回正（`showcase.js`）** —— 离开首屏后目标值从「鼠标位置」切成 `introResetTime()`（`resetAt × duration`，默认 0），并以更果断的 `resetEase = 0.26` 阻尼收敛（跟手是 0.12）。
   - **回正与 0.5s 淡出重叠，不是串行**。串行会让滚动响应多出 `0.4s + 0.5s = 0.9s` 延迟，而主视频此时已在后面推进，滚轮与画面会脱节。
   - `0.5s @60fps = 30 帧`是硬上限，`resetEase` 必须让回正在此之内收干净；实测 10.08s 素材 **24 帧收敛 / 18 帧肉眼中性**，20s / 30s 素材 26 / 28 帧。
2. **写入门 `shouldWriteIntro()`** —— 抽成纯函数，两条纪律互相拉扯且都要成立：(a) 值没变就不写（鼠标静止、回正完成后零 seek）；(b) **回正的最后那一帧精确值必须写进去**。
   > (b) 我第一版写错了：判据在 snap **之后**求值，那一刻恒为假，回正的收尾值永远写不进去，画面停在离初始帧约 6ms 处。抽函数 + 用 `introWritten` 一起判才修好，并有专门一条断言钉住。
3. **`mouseMoved` 门** —— 鼠标从未移动过时，首屏人物保持**初始朝向待机**，不因「鼠标恰好停在屏幕正中」而停在片子中间那一帧。
4. **`readIntroDuration()` 修正** —— 元数据就绪前用的是 `fallbackDuration`，就绪后要重算 `introApplied`，否则首帧会闪一下错位。

同轮复核还修掉两处：

- **CTA 是死锚点** —— `<a class="cta" href="#work">` 指向的 `#work` 不存在，也没有 `data-goto`，点了没反应。已给 `id="work"`（挂在节奏点 1 的 `.copy` 上）并加 `data-goto="0.15"`；`[data-goto]` 的绑定从「只绑 nav tab」改成 `querySelectorAll('[data-goto]')`，`navTabs` 单独保留（它是 HUD 标签的来源）。
- **`STILL SCROLLING.` 在移动端会被劈开** —— `SCROLLING.` 10 字符，iOS/Android 都没有 Impact，回退到系统无衬线时按 ≈0.6em/字符算会顶破容器，`overflow-wrap: break-word` 会从词中间断。改为 `STILL ROLLING.`（最长行 9 字符，留 >10% 余量，语义上也更贴「还在往前滚」）。**字号是流式的、字体回退不可控，能守的只有行长**，所以这条写成了断言。

### 4c. v4 修订（第 4 轮需求）✅

需求原文：「缩小影响范围、靠近鼠标的波纹更细、点击时向外扩散，去掉黑色拖尾。」

**先说一件必须先说的事**：这条需求描述的东西，我在整个 KnowledgeQA 仓库里找不到。搜过 `ripple|trail|波纹|拖尾`、`canvas|getContext|mousemove`、`displacement|feTurbulence|webgl|three|pointerdown|click`，以及当天所有改动过的文件，命中的只有 `.codebuddy` 的技能数据和 `package-lock.json`。**所以我没有去找一个「改坏的旧实现」，而是先问。** 你确认了两件事：这是**展示页上新增**的效果；要**光晕细环**而不是真的折射扭曲；加在**影像之上、文字之下**。

> 关于「加在哪一层」，我原本提的是「加在 `.backdrop` 上」，你选「背景」时也像是在指它。但读代码后发现 `.backdrop` 几乎永远不可见：三个 `.stage` 都是 `position: fixed; inset: 0` + `object-fit: cover` 满屏铺住，墙面只在 `main.mp4` 缺失时才露出来。**我把层表摆给你看，让你在新信息下重选了一次**，改成了真正的「影像之上、文字之下」（z 3，`.scrim` 从 3 抬到 4）。

**新增 `ripple.js`（约 410 行，独立文件）**。四条要求各自钉成一个不等式，而不是形容词：

| 你的原话 | 落成的量 | 值 |
|---|---|---|
| 缩小影响范围 | 包络 `(1−u²)²`，`u = r / influence`，边界**严格**归零 | `influence = 160px` |
| 靠近鼠标的波纹更细 | 波前用对数相位，环距 `s(r) = 2π(r₀+r)/K` 随 r 严格递增 | 近端 **16.1px** → 远端 **56.3px** |
| 点击时向外扩散 | `easeOutCubic` 从 0 扩到 `influence`，一发两圈错开 140ms | 寿命 720ms |
| 去掉黑色拖尾 | 加色混合 + 每帧全清屏 + 环境场**无状态** + 点击环有限寿命 | 见下 |

几何来源（不是拍脑袋）：φ(r) = K·ln(1 + r/r₀)，解 φ = 2πk + ωt 得 r_k = r₀·(exp((2πk+ωt)/K) − 1)。由「近端环距 ≈16px、可见 ≈5 圈」两个条件解出 **r₀ = 64、K = 25**。相位走满一圈时 r(0, 2π) == r(1, 0) = 18.287，连续性成立 —— 旧的最内圈正好变成新的第二圈，同时圆心新生一圈，所以不会出现每圈一次的跳变。

画布**只有 560×560 并跟着光标移动**，不是全屏 —— 「影响范围小」由几何尺寸强制成立，不靠参数自觉；顺带把栅格量降了两个数量级。

**「黑色拖尾」的四条保证**（这是我判断「拖尾」这个词指什么之后反推的根因）：反馈/乒乓缓冲不清屏是 WebGL 折射波纹拖尾的经典根因，所以四条缺一不可 —— `globalCompositeOperation='lighter'`（环与环只相加不压暗）、每帧 `clearRect(0,0,S,S)`、环境场**从 r 与 t 直接解出**没有可累积的历史量、点击环寿命终点与包络零点重合（`r = influence ⟹ alpha = 0`）**必然死透**、不需要超时兜底。

**我自己的一个 bug（自查发现）**：`pointerleave` / `pointerenter` **不冒泡**。我原本挂在 `document` 上，这两个事件的 target 是 `html`/`body`，永远不等于 `document` 本身，监听器**永远不会触发** —— 后果是指针离开窗口后波纹永不淡出，静默烧 CPU，无报错。改成 `documentElement` 的 `mouseleave` + `window` 的 `blur`。重新进入不需要专门监听：`pointermove` 一定会先到，它自己会把 `pointerInside` 置回 true。现在有 3 条断言钉住这个坑。

**`showcase.js` 的配套改动（一处）**：`applyFrame` 新增片尾余量 `tailGuard: 0.04`，`target = Math.min(progressToTime(...), duration − tailGuard)`。这与 `mouseToIntroTime` 既有的留白写法对称，防的是浏览器在**精确到 `duration`** 时给出空白末帧 —— 归零到 `0` 会让滚到底反而黑屏，是「到顶了却更糟」的典型。

### 4d. v4 复核里被我判定为「不该改」的两条

独立复核提了 4 条，我采纳 1 条、**主动不采纳 2 条**，两条都属你的决定而不是我的：

- **（不采纳，中）首屏擦洗的写入节流**：首屏路径在 `|it − introApplied| > 0.008` 时**每帧都写** `currentTime`，实测一次鼠标移动会背靠背写 54 次（鼠标停住后还有约 0.9s 的连续 seek）；而主路径有 `seekDeadzone 0.02` + `maxStep 0.35`。这确实违反了文件自己写的纪律。**但我没改**：加 `!video.seeking` 门可能让回正收敛速率减半、顶破 v3 你明确要的「30 帧 / 0.5s 内收干净」；加限速则要重调 `ease 0.12`，改掉你已经认可的跟手感。**两条都在无浏览器下无法验证**，我不拿你的验收标准去换一个我看不见的收益。
- **（不采纳，低）iOS `unlock()` 之后的一次不可见漂移**：`p=0` 时不可见、且是瞬态。修它要在 seek 循环里**再引入一个状态变量** —— 那个循环我已经写错过一次（见 4b 第 2 点）。风险大于收益。
- **（采纳，低）`tailGuard`**：与 `mouseToIntroTime` 的留白**真正对称**，且防的是浏览器相关的空白末帧。

### 4e. v5 复核记录（独立复核实际跑过的一轮）✅

`trellis-check` 对 **v5 终态**跑了一轮，提了 4 条，**全部采纳**：

1. **顶栏被劫持（真 bug）** —— `.copy--panel` 是 `inset: 0` + `pointer-events: auto` 且 `z-index 6` > 顶栏 `z-index 5`，顶栏**可见但点不动**。修法见 4f。
2. **prd / design 的 z 序漂移** —— `design.md §12.2` 的表把 `.scrim` 记成 4、`.ripple` 记成 3，与代码相反。已改正，并把「薄纱在波纹之下」的理由重写（v4 写的理由把薄纱当成了文字层，而真正的文字层在 z-index 6，波纹两层都够不着；薄纱左侧压暗到 82%、正是光标常驻处，所以波纹必须在它之上）。
3. **`CONFIG.sections` 注释过期** —— 已删。
4. **`.hero__aside-title` 无人覆盖** —— 右栏标题是全页唯一没有溢出断言的长文本。已补 em 预算断言 + 一条反向（去掉 `<br>` 必须变红）。

### 4f. v6 修订（第 6 轮需求）✅

用户原话（含笔误）：**「个人简历背景使用 intro.jepg　作品文件夹背景使用 beat-jepg，左边排版使用 fodler.png，点击后弹出 beat-2.jepg 替换左边内容，特效为弹出过渡效果，无限可能背景使用 beat-3.jepg，活动到这也一个下坠的效果展示出这个图。」**

三处歧义**先问后做**，没有一处靠猜：

| 歧义 | 我的问题 | 你的决定 |
| --- | --- | --- |
| `beat-jepg` 缺一个数字 | 哪张图？ | **用证据定，不问**：读 `media/作品示例排版.png`（你给的面板设计稿），背景与 `beat-1.jpeg` 逐项吻合（右侧扶手椅上的小孩、青灰墙），⇒ `beat-1.jpeg` |
| 点击后「替换左边内容」到底替换成什么 | 三选一 | **封面 → 内页，换成整图**。选项里已写明代价：`beat-2` 的文字是位图，会打破「卡片必须是可选中真文本」 |
| 「下坠的效果」 | 一次性动画还是滚动驱动？ | **滚动进度驱动**：图从上方坠入并停住，可逆 |
| 整图背景必然带人物 | 与 v2「背景恒定」冲突怎么办？ | **确认覆盖，直接用整图** |

改动清单：

- `index.html`：`.backdrop` 内加 3 个 `.backdrop__scene`；`.folder__deck` 换成封面按钮 + 内页按钮；卡片原文移入 `.sr-only`；右栏标题加 `<br>`；媒体契约表头重写
- `showcase.css`：`.backdrop__scene` 基态与 `.is-active`；`.folder__deck` / `.folder__cover` / `.folder__page` 与弹出曲线；`.sr-only`；`.copy--panel { pointer-events: none }`（**这就是 4e 第 1 条的修法**）；移动端改成 `grid-template-areas: "folder"` 让两态共格、过渡保住
- `showcase.js`：`CONFIG.sceneDrop`；纯函数 `sceneDropY`；`sceneEls` / `dropEl` / `dropSpan`；`applyFrame` 里加「按 `copyKey` 切分镜层」与「下坠位移」两步；文件夹开合重写（`setFolderOpen` + 每按钮各自的监听 + 只挂 `.folder__deck` 的空白关闭）
- 断言：131 + 250 + 55 = **436**，另加 `v6_teeth.js` 13 条反向验证

**这一轮唯一真的牺牲掉的东西**：卡片文字从「可选中真文本」变成位图。缓解是把原文放进 `.sr-only`（仍可搜索、可读屏），并且这条放宽在 checker 里是**显式写明的注释**，不是事后追认。

### 5. 自检（无浏览器）✅

```bash
node --check frontend/public/showcase/showcase.js
node "C:/Users/admin/AppData/Local/Temp/showcase_check.js"
```

**不能用 `require('./showcase.js')` 直接跑纯函数断言** —— `frontend/package.json` 是 `"type": "module"`，该目录下的 `.js` 会被当成 ESM，`require` 抛 `ERR_REQUIRE_ESM`，且 ESM 作用域里 `module` 是 undefined，`module.exports` 守卫不会执行。改用 `vm` 以经典脚本方式求值（沙箱里提供假 `module`，`typeof document === 'undefined'` 因此跳过 `init()`）。

**63 条断言，ALL PASS**：分段边界（0 / 0.5 / 0.979 / 0.98 / 1）、`p × duration`、越界钳制、`beatIndexAt` 边界与**与时长无关**（30 / 10.08 / 8 / 120 四种时长结果一致）、`p` 扫过 0..1 覆盖全部 3 段、`formatTime` 补零与负值、`mouseToIntroTime` 的线性映射 / 越界钳制 / invert 反向 / 单调性 / 退化时长。

**v3 新增 17 条**：`shouldWriteIntro` 的 7 种门条件（含「最后一帧 -> 写」与「已收干净 -> 不写」这一对）；**回正收干净后连续 120 帧零写入**；回正收敛帧数模拟（照抄阻尼循环，`snap = 0.008` 与 `applyFrame` 一致）；20s / 30s 素材的回正帧数；以及一条**反向断言** —— 用跟手阻尼 `0.12` 回正需 42 帧 > 30，钉住「`resetEase` 必须与跟手阻尼分开」这个设计决定；`resetEase > ease`、阻尼系数落在 `(0,1)`。

### 5b. HTML ↔ JS 契约交叉校验 ✅

选择器拼错会让 `querySelector` 返回 `null`、页面局部静默失效 —— 这是"不开浏览器"下最容易漏的一类缺陷。

```bash
node "C:/Users/admin/AppData/Local/Temp/showcase_dom_check.js"
```

**72 项断言，ALL PASS**：21 个选择器全部命中、`.stage__inner` 恰好 3 个、**`.backdrop` 是 fixed + cover + z 0**、`bg-wall.jpeg` 在 CSS 里**只被引用一次**（v2 的理由是「背景恒定」；v6 理由换成「底图与逐节图是两条独立的路」，断言本身仍然成立且仍然有用）、**main 段无 poster** 且全站恰好 2 个 `.stage__poster`、无 `.is-beat` / `posters` / `--px` 死代码、4 个 `.copy` 都声明 `data-pos` 且有 ≥2 种不同取值、3 种落位在 CSS 里都有映射、**`.stage` 无 `transform/filter/will-change`**、`.stage__inner` 有 `transform`、main 无 `autoplay`、intro 有 `autoplay+loop` 作兜底且 JS 会摘掉、`muted+playsinline+preload=auto` 齐全、脚本是传统脚本、`--fade` 为 .5s、全站无 `#000`/`#fff`。

**v3 新增 15 项**：`resetEase` / `resetAt` / `mouseMoved` / `introWritten` / `introResetTime` 都在、`shouldWriteIntro` 存在、`intro.currentTime` 由 `introApplied` 驱动（不是读回来当控制量）；CTA 带 `data-goto` 不是死锚点、`href="#work"` 有真实落点、5 个 `data-goto` 全落在 `[0,1]`、JS 绑的是 `[data-goto]` 全集而 `navTabs` 单独保留。

> 断言必须先剥掉注释再判。头一版没剥，`bg-wall.jpeg` 和 `#000 / #fff` 两条被 CSS **注释里**的文字误判成 FAIL —— 代码本身是好的。现在统一用 `cssCode = css.replace(/\/\*[\s\S]*?\*\//g, '')`。

**v4 新增 30 项（72 → 102）**，其中最重要的一条是**推翻我自己 v3 写的断言**。详见下一节。

**v5 → v6 变动**：`.folder__art` / 3 个 `.fcard` 的断言（`exactly 3 .fcard (got 0)` 等 8 条）在 v6 **按新结构重写而非删除**；`refd.size >= 8` 换成对 `EXPECTED_REFS` 的**双向集合相等**（穷举更严，且正则失配不再能蒙混过关）；新增 §1c 分镜层块、§5e-2 右栏标题 em 预算块、§5f-2 文件夹契约块、v5 残骸块。**102 → 250**。

### 5c. 复核抓到的最高价值一条：我 v3 的断言用错了度量 ⚠️ → 已修

v3 我写的是「**主标题最长一行 ≤ 9 字符**」，实测最长 `THE SOFA.` 恰好 9，断言通过。

**但字符数不是排版溢出的不变量。** `THE SOFA.` 9 个字符里有空格，且 T / H / E / O / F / A 都是宽字；按 Arial 大写的字符推进宽度算 **5.279em**，而容器可用宽度是 **5.111em = 101.5%** —— 在 721–1354px 的**每一档**宽度上都会溢出，`overflow-wrap: break-word` 会把 `THE SOFA.` 从词中间拆成 4 行。断言之所以放它过去，是因为它数的是字符而不是宽度：**这条断言和我自己的盲点同构**。

三处一起修：

1. **`.copy` 宽度 `min(40rem, 46vw)` → `min(40rem, 48vw)`** —— 让缩放段与封顶段的可用宽度都恰好落在 **5.333em**。注意 `min(40rem, 48vw)` 与 `clamp(3.5rem, 9vw, 7.5rem)` 都在 **1333px** 处切换，所以可用宽度是一个**常数**，扫一遍视口宽度就能证明。
2. **主标题重新断行** `MADE<br>IN<br>THE SOFA.` → `MADE<br>IN THE<br>SOFA.` —— 最长行从 5.279em 降到 **3.278em**。
3. **断言换成 em 宽度预算**：内置 Arial 大写推进宽度表 + `lineEm()` + `availEm()`（对每个视口分别求 `min()` / `clamp()`），扫 721–2560（桌面）与 320–720（移动），断言 `minAvail >= 5.3`、`worstEm / minAvail <= 0.90`。另加**两条「有牙齿」的反向断言**证明这个预算真的能抓人：`THE SOFA.` 占 **99.0%**、`SCROLLING.` 占 **113.6%**，都会被拦下。

结果：现在最宽的一行是 `ROLLING.` **4.668em / 5.333em = 87.5%**，留有余量。`showcase.css` 里那段声称「≤ 8 字符」的注释也一并重写成 em 预算的推导（**它的注释和它守护的内容早就对不上了**）。

**教训**：能用「字符数」描述的排版约束，实际约束几乎总是**宽度**。ASCII、比例字体、大写字母三者一凑，字符数就是一个会通过的错误指标。

### 5d. 波纹层的纯函数断言 ✅

```bash
node --check frontend/public/showcase/ripple.js
node "C:/Users/admin/AppData/Local/Temp/showcase_ripple_check.js"
```

**55 条断言，ALL PASS**，按你的四条要求分组：

- **影响范围**：`env(0)=1`、`env(influence)=0`、`env(1.5×influence)=0`、半程 `0.5625`、`[0, 2×influence]` 上单调不增、`influence ≤ 200`
- **「更细」**：环距在 `[0, influence]` 上**单调递增**（这是「近处更细」唯一需要的不等式）、近端 16.085 / 远端 56.297、比值 ≥ 3、近端 ≤ 20px；描边宽度近细远粗且单调不减、近端 ≤ 1.2px
- **点击扩散**：`easeOutCubic(0.5)=0.875` 且单调；点击瞬间 `r=0, alpha=clickAlpha`；**寿命终点 `r = influence` 且 `alpha` 严格为 0、`alive=false`**；alpha 全程单调衰减（中途回亮看起来会像卡了一下）；错开的第二圈确实晚于第一圈
- **无拖尾**：300 帧（5s，远大于 `clickLife + 最大 delay`）后存活环数归零、**总 alpha 严格为 0**；连点 100 次后环数被压到 `maxRings`；`fadeStep` **吸附到精确 0** 且 50 帧内完成 —— 纯阻尼只会逼近 0，`isSilent` 就永远为 false，循环永不停止，**这个 bug 不报错、只发热**

两个参数退化保护：`visibleRingCount` 有 4096 硬上限（`gapK ≤ 0` 会让 `exp` 爆掉或恒 0）；相位扫过整圈可见圈数始终有界。

另外单独验证了**待启动的那一圈必须返回 `alive: true`**（`pending: true`）—— 若返回 `null`/`false`，调用方的 `filter` 会把错开的第二圈直接丢掉，它永远不出场。

### 5e. 波纹层的 DOM 契约断言

`showcase_dom_check.js` 里新增一段，与 5b 同一套路：**没有**静态 `<canvas>`（由 JS 创建）、传统脚本、无 `fetch` / `import`、`.ripple` 是 `fixed` + `pointer-events: none`、z-index **4**、`.scrim` 是 **3**（v5 对调；本节写于 v4，当时是反的）、有 `clearRect`、有 `'lighter'`、有 `prefers-reduced-motion` 分支、有 `(hover: hover) and (pointer: fine)` 门、有 `visibilitychange`、有 `requestAnimationFrame`、以及**三个坑位守卫**：没有任何元素挂 `pointerleave`、用的是 `documentElement` 的 `mouseleave`、窗口失焦也淡出。

### 6. 确认 React 应用未被波及 —— ⚠ 无法作为验收门

```bash
cd frontend && npm run build
```

**该命令在本机既有失败，与本轮改动无关**：`xlsx` / `docx-preview` / `recharts` 在 `package.json` 里声明了但 `node_modules` 中没有安装，`tsc -b` 报 `TS2307: Cannot find module`，报错位置全在 `src/`。

已用两条证据确认与本轮改动无关：
1. `frontend/tsconfig.app.json` 是 `include: ["src"]`，`tsconfig.node.json` 是 `include: ["vite.config.ts"]` —— `public/` 下的文件**不在任何一个编译程序内**；
2. 报错文件全部是 `src/` 下的既有 React 代码。

要恢复该验收门需先 `cd frontend && npm install`（会改动 `node_modules` 与可能的 lockfile），**本次未执行**，属需要你决策的环境修复。

> 注：失败的 `tsc -b` 会写脏被跟踪的构建产物 `frontend/tsconfig.app.tsbuildinfo`，已 `git checkout --` 还原。

### 7. 手工验收（由你执行，我不自动开浏览器）

```bash
cd frontend && npm run dev
```

打开 `http://localhost:5173/showcase/`，逐条核对 PRD §5 的 **41 条**验收标准，重点：

- 向下滚前进 / **向上滚倒放**（验收 7）
- **首屏鼠标左右移动，人物头部跟着转；鼠标停住画面就定住不动**（验收 11 / 12）
- **滚轮往下滚离开首屏后，继续晃鼠标，人物朝向不再变化**（验收 27）
- **离开首屏时人物是主动转回初始朝向的**，不是僵在最后那个朝向上淡出（验收 28）
  —— 这两条是 v3 的核心，也是最容易看出「做没做对」的一处
- 滚动全程背景是同一面墙，**不随板块变**（验收 14）
- 文案落位随板块改变：首屏与节奏 1 靠左、节奏 2 上移、节奏 3 压左下（验收 17）
- 三段切换是 0.5s 淡入淡出，不是硬切（验收 10）
- **点首屏的「先认识我，再看作品」按钮，页面会平滑滚到作品文件夹**（验收 32）
- 当前 `main.mp4` 不存在，应看到**恒定墙面 + 文案换位**，无白屏无报错（验收 19）
- 缩到手机宽度，双栏堆叠且主标题不溢出（验收 4 / 33）
- **主标题现在是 3 行 `MADE / IN THE / SOFA.`** —— 如果你看到的是 4 行、或 `SOFA.` 被从中间劈开，说明 em 预算算错了（验收 33）

v4 波纹层（验收 34–41）：

- 光标附近出现一圈圈**细亮环**，**离光标越近环越密**，远处明显更疏（验收 35 / 36）
- **环只在光标周围一小片区域可见**，越往外越淡，到一定半径外完全消失 —— 没有环飘到屏幕别处（验收 34）
- 点击一下，**一圈亮环从点击处向外扩散**，稍后还有第二圈跟上（验收 37）
- **关键：环不会拖出一条黑尾巴。** 快速甩动鼠标、连点十几次，画面应该只有当下的亮环，**任何位置都不该留下变暗的痕迹或残影**（验收 38）
- 鼠标移出窗口 / 切到别的标签页再回来，波纹会淡掉并**停下来**；回来动一下鼠标立刻恢复（验收 39）
- 波纹**盖在画面上、在文字下面** —— 环经过文案区域时不会把字遮住或搅浑（验收 40）
- 系统开了「减弱动态效果」时，**完全没有波纹**；手机上（触屏）也完全没有（验收 41）
  —— 这两条测的是「**根本不创建画布**」，可以在开发者工具里看 DOM：`.ripple` 这个 canvas 元素应该压根不存在

### 8. 提交

- 4 张分镜图 + `bg-wall.jpeg` + `folder.png` + 首屏视频 + **4 个源文件**（`index.html` / `showcase.css` / `showcase.js` / `ripple.js`）一并 `git add`（用户已明确授权素材「纳入，一并 commit」）
- commit message 用中文 → **必须走 `git commit -F <file>`**（把 message 写进文件），不能 `-m "中文"`
- `frontend/assets/示例.jpg` **不在**我的提交范围（你的参考文件）；`media/作品示例排版.png` 同理 —— 它是面板的设计稿，运行时不加载（见「未决 7」），一并排除
- **v6 起引用关系反过来了**：`beat-1.jpeg` / `beat-2.jpeg` / `beat-3.jpeg` / `intro.jpeg` **全部被引用**（分别是作品文件夹背景、内页整图、无限可能背景、个人简历背景），不再是派生源。
- **v6 新的死重量是 `card-rag.png` / `card-web.png` / `card-agent.png`**：v5 的三张卡片图，其 HTML 已被 `beat-2.jpeg` 整图取代，`index.html` 里再不出现。它们与 `folder.png` 的**派生源**关系也断了（现在不需要再派生）。`public/` 是会被 vite 原样拷进 `dist/` 的目录，留着等于每次部署多带这部分重量。**我没有擅自删**（删文件不可逆，且它们仍是设计资产的来源），等你一句话：移走 / 删除 / 留着都行。

---

## 完成定义（DoD）

- [x] `node --check` 对 `showcase.js` 与 `ripple.js` 都通过
- [x] 纯函数断言 131/131 通过（vm 求值，非 `require`）
- [x] 波纹纯函数断言 55/55 通过
- [x] HTML↔JS 契约校验 250/250 通过
- [x] **合计 436 条全绿**（v5 为 350 条）
- [x] **反向验证 13/13 全绿**（`v6_teeth.js`）：每条新断言都有一条「改坏它必须变红」的对照；其中把下坠落点从「精确 0」改成「趋近 0」会同时打红 5 条
- [x] `frontend/src/` 下 React 代码**零改动**
- [x] 图片资源：v6 新增 `media/folder.png`；`bg-wall.jpeg` 由「唯一新增」退为派生兜底；`card-*.png` 由被引用变为无引用（见「未决 10」）
- [ ] ~~`cd frontend && npm run build` 通过~~ → **环境既有失败，非本轮引入**；已由「编译范围证据」替代背书（见步骤 6）
- [ ] PRD §5 的验收：编号至 49，其中 **14 已作废**（v6 改由 42–46 覆盖），实际 **48 条有效**。非手工项已核，`[手工]` 项（45、47）待你在浏览器确认
- [ ] 独立复核（`trellis-check`）对 **v5 终态**跑过一轮 —— v4 那轮的复核早于文件夹面板，不能沿用；**v6 的改动尚未经过独立复核**

## 未决 / 待你确认

1. **首屏擦洗的映射轴**（本任务唯一我没能验证的交互，无浏览器环境下测不出来）。当前按**线性横向扫视**实现：鼠标从左到右 = 时间轴从 0 到片尾。若实拍是「上下左右」的离散朝向，横向扫视仍能用（只是纵向鼠标轴只做 ±8px 微位移、不换朝向）；若方向反了，把 `CONFIG.intro.invert` 改成 `true`；若是 3×3 朝向网格，需要改成 `(row, col)` 索引取帧，改动集中在 `CONFIG.intro` 与 `applyFrame` 第 4 段的 4 行映射。**素材已到位，这条现在你一眼就能看出对不对。**
1b. **「初始状态」是哪一帧** —— `CONFIG.intro.resetAt`（默认 `0`，即片头）就是这个问题的答案，我按「片头即中性」取的默认值。如果实拍的**正脸在片子中间**，回正看到的就是人物转回一个侧脸，观感上不算「回到初始」。改法是一行：`resetAt: 0.5`。哪一帧是正脸只有你看素材才能定。
2. **节奏分界比值**：`CONFIG.beatCuts = [0.30, 0.54, 0.86]`（v5 从两个分界扩到三个，对应参考视频的五节导航）已改为**占全长比例**（原先写死绝对秒数 `[0-9][9-21][21-30]`，那是与「主视频恰好 30 秒」焊死的 —— 换成 10 秒素材会让「无限可能」永远进不去且不报错）。比例只保证四节铺满全长，**不保证分界正好落在画面转场上**，`main.mp4` 到位后仍要按实拍重校这三个值。刻度、导航落点、HUD 序号三处都从这个数组现算，改一处即可。
3. **首屏视频带 AAC 音轨但不发声**。`muted` 是 `preload`+擦洗的硬性前提（也是移动端 autoplay 策略要求），且擦洗模式下视频根本不 play。这是预期行为，不是 bug。
4. **收尾文案**：`p ≥ 0.98` 沿用节奏点 3 的画面，未配独立文案。如需收尾金句，在 `index.html` 加第 5 个 `.copy` 块并在 `CONFIG` 里给它一个 key。
5. **`npm install` 修复构建**：`xlsx` / `docx-preview` / `recharts` 未安装导致 `npm run build` 既有失败。是否要修属你的环境决策，本次未擅自执行。
6. **CDN 缓存**：`docs/deploy-runbook.md:96` 的规则按 `/assets/*` 匹配，`/showcase/*` 不在其中。属正常静态资源、无需额外配置，但若你们的 CDN 只放行白名单路径，需把 `/showcase/*` 加进去。
6b. **首屏擦洗要不要加写入节流**（复核提出，**我故意没改**，理由见 4d）。这是你的决定：现在首屏跟手的观感是你认可过的；加节流会改善「鼠标停住后仍有约 0.9s 连续 seek」这一点，但可能要重调 `intro.ease` 并影响回正收敛速度。**只有你在浏览器里觉得首屏跟手发飘或掉帧，才值得动它。**
7. ~~**`media/作品示例排版.png` 归属未定**~~ → v5 走 (b)：**这个面板做出来了**，所以它现在是「作品文件夹」整屏面板的设计稿，与 `示例.jpg` 同为**只取排版、运行时不加载**的参考图，**不在提交范围**（和 `示例.jpg` 一样处理）。它有两个用处已经兑现：
   - 解开了全页唯一读不出的文案：底部提示原文是**「点击空白栏或按 ESC 收起」**（我之前从视频里猜的是「空白处」，已按原文改回）
   - 确认眉标就是 `BIAOGE / SELECTED WORK`（这份文档原先记的 `BIAGE` 是误读）

8. **卡片内容：视频与设计稿不一致 —— v6 之后这个问题换了个形式，但没消失。** 设计稿上三张卡是 `3D设计` / `UI DESIGN` / `插画 IP`，每张底部还有一行英文小标签（`CHARACTER · MODELING · RENDER` / `INTERFACE · EXPERIENCE · ICON` / `ILLUSTRATION · CHARACTER · STORY`），文件夹本体上写着 `Portfolio -Bg`。而参考视频里成品卡片是 `RAG知识库` / `网站设计` / `Agent设计`，**没有那行英文标签**，文件夹本体也没有文字。v5 取的是**视频**那一版（理由：你给的是「整体设计效果参考设计视频.mp4」，视频是成品、设计稿是过程稿）。
   **v6 起整页改用 `beat-2.jpeg` 整图，所以「卡片文字」不再是 HTML 文案，而是那张图本身** —— 图上是哪一版，页面就是哪一版，改文案已经改不动它了。若你要换版，得先换 `beat-2.jpeg` 这张图（并且同步改 `.sr-only` 里的原文，否则读屏内容与画面不符，那比没有更糟）。
   v6 顺带**用上了设计稿的另一处证据**：`作品示例排版.png` 里的背景与 `beat-1.jpeg` 逐项吻合（右下角扶手椅上的小孩、青灰墙），据此确定了「作品文件夹那一节用哪张图」—— 用户原话里的 `beat-jepg` 缺了一个数字，我没有猜。

9. **v5 / v6 的独立复核未做**。`trellis-check` 只对 v4 终态跑过一轮。v5（首屏六块文案、整屏文件夹面板、分节刻度、暂停互动、视线读数）与 v6（逐节背景、下坠、弹出、顶栏劫持修复）**都没有经过独立复核**，目前只有 436 条离线断言 + 13 条反向验证背书。离线断言能证明「代码按我写的规则成立」，不能替代「这套规则本身对不对」的独立判断。

10. **`card-rag.png` / `card-web.png` / `card-agent.png` 现在无人引用**（详见「提交」一节的说明）。留在 `media/` 会让每次部署多带这部分死重量。**我没删**，等你定：移出 `public/` / 删除 / 保留。

11. **⚠️ `main.mp4` 一旦到位，三张逐节背景在最主要的四个板块里会被完全盖住。** `.stage--main` 是 `position: fixed; inset: 0` 且视频 `object-fit: cover`，铺满整个视口；分镜层在它**下面**（z-index 0 < 1）。也就是说本轮要的「个人简历 / 作品文件夹 / 无限可能各有背景」**只在 `main.mp4` 缺失时可见**。这不是参数问题，是层序的必然结果。两条路：**(a)** 保持现状（分镜层只在无视频时兜底）；**(b)** 把分镜层提到影像之上 —— 那等于放弃 main 视频在主体段的可见性。**这是个方向性决定，我没有擅自反转层序。**

## 已解决

- ~~outro 视频源~~ → 用户决定 outro 不使用视频，只显示 `beat-3.jpeg` 静态图。页面因此只需 **2 路视频解码**。
- ~~v1 三层 poster 交叉淡入~~ → v2「背景恒定」需求与之直接冲突，已整体删除；main 缺失时改由 `.backdrop` 兜底。**v6 把「逐节背景」重新加回来了，但做法不是恢复 poster**：改用 `.backdrop` 内部的 `.backdrop__scene` 层，与 stage 层互不干扰，所以「main stage 里没有 poster」这条**依然成立**。这是「背景恒不恒定」的第二次翻转（v1 变 → v2 恒定 → v6 变）。
- ~~v5 的 `.fcard` 三卡结构~~ → v6 用户要求「点击后弹出 `beat-2.jpeg` 替换左边内容」，三张卡的整体被一张整图取代。原文移入 `.sr-only` 保留可搜索性，`object-fit` 与逐卡动画一并删除。
- ~~v1 整体平移视差~~ → v2 改为鼠标位置擦洗时间轴，`--px` 变量及其所有引用已清除。
- ~~节拍写死 30 秒~~ → 改为 `beatCuts` 比例，与时长解耦，并加了四条「与时长无关」回归断言。
- ~~首屏视频素材缺失~~ → 已到位并接入。
- ~~离开首屏就停写 `intro.currentTime`~~ → v2 的写法让人物僵在半转头淡出，v3 改为主动回正。
- ~~CTA 点了没反应~~ → `#work` 是死锚点。最终解法不是补 `id` + 写死 `data-goto`，而是 v5 改成 `data-section="2"`：进度值由 `sectionTarget()` 从 `beatCuts` 现算。写死进度等于给分节留了一份会静默过期的副本，改分节时那一节点了就没反应且不报错。
- ~~首屏 poster 404~~ → HTML 引用 `media/intro-loop.jpeg`，磁盘上却是 `media/intro.jpeg`（视频叫 `intro-loop.mp4`，兜底图并不叫 `intro-loop.jpeg`）。**声明了却不存在，首屏兜底图从头到尾没显示过，而所有文本匹配断言全绿。** 已改引用，并补上「每个 `media/` 引用都要在磁盘上真有」这条断言 —— 三种引用形式（`src`/`href`、CSS `url()`、内联 style 里的 `--poster:url()`）都要抓。
- ~~`STILL SCROLLING.` 移动端被劈开~~ → 改 `STILL ROLLING.`。
- ~~「最长一行 ≤ 9 字符」~~ → **这个不变量本身就是错的**（字符数不是排版溢出的度量）。已换成 em 宽度预算，见 5c。
- ~~波纹效果找不到实现~~ → 不是「改坏的旧实现」，是**新增**；已按你确认的两个岔路（光晕细环 / 影像之上文字之下）实现。
- ~~`pointerleave` 挂 `document` 收不到~~ → 这两个事件不冒泡，改 `documentElement` 的 `mouseleave` + `window` 的 `blur`。
