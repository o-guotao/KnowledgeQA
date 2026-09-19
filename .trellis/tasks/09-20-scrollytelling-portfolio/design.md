# design.md — 滚动叙事作品集展示页

> **v6 变更摘要**（用户第 6 轮需求，**第二次推翻「背景恒定」**）
> 1. 三个板块各有一张**逐节背景图**：个人简历 `intro.jpeg`、作品文件夹 `beat-1.jpeg`、
>    无限可能 `beat-3.jpeg`。做法是在 `.backdrop` **内部**加 `.backdrop__scene` 分镜层，
>    底图 `bg-wall.jpeg` 退化为恒定兜底。
> 2. 作品文件夹的左侧排版改成 `folder.png`（合着的文件夹）→ 点击弹出 `beat-2.jpeg`（内页整图）。
> 3. 无限可能那一节，背景图随滚动**下坠入画**（`easeInCubic`，落点精确为 0）。
> 4. 顺带修掉 v5 遗留的一个真缺陷：面板 `pointer-events` 劫持顶栏（§3.6 同款问题，见 prd §3.6）。
>
> ⚠️ **本文档里所有「背景恒定」的表述（§3、§11 等）均已被 v6 推翻**，保留原文只为记录演变。
> 注意：**只要 `main.mp4` 到位，它在四个主体段里用 `object-fit: cover` 铺满视口，
> 分镜层就会被完全盖住** —— 这是分镜层与「main 视频必须全屏」之间的固有冲突，
> 已如实报给用户，未擅自反转层序。详见 prd §3.5。
>
> **v4 变更摘要**（用户第 4 轮需求）
> 新增一个**鼠标波纹层**：光标附近一圈细亮环，点击时向外扩散一轮。
> 四条参数要求 —— 影响范围小、近鼠标处波纹更细、点击向外扩散、**无黑色拖尾**。
> 两个已定的岔路：**画光晕细环而非折射扭曲**、**加在影像之上文字之下**（不是 `.backdrop`）。
> 详见 §12。
>
> **v3 变更摘要**（用户第 3 轮需求）
> 1. 滚轮离开首屏后，鼠标**交出**对人物视线的控制，人物**主动回正到初始朝向**，再衔接下一段
>    动画。v2 只是「停止写 `currentTime`」→ 人物僵在最后朝向淡出。详见 §7.1。
> 2. 顺带修掉三处复核发现的问题：intro 的时长重算不对称、`unlock()` 缺 promise 守卫、
>    CTA 是死锚点；以及主标题最长行超长会在移动端被断词劈开（`SCROLLING.` → `ROLLING.`）。
>
> **v2 变更摘要**（用户第 2 轮需求，覆盖 v1 相应部分）
> 1. ~~参考图**只取文字排版**，不取背景；**全站背景恒定**为分镜里那面青灰墙（裁切派生 `bg-wall.jpeg`）~~
>    —— 前半句（只取排版）**已于 v6 推翻**：作品文件夹改用 `beat-2.jpeg` 整图；
>    后半句（背景恒定）**已于 v6 推翻**：改为逐节分镜图，`bg-wall.jpeg` 退为兜底
> 2. 首屏改为**鼠标位置擦洗视频时间轴**（不再 autoplay loop）
> 3. 文案**避让视频构图**，每个板块落位不同
>
> 因此 v1 的「main 段三层 poster 交叉淡入」被**移除** —— 它与当时的「背景恒定」直接冲突。
> v6 改回逐节背景，但做法不同：不在 main stage 里放 poster，而是在 `.backdrop` 内加分镜层，
> 分镜层与 stage 是**两个独立的层**，各自的显隐互不干扰。

## 1. 目录与文件布局

```
frontend/public/showcase/          ← vite 默认 publicDir，原样拷进 dist/
├── index.html                     # 结构 + 文案 + 媒体路径声明
├── showcase.css                   # 设计令牌 + 排版 + 响应式
├── showcase.js                    # 状态机 + 滚动驱动 seek + 鼠标擦洗
├── ripple.js                      # 【v4】鼠标波纹层，独立 rAF，零依赖
└── media/
    ├── bg-wall.jpeg               # 【派生】底图：v6 起退为兜底，不再是唯一背景
    ├── folder.png                 # 【v6】作品文件夹封面：合着的橙色文件夹（透明 PNG）
    ├── card-rag.png               # 【v6 起无引用】v5 的三张卡片图，已被 beat-2 整图取代
    ├── card-web.png               #       仍留在磁盘上，未删（见 implement.md 未决项）
    ├── card-agent.png             #       （works 目录的 作品示例排版.png 同理）
    ├── intro-loop.jpeg            ← 由 frontend/assets/start.jpeg 移入
    ├── beat-1.jpeg                ← 由 frontend/assets/computer.jpeg 移入
    ├── beat-2.jpeg                ← 由 frontend/assets/card.jpeg 移入
    ├── beat-3.jpeg                ← 由 frontend/assets/end.jpeg 移入
    ├── intro-loop.mp4             # 【已到位】首屏视频：10.08s / 1280x720 / H.264 + AAC
    └── main.mp4                   # 待你放（主视频.mp4）
```

页面只需这 **2 路视频**。outro 段**无视频**，只显示 `beat-3.jpeg` 静态图。

**为什么是 `public/` 而不是 `assets/`**：`frontend/Dockerfile` 只 `COPY --from=build /app/dist`，`assets/` 不进镜像；`nginx.conf` 的 `try_files ... /index.html` 会把找不到的路径**静默回退成 React 首页**（返回 200，不 404），排查成本高。`public/` 的内容由 vite 原样拷贝进 `dist/`，dev / Docker / EdgeOne 三条路径全部可达，**零配置改动**。

**`bg-wall.jpeg` 从哪来**：`beat-1.jpeg` 的 `x 0–1300, y 60–790`（1300×730，约 16:9）是纯墙面。四张分镜都把人物画在右侧，直接拿任一张当背景会让**人物与 main 视频里的人物重影**，所以必须裁。裁出的区域正好左暗右亮，与左侧文案天然形成对比。

> **v6 起这条「必须裁」的理由被用户明确推翻**：用户要求直接用整张分镜图当作对应板块的背景，
> 接受「分镜里的人物可能和 main 视频里的人物重影」。`bg-wall.jpeg` 因此不再是唯一背景，
> 只在没有任何分镜层命中的两个板块（第 2 段、收尾段）露出来兜底。
> 这是本项目里「背景恒不恒定」的**第二次**翻转（v1 变 → v2 恒定 → v6 变）。

**副作用（可接受）**：`dist/` 会多出 `showcase/` 目录；`docs/deploy-runbook.md:96` 的 CDN 缓存规则按 `/assets/*` 匹配，`/showcase/*` 不在其中，属正常静态资源、无需额外缓存配置。

---

## 2. 两条铁律：配置放哪

| 改什么 | 改哪里 | 为什么 |
| --- | --- | --- |
| 视频 / 图片路径 | **`index.html`** 的 `<source src>` / `--poster` 变量 | 真正做到「把 mp4 丢进 `media/` 就生效」，不碰 JS |
| 文案落位 | **`index.html`** 的 `.copy[data-pos]` | 改一个属性值即换位置，不碰 CSS |
| 节奏分界比例（`beatCuts`）、缓动、擦洗映射、阈值 | **`showcase.js`** 顶部 `CONFIG` | 纯调参，改动风险低 |

---

## 3. DOM 结构

```html
<body>
  <!-- 0. 底图恒定；v6 起内部再叠三张逐节分镜层（个人简历 / 作品文件夹 / 无限可能），
       分镜层必须 absolute —— fixed 会逃出 .backdrop 的包含块，整块不再属于 z-index 0 -->
  <div class="backdrop" aria-hidden="true">
    <div class="backdrop__scene" data-scene="0" style="--scene:url(media/intro.jpeg)"></div>
    <div class="backdrop__scene" data-scene="1" style="--scene:url(media/beat-1.jpeg)"></div>
    <div class="backdrop__scene" data-scene="3" data-drop
         style="--scene:url(media/beat-3.jpeg)"></div>
  </div>

  <!-- 三段舞台。要害：.stage 本身绝不能有 transform / filter / will-change，
       否则 position:fixed 的包含块变成它自己，全屏铺满立刻失效。 -->
  <section class="stage stage--main" data-stage="main">     <!-- z 1 -->
    <div class="stage__inner">
      <video data-role="main" ...></video>                  <!-- 无 poster -->
    </div>
  </section>

  <section class="stage stage--intro" data-stage="intro">   <!-- z 2 -->
    <div class="stage__inner">                              <!-- 鼠标擦洗只动这里 -->
      <div class="stage__poster" style="--poster:url(media/intro-loop.jpeg)"></div>
      <video data-role="intro" ...></video>
    </div>
  </section>

  <section class="stage stage--outro" data-stage="outro">   <!-- z 2，无 video -->
    <div class="stage__inner">
      <div class="stage__poster" style="--poster:url(media/beat-3.jpeg)"></div>
    </div>
  </section>

  <!-- 3. 可读性薄纱（保留原样，用户决定） -->
  <div class="scrim" aria-hidden="true"></div>

  <header class="topbar"> … </header>                       <!-- z 5 -->
  <div class="copy-layer"> … </div>                         <!-- z 6 -->
  <div class="hud"> … </div>                                <!-- z 7 -->
  <div class="scroll-track" data-scroll-track></div>
  <script src="showcase.js"></script>
</body>
```

**叠放顺序**（全部 `position: fixed`，靠 z-index 分层）：

```
0  .backdrop                底图 bg-wall.jpeg，恒定
      └ .backdrop__scene    逐节分镜层，absolute + inset:0，同属 z-index 0
1  .stage--main   主视频；缺失时透明 → 露出 .backdrop
2  .stage--intro / .stage--outro
3  .scrim         压暗渐变，盖在所有影像之上
5  .topbar   6  .copy-layer   7  .hud
```

**分镜层为什么嵌在 `.backdrop` 里面，而不是新开一层**：`z-index` **不接受小数**，
在 0 与 1 之间插不进新层；而把 layer 提到 1 之上又会盖住 stage。
放进 `.backdrop` 内部则完全不动 z 链 —— 「严格递增」这条断言（implement.md 校验项）无需改动。
配套约束：`.backdrop__scene` 必须是 `absolute`（`fixed` 会逃出 `.backdrop` 的包含块，
整块不再属于 z-index 0），这一点有专门的断言 + 反向验证。

**关键差异（v1 → v2）**：main stage 里**没有 poster**。v1 用三层 poster 按 beat 交叉淡入做缺失兜底，那会让背景随板块变化，与当时的「背景恒定」冲突。现在 main 缺失时直接露出 `.backdrop` —— 恒定墙面 + 随板块变化、位置各异的文案，正是用户要的效果。

> **v6 补充**：分镜层在 `.backdrop` 内部随 `data-copy` 切换，与 stage 层是两回事，
> 所以「main stage 里没有 poster」这条**依然成立**，没有被 v6 改回去。

---

## 4. 三段状态机

滚动进度 `p` 是唯一输入，三个 stage 的 `opacity` 是唯一输出。

```
segmentOf(p):
  p <= INTRO_AT (0.002)  → 'intro'
  p >= OUTRO_AT (0.98)   → 'outro'
  否则                    → 'main'

opacity 写入（仅在与上次不同时写，避免每帧触发样式重算）：
  intro   = (segment === 'intro') ? 1 : 0
  main    = (segment === 'intro') ? 0 : 1        // p > 0 起即为 1，含 [0.98, 1]
  outro   = (segment === 'outro') ? 1 : 0
```

- `0.98 ≤ p ≤ 1` 区间 main 保持 `opacity: 1`（停在最后一帧），outro 淡入叠在其上 —— 对应 PRD 验收 9。
- CSS 统一 `transition: opacity .5s ease` → 对应验收 10，无硬切。
- intro 与 outro 同为 z-index 2，main 为 1；因 intro/outro 互斥、且只有 outro 需要盖住 main，顺序天然正确。

**文案跟随 beat**：`copy` 的激活项由 `p` 换算，**不读视频状态**，因此视频缺失时仍准确切换：
```
beatIndex = p <= INTRO_AT (0.002) ? 'intro'
          : p >= OUTRO_AT (0.98)  ? 2                // 收尾沿用最后一段画面
          : beatIndexAt(p)                           // 见下
```

**节奏点用比例，不用绝对秒数**（v2 修正）。`CONFIG.beatCuts = [0.30, 0.70]`：
```
[0, .30) 作品文件夹   [.30, .70) 作品预览   [.70, 1] 无限可能
```
v1 写的是绝对秒数 `[0-9][9-21][21-30]`，那是**与「主视频恰好 30 秒」焊死的**。真素材
一换成 10 秒，「无限可能」就永远进不去（`t` 到不了 21），而且**不报错、只静默少一段**。
`p` 本身已是归一化进度，所以比例写法对任何时长都成立 —— 且对 30 秒的兜底情形，
两套写法给出完全相同的分段。回归断言见 `showcase_check.js` 的「与时长无关」四条。

> 素材到位后仍要按**实拍内容**重校这三个分界值：比例只保证「三段铺满全长」，
> 不保证「分界正好落在画面转场上」。

---

## 5. 滚动 → 进度 → seek（防抖核心）

### 5.1 进度

```js
maxScroll = document.documentElement.scrollHeight - window.innerHeight
p         = maxScroll > 0 ? clamp(window.scrollY / maxScroll, 0, 1) : 0
```
滚动监听器只置 `scrollDirty = true`，**不做任何布局读取** —— 避免 scroll 事件里强制同步布局导致掉帧；每帧最多读一次 `scrollY`（且在 dirty 时才读）。

### 5.2 阻尼 seek

写 `currentTime` 的频率必须被压住，否则每帧一次 seek 会拖垮解码器。核心是**不读回 `video.currentTime` 做控制**（seek 在途时读回的是旧值，会引发来回振荡），而是用自己维护的 `applied` 变量。

```js
let applied = 0;                                  // 我们最后一次写进去的值
const target = p * duration;

const diff = target - applied;
if (Math.abs(diff) <= SEEK_DEADZONE) {            // 0.02s
  if (applied !== target) { applied = target; writeSeek(applied); }   // 收敛到精确值
} else {
  let step = diff * EASE;                         // 0.18，指数逼近
  if (Math.abs(step) > MAX_STEP) step = Math.sign(step) * MAX_STEP;  // 0.35s/帧 上限
  applied += step;
  writeSeek(applied);
}

function writeSeek(t) {
  if (main.readyState >= 2 /* HAVE_CURRENT_DATA */) main.currentTime = t;
  else pendingSeek = t;                           // 未就绪则挂起，canplay 时补写
}
```

- `applied !== target` 判断让**静止时零写入**，滚动停止后不再有任何 seek。
- 倒放（`diff < 0`）走完全相同的代码路径，`currentTime` 递减即可，无需特判 —— 对应验收 7。

### 5.3 就绪与首帧

- `loadedmetadata` → 拿到真实 `duration`，重算 `.scroll-track` 高度（`duration × 100vh`）；此前用 `CONFIG.fallbackDuration` 兜底，**页面从一开始就可滚动**。
- `canplay` → 补写 `pendingSeek`。
- **首帧 nudge**：`loadeddata` 后写一次 `currentTime = 0.001`，强制解码器吐出第一帧，否则部分浏览器在未 seek 前显示黑帧。

---

## 6. 素材缺失容错（当前默认路径）

两路 `<video>` 的 `src` 指向尚不存在的 mp4 时，浏览器在元素上触发 `error`：

```
video.addEventListener('error', () => stage.classList.add('is-missing'));
```

`is-missing` 时视频层 `opacity: 0`，**下层的 poster / backdrop 自然露出**。这套「poster 垫在视频下面」的叠放顺序带来一个额外好处：**不需要任何 JS 分支**。

v2 下的表现：
- **main 缺失** → 露出 `.backdrop` 恒定墙面，文案照常随板块切换并改变落位（验收 19）
- **intro 缺失** → 露出 `intro-loop.jpeg` 静态人物
- **outro 本来就无视频** → 一直是 `beat-3.jpeg`

---

## 7. 首屏鼠标擦洗（v2 核心交互）

v1 的「整体平移视差」已废弃。现在鼠标位置**直接驱动 intro 视频的时间轴**。

```js
mx01 = e.clientX / innerWidth          // 0 .. 1  横向
my01 = e.clientY / innerHeight         // 0 .. 1  纵向

// 横向 → 时间轴
introTarget  = (CONFIG.intro.invert ? 1 - mx01 : mx01) * introDuration;
introApplied += (introTarget - introApplied) * CONFIG.intro.ease;   // 0.12 阻尼
if (Math.abs(introTarget - introApplied) < 0.01) introApplied = introTarget;
if (intro.readyState >= 2) intro.currentTime = introApplied;

// 纵向 → 极小的画面位移，做触感反馈
--py = (my01 - 0.5) * CONFIG.intro.tiltY                              // ±8px
```

- **不播放、不循环**：进入 scrub 模式时 `intro.pause()` 并移除 `loop`。鼠标静止 → `currentTime` 不变、画面静止在对应帧（验收 12）。
- **回退**：`(hover: none)` 触屏、或 `prefers-reduced-motion` 时**不进入 scrub 模式**，改为 `intro.play()` + `loop` 自动循环（验收 13）—— 否则移动端首屏会完全死住。

### 7.1 离开首屏「回正」（v3）

v2 在这一步只是**停止写** `currentTime`。后果是人物僵在鼠标最后指到的那个朝向淡出，
看着像卡住了 —— 用户要的是**主动回到初始朝向**，再交给下一段。

```js
// 每帧：目标由 seg 决定，不再是「在首屏才写」
it = (seg === 'intro' && mouseMoved) ? introTarget() : introResetTime();
ie = (seg === 'intro') ? CONFIG.intro.ease : CONFIG.intro.resetEase;

introApplied += (it - introApplied) * ie;
if (Math.abs(it - introApplied) < 0.008) introApplied = it;

if (readyState >= 2 && shouldWriteIntro(seg, introApplied, introWritten, resetT)) {
  intro.currentTime = introApplied;
  introWritten = introApplied;
}
```

四处要害：

1. **`mouseMoved` 门**：鼠标一次都没动过时也走回正分支 → 人物保持初始朝向**待机**，
   而不是一进页面就停在画面正中那一帧（`mx01` 初值 0.5 会映射到片中）。
2. **`shouldWriteIntro` 抽成纯函数**：两条纪律互相拉扯 —— 「值没变就不写」（鼠标静止、
   回正完成后零写入，与 main 的 `applied` 对称）与「回正最后一帧的精确值必须写进去」。
   后者曾因判据在 snap **之后**求值而永远为假，画面停在离初始帧 ~6ms 处。
   抽出来是为了让这两条都能被断言钉住，而不是靠人再读一遍。
3. **`resetEase` (0.26) 与 `ease` (0.12) 分开**：回正必须落在 `0.5s` 淡出**内**才看得见。
   60fps 下 30 帧是硬上限 —— 用跟手阻尼回正 10s 素材要 42 帧，淡出结束时人物还差一截
   没转回来。0.26 降到 24 帧收敛 / 18 帧肉眼中性，且能撑到 30s 的素材。
4. **`resetAt` 可配**：中性朝向在素材的哪一帧由实拍决定，不写死为 0。复用
   `mouseToIntroTime(resetAt, dur, false)` 算，所以它和鼠标映射共用同一套已测过的钳制逻辑。

**回正与淡出是重叠的，不是先后**。严格「先回正完、再开始淡出」要 0.4s + 0.5s = 0.9s，
而这段时间里 main 视频已经随滚动在身后推进了 —— 用户会觉得滚动和画面脱节。
所以取重叠：人物一边转回中性、画面一边淡出。若确实要严格串行，把 `.stage` 的
`transition-delay` 加在 intro 的淡出上即可，代价是每次开始滚动的响应都晚 0.4s。

**映射轴的假设**：默认按「线性横向扫视」实现（横向鼠标 = 完整时间轴）。若真实素材是 **3×3 朝向网格**（九宫格九个朝向），需要改成 `(row, col)` 索引取帧，改动集中在 `CONFIG.intro` 与这一段的 4 行映射代码。素材到位后按实拍重调。

---

## 8. iOS Safari 三个坑

| 坑 | 处理 |
| --- | --- |
| 无用户手势时不允许解码/播放 | 首个 `pointerdown` / `touchstart` / `wheel` 里做一次 `main.play().then(() => main.pause())` "点火"，解锁后续 seek 渲染 |
| 视频会强制全屏播放 | 两张 `<video>` 一律 `playsInline` + `muted` + `preload="auto"` |
| 同时解码多路视频资源紧张 | 只有当前 segment 的视频处于播放态；main **永不 autoplay**（只被 seek）。outro 无视频，全页最多 1 路解码 |

---

## 9. 设计令牌（只还原 `示例.jpg` 的文字排版）

```css
:root {
  --ink:      #EDE7DC;   /* 奶白，全站文字色 */
  --ink-dim:  rgba(237, 231, 220, .72);
  --bg-deep:  #2E362F;   /* 暗青灰，背景图未加载时的底色 */
  --accent:   #E8A33D;   /* 暖沙金，仅用于 eyebrow / 进度条 / CTA */
  --font-display: Impact, "Haettenschweiler", "Arial Narrow Bold",
                  "Franklin Gothic Bold", "Arial Black", sans-serif;
  --font-body: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
}
```

- **刻意不引外部字体**：`Impact` 在 Windows / macOS 均自带，本身就是压缩重体，最接近参考图气质；外链 Google Fonts 会引入网络依赖与 FOUT，与「双击 `index.html` 就能打开」冲突。
- **全站无 `#000` / `#fff`** —— 对应验收 3。参考图靠「暗色影像 + 暖白字 + 单点暖金」立住，纯黑纯白会立刻拉低质感。
- **只取排版，不取背景**：参考图的背景是一帧视频画面 + 左侧压暗渐变，这两者的处理方式**不采用**；但压暗渐变本身**保留原样**（用户决定，它服务文字可读性）。

### 排版比例（四段通用）

| 槽位 | 规格 |
| --- | --- |
| eyebrow | `--font-body` / `12px` / `uppercase` / `letter-spacing .18em` / `--accent` |
| 主标题 | `--font-display` / `clamp(...)` / `line-height .88` / `uppercase` / `--ink` / 硬换行 2–3 行 |
| 描述 | `--font-body` / `15px` / `line-height 1.9` / `--ink-dim` |
| CTA | 药丸形描边 `1px solid var(--ink)` + 圆形箭头 icon，仅首屏出现 |

### 文案落位（v2：避让视频构图）

由 `.copy[data-pos]` 决定，CSS 只写三种位置的映射：

| `data-pos` | 落位 | 用在 |
| --- | --- | --- |
| `left` | 左侧垂直居中 | 首屏、节奏 1（主体都在右侧） |
| `top` | 上部靠左 | 节奏 2（三张卡片居中占满中下部） |
| `bottom` | 左下角 | 节奏 3（人物居中、碎片向上飞散） |

**改位置只改 HTML 上的 `data-pos` 值，不碰 CSS。**

### 响应式 `≤ 720px`

双栏**堆叠为单列**：文案占满横向（`left/right: var(--gut)`），主标题由 `clamp()` 缩小，纵向落位差异保留；顶部导航隐藏、`SCROLL TO EXPLORE` 隐藏（触屏无鼠标，提示无意义）；鼠标擦洗关闭、intro 回退为自动循环。

---

## 10. 可测性设计（无浏览器也能验）

`showcase.js` 必须是**传统脚本**（`<script src>`，非 `type="module"`）—— ES module 在 `file://` 下会被 CORS 拦截，"双击打开"就废了。

为了在不启动浏览器的前提下验证进度映射（验收 6/8/9），文件尾部加一个无害的双环境守卫：

```js
if (typeof document !== 'undefined') init();          // 浏览器才初始化 DOM
if (typeof module !== 'undefined') module.exports = { segmentOf, beatIndexAt, progressToTime };
```

所有 DOM 访问都收在 `init()` 内，顶层只做纯函数定义与 `CONFIG` 声明。

> **注意**：`frontend/package.json` 是 `"type": "module"`，该目录下的 `.js` 会被 node 当成 ESM，`require` 抛 `ERR_REQUIRE_ESM`。测试要用 `vm` 以经典脚本方式求值（详见 implement.md 步骤 5）。

---

## 11. 取舍记录

| 决策 | 取舍 |
| --- | --- |
| ~~背景恒定（v2）~~ **已被 v6 推翻** | 放弃 v1「三张分镜交叉淡入」的丰富度，换取「背景不动、只有内容在变」的稳定感 —— 这是用户明确要的。代价：没有 mp4 时画面运动感全靠文案落位变化 |
| 裁切派生 `bg-wall.jpeg` | 新增了一个图片文件，但避免了「人物重影」这个致命观感问题。若你更希望零新增文件，可改回用 `background-position` 在分镜图上取值，但需要针对每张图调参、更脆 |
| **逐节背景用整张分镜图（v6）** | 用户明确选择，代价是接受「分镜里的人物与 main 视频里的人物重影」。**并且只要 `main.mp4` 到位，分镜层在四个主体段会被视频完全盖住** —— 这个冲突已上报，未擅自反转层序 |
| **分镜层嵌进 `.backdrop`（v6）** | `z-index` 不收小数，插不进 0 与 1 之间。嵌进去换来「z 链零改动」，代价是 `.backdrop__scene` 必须守 `absolute` 这条纪律（`fixed` 会静默逃逸），故补了一条断言 + 一条反向验证 |
| **作品文件夹用整图内页（v6）** | 弹出效果最干净，但 `beat-2.jpeg` 里的卡片文字是**位图**，打破 v5 锁定的「卡片必须是可选中真文本」。缓解：原文保留在 `.sr-only` 里（可搜索、可读屏），且这条放宽在 checker 里是**显式写明**的，不是事后追认 |
| **下坠由滚动进度驱动而非一次性动画（v6）** | 可逆（倒着滚会原样升回去）、静止时零写入，符合本项目「进度是唯一输入」的一贯纪律。代价：不能用 CSS `animation`，得自己算曲线 |
| 拨盘曲线 `easeInCubic` 而非线性（v6） | 前段慢后段快 = 「坠」的体感。注意 `y` 从 −1 升到 0，位移值是**单调递增**的（层在往下掉、数值在往上爬），方向极易写反，套件里专门有一条单调性断言 |
| 鼠标擦洗（v2） | 放弃 intro 的自动循环，换得「头部真的跟着鼠标转」。代价：触屏与 reduced-motion 必须走回退分支，两条代码路径都要维护 |
| 阻尼而非直接赋值 `currentTime` | 完全跟手但逐帧 seek 会卡；阻尼牺牲约 0.15s 的跟随延迟换取平滑 —— 验收 6 已为此留出「一帧内阻尼误差」 |
| poster 垫在视频下方 | 牺牲首屏解码前的一点点可见延迟，换来「零分支」的缺失容错 |
| 移动而非复制分镜图 | 仓库不存两份 2MB；若你希望 `assets/` 保留原件，从 git 历史取回即可 |
| 波纹用 canvas 2D 而非 WebGL 折射（v4） | 折射（真扭曲画面）观感更「水」，但 `file://` 下 WebGL 读本地图片会抛 `SecurityError`，直接丢掉「双击即开」；且全屏视频每帧重新采样会和擦洗 rAF 抢帧预算。改用加色细环：不读像素、不依赖 GPU 特性，且「黑色拖尾」在结构上不可能发生 |
| 波纹画布随光标移动而非全屏（v4） | 全屏画布在 4K + DPR2 下是 3300 万像素的 backing store。改成 560×560 跟随光标，栅格量降低两个数量级，同时「影响范围小」这件事由几何尺寸**强制**成立，而不是靠参数自觉 |
| 环境波纹场**无状态**（v4） | 每帧由 `r` 与 `t` 直接解出波前半径，不保存任何历史。代价：无法做「拖尾/回声」类效果；收益：不可能累积残留 —— 这正是「去掉黑色拖尾」最根本的那条保证 |
| 边缘软遮罩只在有点击环时施加（v4） | 环境场永远以光标为心，几何上不可能越界，无需遮罩；只有被光标位移拖走的点击环需要。省掉空闲时每帧一次 1120² 的渐变填充 |

---

## 12. 鼠标波纹层（v4）

### 12.1 为什么加在「影像之上」而不是 `.backdrop` 上

用户原话是「在背景上新增」，但实测三个 stage 全是 `position: fixed; inset: 0`、内部 `object-fit: cover` / `background-size: cover`：

| 进度 | 实际画面 | `.backdrop` 可见 |
| --- | --- | --- |
| `p = 0` | `.stage--intro` 的 poster + 视频，满屏 | 否 |
| `0 < p < 0.98` | `.stage--main` 的 main.mp4，满屏 | **仅当 main.mp4 缺失** |
| `p ≥ 0.98` | `.stage--outro` 的 beat-3.jpeg，满屏 | 否 |

即：墙面**只有中间一段可见**，而且 `main.mp4` 一到位就永远不可见。所以波纹层必须盖在影像之上才始终成立。经确认取**影像之上、文字之下**。

### 12.2 层级重排

`z-index` 不接受小数，而 `.stage--intro/--outro` 已经占了 2。用 DOM 顺序去打破同层平级太脆，所以给波纹层单独腾一格，薄纱顺延：

| 层 | z-index | 变化 |
| --- | --- | --- |
| `.backdrop`（v6 起内含 `.backdrop__scene` 逐节背景，整块仍占 0） | 0 | — |
| `.stage--main` | 1 | — |
| `.stage--intro` / `.stage--outro` | 2 | — |
| `.scrim`（薄纱） | **3** | 由 4 改为 3（v5 对调） |
| **`.ripple`** | **4** | 由 3 改为 4（v5 对调） |
| `.topbar` | 5 | — |
| `.copy-layer` | 6 | — |
| `.hud` | 7 | — |

**波纹必须在薄纱之上**（v5 对调，理由与 v4 写的相反）：

v4 写的是「薄纱是给文字让出对比度的压暗层；波纹若盖在它上面，等于把文字的可读性
交给一个跟着鼠标跑的动效去负责」。**那句话把薄纱当成了文字层，是错的** ——
薄纱只是对**影像**的一层处理，属于「影像」那一侧；真正要护的文字在 `z-index` 6，
波纹无论在 3 还是 4 都够不到它。而薄纱左侧压暗到 82% 不透明，波纹压在它下面
会被吃掉约 5 倍亮度，**光标常去的左半侧恰好最暗**。所以波纹应当在薄纱之上。

整条链已改成**一次性断言严格递增**（`showcase_dom_check.js`），
防止将来往中间插一层时把谁挤到错的一侧。

### 12.3 画布几何 —— 「影响范围小」由尺寸强制

```
maskR  = influence + maskPad      = 160 + 120 = 280
canvas = 2 × maskR                = 560 × 560 CSS px
backing = 560 × dprCap(2)         = 1120 × 1120 ≈ 5 MB
```

画布 `position: fixed; top:0; left:0`，每帧 `transform: translate3d(x − maskR, y − maskR, 0)` 跟随光标。**波纹半径上限与画布尺寸绑死**，写错参数也不可能溢出成全屏动效。

`.ripple` 自身带 `transform` 是安全的 —— 它是叶子节点，没有 `position: fixed` 的后代，不触发 §1-2 那个包含块陷阱。

### 12.4 环境波纹场：无状态波前

相位取**对数**形式，波前半径由 `φ = 2πk + ωt` 反解：

```
φ(r) = K · ln(1 + r/r0)
r_k  = r0 · (exp((2πk + ωt) / K) − 1)
```

好处是**环距随半径线性增长**：

```
s(r) = dr/dφ · 2π = 2π(r0 + r) / K
```

取 `r0 = 64`、`K = 25`（由「近处 s ≈ 16px、可见 5 圈」两条条件解出）：

| | 环距 | 说明 |
| --- | --- | --- |
| `r = 0`（光标处） | **16.0 px** | 细 |
| `r = 160`（影响边界） | **56.1 px** | 疏 |

可见圈数 `= K·ln(1 + influence/r0) / 2π = 5.0`。**「靠近鼠标的波纹更细」不是调出来的观感，是 `s'(r) = 2π/K > 0` 这个不等式**，可以直接断言。

每帧从 `phase = (ωt) mod 2π` 起枚举 `k`，`r_k ≤ influence` 为止。`phase` 走满一圈时外圈掉出边界、内圈从圆心生成 —— 两者都在包络零点附近，故无跳变。

**描边宽度**同样随半径线性增厚，近处最细：

```
w(r) = widthNear + (widthFar − widthNear) · r / influence      // 0.8px → 2.0px
```

**包络**负责「影响范围」与收边：

```
u    = r / influence
env  = (1 − u²)²          // env(0)=1，env(1)=0，[0,1] 上单调不增
```

### 12.5 点击环：有状态、有限寿命

`pointerdown` 生成 `clickRings = 2` 个环，启动时刻错开 140ms：

```
τ     = now − t0 − delay
r(τ)  = influence · easeOutCubic(clamp(τ/clickLife, 0, 1))
α(τ)  = clickAlpha · env(r(τ)/influence) · (1 − τ/clickLife)²
```

`r(clickLife) = influence` ⟹ `env = 0` ⟹ `α = 0`。**寿命终点与包络零点重合**，所以环必然死透，不需要「超时兜底」。`maxRings = 24` 封顶，超出丢最旧的，内存有界。

### 12.6 「去掉黑色拖尾」的四条保证

| # | 保证 | 为什么它管用 |
| --- | --- | --- |
| 1 | `globalCompositeOperation = 'lighter'` | 加色混合只加亮。结构上无法产生比背景更暗的像素 |
| 2 | 每帧 `clearRect(0, 0, S, S)` 全清 | 不残留上一帧。反馈缓冲式拖尾的根因就是不清屏 |
| 3 | 环境场无状态 | 每帧从 `r`、`t` 直接解出，没有可累积的历史量 |
| 4 | 点击环有限寿命 + 包围零点 | 环集合必然收敛到空，且寿命与半径同时到界 |

第 3、4 条合起来给出一个很强的可断言命题：**停止输入后模拟 300 帧，总 alpha 必须严格等于 0**。

### 12.7 边缘软遮罩

环境场永远以光标为心，几何上不可能越界。只有点击环会被光标位移拖走 —— 快速甩动鼠标时，环心可能被拖到画布边缘附近，环本身还有半径，于是被画布边界**硬切**出一道直线。

所以在有点击环存活时才追加一次遮罩：

```js
ctx.globalCompositeOperation = 'destination-in';
ctx.fillStyle = edgeMask;            // 白到透明，0 → influence/influence+maskPad 之后才开始淡
ctx.fillRect(0, 0, S, S);
```

无点击环时**跳过**这一笔 —— 空闲时省掉每帧一次 1120² 的渐变填充。

### 12.8 生效门槛

与首屏擦洗同一套判断，保持一致：

| 条件 | 行为 |
| --- | --- |
| `prefers-reduced-motion: reduce` | 不创建画布 |
| `hover: none`（触屏） | 不创建画布（没有悬停指针，效果无意义） |
| `document.hidden` | 停 rAF |
| 指针未进入过窗口 | 不渲染（不知道位置） |
| 指针离开窗口 / 窗口失焦 | 全局淡出到 0，然后**停 rAF** |

### 12.9 每条要求 → 可断言量

| 用户要求 | 实现量 | 断言 |
| --- | --- | --- |
| 缩小影响范围 | `influence = 160`；`env(u) = (1−u²)²` | `env(0)=1`、`env(1)=0`、`[0,1]` 单调不增 |
| 靠近鼠标的波纹更细 | `s(r) = 2π(r0+r)/K`；`w(r)` 线性增厚 | `s(0) < s(influence)` 严格；`w(0) ≤ 1.2` 且 `w` 单调增 |
| 点击时向外扩散 | 2 环错开 140ms，`easeOutCubic` 到 `influence` | `r(clickLife) = influence`；`α(clickLife) = 0` |
| 去掉黑色拖尾 | 加色 + 全清 + 无状态 + 有限寿命 | 停输入后 300 帧总 alpha **严格为 0**；环数 ≤ `maxRings` |

### 12.10 为什么单开一个 `ripple.js`

`showcase.js` 已经承担状态机 + 滚动 seek + 鼠标擦洗三件事。波纹是**正交**的一层：它不读滚动进度、不改任何 stage、不需要 `showcase.js` 的任何内部量。分成两个传统脚本各跑自己的 rAF，比塞进同一个循环更好测 —— 附带的纯函数测试文件可以独立加载它，不必构造 `showcase.js` 的整套 DOM 依赖。

代价是页面上有两个 rAF。空闲时波纹循环会**主动停掉自己**，而擦洗循环本来就在跑，所以稳态开销不增加。

---

## 13. 逐节背景 + 两个交互（v6）

### 13.1 分镜层：复用 `data-copy` 的键空间

分镜层用 `data-scene` 作键，值与 `data-copy` **同一套编号**（`0` 个人简历 / `1` 作品文件夹 / `3` 无限可能）：

```js
var sceneEls = {};
Array.prototype.forEach.call(document.querySelectorAll('[data-scene]'), function (el) {
  sceneEls[el.dataset.scene] = el;
});
var dropEl = document.querySelector('[data-scene][data-drop]');
var dropSpan = sectionSpans()[CONFIG.beatCuts.length];
```

复用一个键空间意味着**不需要第二张映射表**：显隐完全跟着已经算好的 `copyKey` 走，
在既有的 `copyKey !== lastCopyKey` 分支里加一个循环即可：

```js
for (var s in sceneEls) {
  if (Object.prototype.hasOwnProperty.call(sceneEls, s)) {
    setClass(sceneEls[s], 'is-active', s === copyKey);
  }
}
setFolderOpen(false);          /* 换节即把文件夹合回去 */
```

**反过来说，这也是一条硬约束**：`data-scene` 只能取 `data-copy` 里真实存在的值。
若写了一个不存在的键（比如 `2`），该层**永远不会 `is-active`** —— 页面上什么都不会发生，
但「层存在」「图能解析」这些断言依然全绿。所以套件里断言的是**集合相等**
（恰好 3 层、键集合恰为 `{0,1,3}`、无重复），而不是「至少有几层」。

`2` 与收尾段没有分镜层，落到 `.backdrop` 的恒定底图 —— 这是**设计**，不是遗漏。

### 13.2 下坠：`sceneDropY(p, span)`

```js
function sceneDropY(p, span) {
  if (!span) return 0;
  var w = (span[1] - span[0]) * CONFIG.sceneDrop.dropSpan;   /* 下落只占该节前 35% */
  if (!(w > 0)) return 0;                                    /* 退化区间：起==止 / 起>止 */
  var u = clamp((p - span[0]) / w, 0, 1);
  var k = u * u * u;                                         /* easeInCubic */
  return CONFIG.sceneDrop.from * (1 - k);                    /* from = -1 → 整层在视口上方 */
}
```

几何：`from = -1` 表示「整体移到视口上方，刚好完全不可见」，落点是 **0**。
`dropSpan = 0.35` 表示该节走完 35% 时图就位，之后 65% 静止 —— 图贴在那里不抖。

三个必须写对的地方：

1. **落点必须是精确 0，不是「趋近 0」。** `(1 - k)` 在 `u = 1` 时 `k = 1`，结果严格 `0`。
   若写成 `+ (k >= 1 ? 1e-9 : 0)` 之类的「软化」，层会永远停在亚像素偏移上 ——
   波纹停机判据踩过同一个坑（§12）。反向验证里专门有一条把落点改成「趋近 0」，
   会同时打红 **5** 条断言。
2. **位移值是单调递增的，不是递减。** 层在往下掉，数值却从 `-1` **爬升**到 `0`。
   写成「单调不增」是最容易犯的错，所以单调性断言单独列一条，并把「倒着滚原样升回」
   写进标签里。
3. **`u` 必须 `clamp`。** 进度在节前为负、节后大于 1，不钳位会让层飞出视口。

这段是**纯函数**，和 `segmentOf` / `beatIndexAt` 一样导出给套件直接验，
不需要构造 DOM：`module.exports = { ..., sceneDropY: sceneDropY }`。

### 13.3 文件夹开合状态机

结构上只有两个互斥的按钮，都带 `data-folder-toggle`：

```
.folder__deck                     ← pointer-events: auto（唯一的命中区）
├── button.folder__cover          ← folder.png，合着
└── button.folder__page           ← beat-2.jpeg，内页整图
```

开合由 `.folder.is-open` 一个类驱动，两个按钮各自的 `opacity / visibility / transform`
在这个类下互换。**弹出感**来自非对称的两条曲线：展开用
`cubic-bezier(.34, 1.56, .64, 1)`（>1 的过冲，先冲过头再回弹），收起用普通 `ease`。
`visibility` 不能忘：它跟着 `opacity` 走，但 **transition 延迟必须与透明度时长一致**
（`visibility 0s linear var(--fade)` 这类写法），否则隐藏瞬间无法被点中、或显示瞬间不可见。

状态复位有两处，缺一不可：

- 换节时 `setFolderOpen(false)` —— 否则「封面 → 内页」只有第一次成立，
  离开再回来会直接停在内页上。反向验证里删掉这一行会打红。
- 合上时把焦点还给封面 —— 否则键盘用户点 Enter 收起后，焦点留在一个
  `visibility: hidden` 的按钮上，等于焦点丢失。

### 13.4 点击区域：v5 那个真缺陷

v5 把点击监听挂在**整屏面板**（`inset: 0`）上，于是：

- 面板 `pointer-events: auto` + `z-index 6` > 顶栏 `z-index 5` ⇒ **顶栏可见但点不动**；
- 点 `folder.png` 本身反而被当成「点空白」把面板关了 —— 与提示文案自相矛盾。

v6 的修法是把命中区收窄到真正的交互元素：`.copy--panel` 设 `pointer-events: none`，
只给 `.folder__deck` 和 `.folder__close` 开 `auto`；空白关闭的监听挂在 `.folder__deck` 上，
并且先判 `closest('[data-folder-toggle]')` 直接返回。**`pointer-events` 是可继承属性**，
这一点是「顶层设 none、子元素按需开 auto」这套写法能成立的原因。

配套：卡片原文放进 `.sr-only`（clip + `clip-path: inset(50%)`），
并且**必须放在 `.folder__deck` 之外** —— 否则它会继承 `pointer-events: auto`，
变成一块看不见但能点中的区域。

### 13.5 每条要求 → 可断言量

| 用户要求 | 实现量 | 断言 |
| --- | --- | --- |
| 三个板块各有背景 | `data-scene` 键集合 `{0,1,3}`，各带 `--scene:url(media/…)` | 恰好 3 层、键集合**相等**（不是 `size >=`）、无重复、每层都有非空 `--scene` |
| 分镜层不破坏 z 链 | 嵌在 `.backdrop` 内，`.backdrop__scene { position: absolute }` | CSS 里是 `absolute` 不是 `fixed`；基态无 `transform`；z 链仍严格递增 |
| 无限可能背景下坠 | `sceneDropY`，`easeInCubic`，`from = -1` | 节起点整层在视口上方；时间过半只落 12.5%（前段慢）；落点精确 0；落点后仍 0；全区间单调递增；有界于 `[from, 0]` |
| 弹出过渡效果 | 展开 `cubic-bezier(.34,1.56,.64,1)`，收起 `ease` | 两条贝塞尔都在 CSS 里；`aria-expanded` 双态；换节复位 |
| 卡片文字不丢 | `.sr-only` 段落保留三段原文 | 三个项目名都在 `.sr-only` 内；`.sr-only` 规则在 CSS 里；且**位于 `pointer-events: auto` 容器之外** |
| 顶栏仍可点 | `.copy--panel { pointer-events: none }` | 断言 + 反向验证（改回 `auto` 会复现劫持） |

### 13.6 已知冲突（未解决，已上报）

`.stage--main` 是 `position: fixed; inset: 0` 且视频 `object-fit: cover`，
一旦 `main.mp4` 到位，它在四个主体段里**铺满整个视口**，
`.backdrop` 连同里面的分镜层会被完全盖住 —— 用户要求的三张逐节背景**只在 `main.mp4` 缺失时可见**。

这不是可以靠调整参数绕开的，是「分镜层在影像之下」这个层序的必然结果。
反转层序（让分镜层盖住视频）是另一个决策：那等于放弃 main 视频在主体段的可见性。
**已如实报给用户，等其决定**，未擅自反转。
