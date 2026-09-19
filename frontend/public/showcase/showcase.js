/* ══════════════════════════════════════════════════════════════════════
   Biaoge. 滚动叙事作品集 — 交互

   滚动进度 p ∈ [0,1] 是唯一输入；p × main.duration = main.currentTime。
   首屏（p === 0）另有一条输入：鼠标横向位置 → intro.currentTime。

   三条不准违反的规则：
   1) 不从 main.currentTime 读回控制量。seek 在途时读回的是旧值，会引发
      来回振荡。只信自己维护的 applied。intro 同理，用 introApplied。
   2) 本文件必须是传统脚本（<script src>），不能写成 ES module ——
      module 在 file:// 下会被 CORS 拦截，"双击打开"就废了。
   3) 视频/图片路径只写在 index.html 里，本文件一个路径都不含。
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* ── 调参区：节奏时间点、缓动、擦洗映射 ─────────────────────────────────
   视频/图片路径在 index.html 里，不在这里。 */
var CONFIG = {
  /* main 元数据到位前的兜底时长（秒）。页面总高度 = 该值 × 100vh。 */
  fallbackDuration: 30,

  /* 四个节奏点的分界（占全长比例），对应参考视频的五节导航：
        intro        初次见遇
        [_,  .30)    个人简历      BIOGRAPHY
        [.30, .54)   作品文件夹    WORK       ← 整屏面板
        [.54, .86)   作品预览      PREVIEW
        [.86, _]     无限可能      BEYOND
     三个分界 → 四个节，加上 intro 正好五项，与 .topbar__nav 的五个 tab
     一一对应（节的序号 = tab 的下标）。

     刻意用比例而非绝对秒数。用秒数的话，这段代码就与「主视频恰好是 30 秒」
     这个假设焊死了 —— 换成 10 秒的素材，「无限可能」会永远进不去
     （t 到不了 21），而且不会有任何报错，只会静默少一段。
     p 本身已经是归一化进度，所以比例写法对任何时长都成立。
     真素材到位后按实拍内容重校这三个分界值即可。 */
  beatCuts: [0.30, 0.54, 0.86],

  introAt: 0.002,      /* p <= 此值 → intro 段（首屏，鼠标擦洗） */
  outroAt: 0.98,       /* p >= 此值 → outro 段（静态图淡入叠在 main 末帧上） */

  seekDeadzone: 0.02,  /* 秒。差距小于它就直接收敛，不再阻尼 */
  ease: 0.18,          /* 阻尼系数，越大越跟手、越小越顺滑 */
  maxStep: 0.35,       /* 单帧最大推进秒数，防止快速滚动时一次跳太远 */

  /* 首屏鼠标擦洗（v2 核心交互）。
     真实素材的拍法若与「线性横向扫视」不符（例如 3×3 朝向网格），
     把 mode 改成 'loop' 即可整体退回自动循环，不用动别处。 */
  intro: {
    mode:            'scrub',  /* 'scrub' | 'loop'（强制自动循环） */
    invert:          false,    /* true = 鼠标越靠左越接近片尾 */
    ease:            0.12,     /* 跟手阻尼，越大越跟手 */

    /* ── 离开首屏时「回正」────────────────────────────────────────────
       滚轮一旦把 p 推出首屏，鼠标立即交出控制权，人物主动回到初始
       朝向，再淡出、由下一段接管。不这么做的话，人物会僵在鼠标最后
       指到的那个朝向淡出，看着像卡住了。 */
    resetEase:       0.26,     /* 回正阻尼。比跟手快：要落在 0.5s 淡出内。
                                  0.22 时 10s 素材要 29 帧/30 帧，等于坐在临界点
                                  上；0.26 降到 24 帧，且能撑到 30s 的素材 */
    resetAt:         0,        /* 回正到哪一帧（占总长比例）。0 = 片头。
                                  若素材的中性朝向其实在片中，改这里 */

    tiltY:           8,        /* 纵向微位移幅度(px)，纯触感反馈 */
    fallbackDuration: 5        /* intro 元数据到位前的兜底时长(秒) */
  }
};

/* ══ 纯函数（无 DOM 依赖，可在 node 里直接断言） ═══════════════════════ */

function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

/** 滚动进度 → 生效段 */
function segmentOf(p) {
  if (p <= CONFIG.introAt) return 'intro';
  if (p >= CONFIG.outroAt) return 'outro';
  return 'main';
}

/** 滚动进度 → 主视频时间（秒） */
function progressToTime(p, duration) {
  return clamp(p, 0, 1) * duration;
}

/** 滚动进度 → 第几个节奏点（0 起）。只吃 p —— p 已是归一化进度，
    所以这个映射与视频时长完全无关（见 CONFIG.beatCuts 的说明）。 */
function beatIndexAt(p) {
  var cuts = CONFIG.beatCuts;
  for (var i = 0; i < cuts.length; i++) if (p < cuts[i]) return i;
  return cuts.length;                /* 收尾沿用最后一段画面 */
}

/** 秒 → "mm:ss" */
function formatTime(sec) {
  var s = Math.max(0, Math.floor(sec));
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' +
         String(s % 60).padStart(2, '0');
}

/**
 * 滚动进度 → 分节刻度在滑轨上的位置（0..1）。
 * 取自 beatCuts，不另写一份 —— 导航、HUD 序号、刻度必须同源，
 * 否则改了分节却没改刻度，刻度会静默错位。
 */
function sectionTicks() {
  return CONFIG.beatCuts.slice();
}

/**
 * 每一节的进度区间 [[起, 止], ...]，不含首屏。
 * 首屏是 [0, introAt]，四节依次接在三个分界之间，最后一节到 outroAt ——
 * outroAt 之后是收尾段，画面沿用最后一节的文案。
 */
function sectionSpans() {
  var cuts = CONFIG.beatCuts;
  var spans = [];
  var prev = CONFIG.introAt;
  for (var i = 0; i < cuts.length; i++) { spans.push([prev, cuts[i]]); prev = cuts[i]; }
  spans.push([prev, CONFIG.outroAt]);
  return spans;
}

/**
 * 第 i 个导航节（0 = 首屏）该滚到哪个进度。
 *
 * 取该节前 25% 处，而不是节的起点：起点恰在分界线上，
 * 滚轮差一点点就会滑回上一节，导航会「点了没反应」。
 * 25% 让落点稳稳落在节内，右边也留出整节的余量给人往下滚。
 *
 * 现算而不写死在 data-goto 上：分节一改落点必须跟着改，
 * 写死只会在改 beatCuts 时静默把某一节指错，且不报错。
 */
function sectionTarget(i) {
  if (i <= 0) return 0;
  var spans = sectionSpans();
  var s = spans[i - 1];
  if (!s) return 1;
  return s[0] + (s[1] - s[0]) * 0.25;
}

/**
 * 鼠标归一化位置 → 八向视线读数。
 *
 * 为什么要自己算方位：intro-loop.mp4 是一段**连续转头**的动画，
 * 不是二维朝向网格，所以没有「第几行第几列」可以直接查；
 * 方位只能从鼠标位置反推。
 *
 * 分档用「角度八分」而不是「横竖各三档」：后者会出现
 * 「LOOKING UP CENTER」这种既别扭又不齐整的标签。
 * 八分加一个正中的死区，读数恰好是「LOOKING AT YOU」。
 *
 * 注意 y 轴向下为正（屏幕坐标系），所以 90° 是 DOWN 而不是 UP ——
 * 这跟数学习惯相反，是最容易写反的一处，已单独断言。
 *
 * @param x01  鼠标横向归一化位置 0..1
 * @param y01  鼠标纵向归一化位置 0..1
 * @param dead 正中死区半径（归一化），缺省 0.14
 */
var GAZE_LABELS = [
  'LOOKING RIGHT',      /*   0° */
  'LOOKING DOWN RIGHT', /*  45° */
  'LOOKING DOWN',       /*  90° */
  'LOOKING DOWN LEFT',  /* 135° */
  'LOOKING LEFT',       /* 180° */
  'LOOKING UP LEFT',    /* 225° */
  'LOOKING UP',         /* 270° */
  'LOOKING UP RIGHT'    /* 315° */
];

function gazeLabel(x01, y01, dead) {
  var dx = clamp(x01, 0, 1) - 0.5;
  var dy = clamp(y01, 0, 1) - 0.5;
  var r  = Math.sqrt(dx * dx + dy * dy);
  if (r < (dead === undefined ? 0.14 : dead)) return 'LOOKING AT YOU';
  var deg = Math.atan2(dy, dx) * 180 / Math.PI;          /* -180..180 */
  var i   = Math.round(((deg + 360) % 360) / 45) % 8;
  return GAZE_LABELS[i];
}

/**
 * 首屏该不该把 introApplied 写进 currentTime（v3 回正的门条件）。
 * 抽成纯函数是因为「回正收干净后必须停写」与「最后一帧精确值必须写进去」
 * 这两条互相拉扯 —— 后者曾经因为条件在 snap 之后求值而被漏掉。
 * 现在这两条都被断言锁住了，改坏了会红。
 *
 * @param seg          'intro' | 'main' | 'outro'
 * @param introApplied 本帧算出的目标时间
 * @param introWritten 上次真正写进去的值（未写过传 null）
 * @param resetT       回正帧
 */
function shouldWriteIntro(seg, introApplied, introWritten, resetT) {
  if (introApplied === introWritten) return false;      /* 值没变 → 零写入 */
  if (seg === 'intro') return true;                     /* 首屏 → 持续跟手 */
  /* 离开首屏 → 一直写到回正彻底收干净（两个值都落在 resetT 上）为止 */
  return !(introApplied === resetT && introWritten === resetT);
}

/**
 * 鼠标横向归一化位置 → intro 时间（秒）。
 * 抽成纯函数是因为首屏擦洗是本页最核心的交互，而它恰恰是最难在
 * 无浏览器环境下验证的一处 —— 这样至少映射本身可以被断言。
 *
 * 留 0.04s 余量：部分浏览器 seek 到恰好 duration 会返回黑帧。
 */
function mouseToIntroTime(x01, duration, invert) {
  var x   = invert ? 1 - clamp(x01, 0, 1) : clamp(x01, 0, 1);
  var max = Math.max(0, duration - 0.04);
  return clamp(x * max, 0, max);
}

/* ══ 运行时 ═══════════════════════════════════════════════════════════ */

function init() {
  var docEl  = document.documentElement;
  var noop   = function () {};
  var body   = document.body;

  var track    = document.querySelector('[data-scroll-track]');
  var hud      = document.querySelector('.hud');
  var hudFill  = document.querySelector('[data-hud-fill]');
  var hudNum   = document.querySelector('[data-hud-num]');
  var hudLbl   = document.querySelector('[data-hud-label]');
  var hudTime  = document.querySelector('[data-hud-time]');
  var hudTot   = document.querySelector('[data-hud-total]');
  var hudTrack = document.querySelector('[data-hud-track]');
  var hudKnob  = document.querySelector('[data-hud-knob]');

  var hero     = document.querySelector('[data-hero]');
  var gazeEl   = document.querySelector('[data-gaze]');
  var pauseBtn = document.querySelector('[data-toggle-interaction]');
  var folderEl = document.querySelector('.folder');

  var stages = {
    intro: document.querySelector('[data-stage="intro"]'),
    main:  document.querySelector('[data-stage="main"]'),
    outro: document.querySelector('[data-stage="outro"]')
  };
  var introInner = stages.intro && stages.intro.querySelector('.stage__inner');

  var videos = {
    intro: document.querySelector('video[data-role="intro"]'),
    main:  document.querySelector('video[data-role="main"]')
  };

  var copyEls = {};
  Array.prototype.forEach.call(document.querySelectorAll('.copy'), function (el) {
    copyEls[el.dataset.copy] = el;
  });

  var navTabs = Array.prototype.slice.call(document.querySelectorAll('.topbar__tab'));

  /* ── 输入模式：有精确指针才做鼠标擦洗 ────────────────────────────────
     触屏 (hover: none) 与 prefers-reduced-motion 一律退回自动循环，
     否则首屏会完全死住（验收 13 / 23）。 */
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var scrubMode = CONFIG.intro.mode === 'scrub' &&
                  window.matchMedia('(hover: hover) and (pointer: fine)').matches &&
                  !reducedMotion;

  /* ── 状态 ────────────────────────────────────────────────────────── */
  var duration      = CONFIG.fallbackDuration;  /* 秒；loadedmetadata 后换成真值 */
  var introDuration = CONFIG.intro.fallbackDuration;
  var progress      = 0;
  var applied       = 0;      /* 最后一次写进 main.currentTime 的值 */
  var introApplied  = -1;     /* intro 的目标时间；-1 = 未初始化 */
  var introWritten  = null;   /* 最后一次真正写进 intro.currentTime 的值 */
  var pendingSeek   = null;   /* main 没就绪时挂起的 seek */
  var scrollDirty   = true;

  var mx01 = 0.5, my01 = 0.5; /* 鼠标归一化位置 */
  var mouseMoved = false;     /* 鼠标动过之前，人物保持初始朝向待机 */
  var py = 0, tpy = 0;
  var interactionPaused = false;  /* 「暂停互动」按下的状态 */

  var lastSeg = null, lastCopyKey = null;
  var lastFill = null, lastTime = null, lastScrolled = null;
  var lastPyW = null, lastKnob = null, lastTot = null, lastGaze = null;

  /* ── 工具：只在值真的变了才写 DOM ─────────────────────────────────── */
  function setText(el, s) {
    if (el && el.textContent !== s) el.textContent = s;
  }
  function setClass(el, cls, on) {
    if (el) el.classList.toggle(cls, on);
  }

  /* ── 页面高度 = main 时长 × 100vh ─────────────────────────────────── */
  function layoutTrack() {
    if (track) track.style.height = (duration * 100) + 'vh';
    scrollDirty = true;
  }

  function computeProgress() {
    var max = docEl.scrollHeight - window.innerHeight;
    if (max <= 0) return 0;
    return clamp(window.scrollY / max, 0, 1);
  }

  /* ── seek 写入 ───────────────────────────────────────────────────── */
  function writeSeek(t) {
    var v = videos.main;
    if (!v) return;
    /* HAVE_CURRENT_DATA 之前写入会被忽略，挂起等 canplay 补写 */
    if (v.readyState >= 2) { v.currentTime = t; pendingSeek = null; }
    else { pendingSeek = t; }
  }

  /* ── 播放态：同一时刻至多一段在播 ───────────────────────────────────
     intro 只在「自动循环模式 + 互动未暂停 + 正在首屏」三个条件同时成立时
     才播；其余一律停住。擦洗模式天然落在「不播」那一支，不需要单列分支。 */
  function syncPlayback(seg) {
    var vi = videos.intro, vm = videos.main;
    var introShouldPlay = !scrubMode && !interactionPaused && seg === 'intro';

    if (introShouldPlay) {
      if (vi && vi.paused) { var pr = vi.play(); if (pr && pr.catch) pr.catch(noop); }
    } else if (vi && !vi.paused) {
      vi.pause();
    }

    /* main 永不 autoplay —— 只被 seek，从不 play */
    if (vm && !vm.paused) vm.pause();
  }

  /* ── 首屏：鼠标位置 → intro.currentTime ───────────────────────────── */
  function introTarget() {
    return mouseToIntroTime(mx01, introDuration, CONFIG.intro.invert);
  }

  /* 回正到的那一帧。复用同一个映射函数，所以 resetAt=0 就是片头，
     resetAt=0.5 就是片中 —— 中性朝向在哪儿由素材决定，不写死。 */
  function introResetTime() {
    return mouseToIntroTime(CONFIG.intro.resetAt, introDuration, false);
  }

  /* ── 每帧工作 ────────────────────────────────────────────────────── */
  function applyFrame() {
    if (scrollDirty) { scrollDirty = false; progress = computeProgress(); }

    /* 1) main 阻尼 seek —— 不读回 currentTime，只信 applied。
          这里**故意不留**片尾余量（首屏的 mouseToIntroTime 留了 0.04s）：
          两条路径的不对称是有理由的，不是疏漏。
            · 首屏擦洗时鼠标推到最右，末帧就是画面本体，必须避开黑帧；
            · main 的末段被 outro 从 p >= 0.98 起整段盖住，末帧根本看不见。
          曾经为「对称」在这里加过 tailGuard，代价是 HUD 的时间码取自
          applied、而 formatTime 用 Math.floor —— duration 为整数时
          页底会稳定显示「00:29 / 00:30」，是个必然可见的错。
          用一个看不见的隐患换一个看得见的错，不划算，已撤掉。 */
    var target = progressToTime(progress, duration);
    var diff   = target - applied;
    if (Math.abs(diff) <= CONFIG.seekDeadzone) {
      if (applied !== target) { applied = target; writeSeek(applied); }
    } else {
      var step = diff * CONFIG.ease;
      if (Math.abs(step) > CONFIG.maxStep) step = (step < 0 ? -1 : 1) * CONFIG.maxStep;
      applied += step;
      writeSeek(applied);
    }

    /* 2) 分段与透明度（只在与上次不同时写 class，避免每帧触发样式重算） */
    var seg = segmentOf(progress);
    if (seg !== lastSeg) {
      lastSeg = seg;
      setClass(stages.intro, 'is-active', seg === 'intro');
      setClass(stages.main,  'is-active', seg !== 'intro');   /* [outroAt,1] 仍亮，停末帧 */
      setClass(stages.outro, 'is-active', seg === 'outro');
      /* 首屏那四块附加文案与左栏主标题同属首屏，必须一起进退 ——
         它们各自带 0.5s 淡出，与 .copy 同一套节奏。 */
      setClass(hero, 'is-active', seg === 'intro');
      syncPlayback(seg);
    }

    /* 3) 节奏点 → 文案 / 导航 / 序号。只由 p 换算，不读视频状态，
          因此 mp4 缺失时文案照样准确切换。 */
    var beat = (seg === 'intro') ? -1
             : (seg === 'outro') ? CONFIG.beatCuts.length
             : beatIndexAt(progress);
    var copyKey = (beat < 0) ? 'intro' : String(beat);

    if (copyKey !== lastCopyKey) {
      lastCopyKey = copyKey;
      for (var k in copyEls) {
        if (Object.prototype.hasOwnProperty.call(copyEls, k)) {
          setClass(copyEls[k], 'is-active', k === copyKey);
        }
      }

      var segIndex = (beat < 0) ? 0 : beat + 1;
      var tab = navTabs[segIndex];
      for (var j = 0; j < navTabs.length; j++) setClass(navTabs[j], 'is-active', j === segIndex);
      /* 序号从 01 起（参考视频首屏就是 01，不是 00），而节的下标从 0 起 ——
         显示必须 +1。这一位之差和 beat/section 的换算叠在一起，最容易漏。 */
      setText(hudNum, String(segIndex + 1).padStart(2, '0'));
      /* 英文取自导航标签的 data-en，与它旁边的中文同源：
         另写一份的话，改导航忘了改 HUD，两处会静默不一致。 */
      if (tab) {
        setText(hudLbl, (tab.dataset.en ? tab.dataset.en + ' ' : '') + tab.textContent.trim());
      }
    }

    /* 4) 首屏：在首屏时鼠标擦洗；离开首屏则主动回正到初始朝向
          （v3）。只在 intro 段写入会与 main 的滚动驱动打架，所以两件事
          都收在这一个分支里，由 seg 决定目标。 */
    if (scrubMode && videos.intro) {
      var resetT = introResetTime();

      /* 跟手要同时满足三条：在首屏、鼠标动过、互动没被暂停。
         第三条（v5 新增）复用「回正」这一支，而不是另写一套：
         暂停互动时人物回到中性朝向定住，与离开首屏时的收尾是同一个动作。
         鼠标一次都没动过时也走这一支 —— 人物保持初始朝向待机，
         而不是一进页面就停在画面正中那一帧。 */
      var following = (seg === 'intro' && mouseMoved && !interactionPaused);
      var it = following ? introTarget() : resetT;
      var ie = following ? CONFIG.intro.ease : CONFIG.intro.resetEase;

      if (introApplied < 0) introApplied = it;
      introApplied += (it - introApplied) * ie;
      if (Math.abs(it - introApplied) < 0.008) introApplied = it;

      /* 该不该写 —— 见 shouldWriteIntro 的说明。鼠标停住、或回正收干净后
         就零写入，与 main 的 applied 同一纪律。 */
      if (videos.intro.readyState >= 2 &&
          shouldWriteIntro(seg, introApplied, introWritten, resetT)) {
        videos.intro.currentTime = introApplied;
        introWritten = introApplied;
      }

      /* 纵向只做极小位移，给「跟手」一点触感（横向才是真正的时间轴）。
         离开首屏同样归零，和回正一起收。 */
      tpy = following ? (my01 - 0.5) * CONFIG.intro.tiltY : 0;
      py += (tpy - py) * CONFIG.intro.ease;
      if (Math.abs(tpy - py) < 0.02) py = tpy;

      if (introInner) {
        var wy = py.toFixed(2);
        if (wy !== lastPyW) { lastPyW = wy; introInner.style.setProperty('--py', wy + 'px'); }
      }
    }

    /* 5) 首屏视线读数。只在「首屏 + 鼠标动过 + 未暂停」时跟随鼠标 ——
          其余情况一律写回正中读数：那时人物正回正到片头的中性朝向，
          读数必须和画面一致，不能停在最后一次跟手的方位上。 */
    var gazeOn = (seg === 'intro' && mouseMoved && !interactionPaused);
    var g = gazeOn ? gazeLabel(mx01, my01) : 'LOOKING AT YOU';
    if (g !== lastGaze) { lastGaze = g; setText(gazeEl, g); }

    /* 6) HUD */
    var fill = progress.toFixed(4);
    if (fill !== lastFill) {
      lastFill = fill;
      if (hudFill) hudFill.style.transform = 'scaleX(' + fill + ')';
      /* 滑块走的是滑轨的百分比宽度，与 fill 的 scaleX 同一根轴；
         左移 3.5px 由 CSS 的负 margin 负责，这里只管位置。 */
      if (hudKnob) hudKnob.style.left = (progress * 100).toFixed(2) + '%';
    }

    /* 时间码显示**当前段自己的**时间轴：首屏是 intro 的，其余是 main 的。
       参考视频首屏写的就是这一屏在放的那条时间轴（00:00 / 00:10），
       不是全站那条 —— 首屏画面上根本没有 main 的视频。 */
    var shown, total;
    if (seg === 'intro') {
      /* 这里读回 currentTime 是**显示**，不是控制量，与规则 1 不冲突：
         自动循环模式下 intro 在自由播放，introApplied 根本不更新，
         只有视频自己的时钟知道现在放到第几秒。 */
      shown = scrubMode ? Math.max(0, introApplied)
                        : (videos.intro ? videos.intro.currentTime : 0);
      total = introDuration;
    } else {
      shown = applied;
      total = duration;
    }

    var t = formatTime(shown);
    if (t !== lastTime) { lastTime = t; setText(hudTime, t); }

    var tot = formatTime(total);
    if (tot !== lastTot) { lastTot = tot; setText(hudTot, tot); }

    var scrolled = progress > CONFIG.introAt;
    if (scrolled !== lastScrolled) { lastScrolled = scrolled; setClass(hud, 'is-scrolled', scrolled); }
  }

  function loop() {
    applyFrame();
    requestAnimationFrame(loop);
  }

  /* ── 事件接线 ────────────────────────────────────────────────────── */

  window.addEventListener('scroll', function () { scrollDirty = true; }, { passive: true });
  window.addEventListener('resize', function () { scrollDirty = true; }, { passive: true });
  window.addEventListener('orientationchange', function () { scrollDirty = true; }, { passive: true });

  /* 视口/track 高度变化时重算进度（移动端地址栏收起等） */
  if (window.ResizeObserver) {
    new ResizeObserver(function () { scrollDirty = true; }).observe(document.body);
  }

  window.addEventListener('pointermove', function (e) {
    if (!scrubMode) return;
    mx01 = clamp(e.clientX / window.innerWidth,  0, 1);
    my01 = clamp(e.clientY / window.innerHeight, 0, 1);
    mouseMoved = true;      /* 首次移动后，人物才开始跟手 */
  }, { passive: true });

  /* iOS：没有用户手势就解码不出来。首个手势里点火一次。
     擦洗模式下不能让 intro 真的播起来，只点火 main。 */
  var unlocked = false;
  function unlock() {
    if (unlocked) return;
    unlocked = true;
    if (!scrubMode && videos.intro) {
      var ip = videos.intro.play();                 /* 与本文件另外三处对齐 */
      if (ip && ip.catch) ip.catch(noop);
    }
    if (videos.main) {
      var pr = videos.main.play();
      if (pr && pr.then) pr.then(function () { videos.main.pause(); }).catch(noop);
    }
  }
  ['pointerdown', 'touchstart', 'wheel', 'keydown'].forEach(function (ev) {
    window.addEventListener(ev, unlock, { passive: true });
  });

  /* ── 跳到第 i 节 ───────────────────────────────────────────────────
     落点由 sectionTarget() 从 CONFIG.beatCuts 现算，HTML 上只写「第几节」。
     写死进度值的话，改分节就会静默把某一节指错，而且不报错。 */
  function goToSection(i) {
    var max = docEl.scrollHeight - window.innerHeight;
    if (max <= 0) return;
    window.scrollTo({ top: sectionTarget(i) * max,
                      behavior: reducedMotion ? 'auto' : 'smooth' });
  }

  /* 任何带 data-section 的东西点了都跳到那一节 —— 顶部导航的五个标签，
     以及首屏那个 CTA。CTA 的 href="#work" 是死锚点（页面上没有 id="work"
     的元素），点了只往 URL 里塞个 hash、页面不动；这里统一接管并
     preventDefault，href 只留作无障碍语义。

     不要图省事直接复用 navTabs —— navTabs 还兼作 HUD 分节文案的来源，
     把 CTA 混进去会让 HUD 的序号/文案错位。 */
  Array.prototype.forEach.call(document.querySelectorAll('[data-section]'), function (el) {
    el.addEventListener('click', function (e) {
      var i = parseInt(el.dataset.section, 10);
      if (isNaN(i)) return;
      if (e && e.preventDefault) e.preventDefault();
      goToSection(i);
    });
  });

  /* ── 首屏输入模式的上线 ───────────────────────────────────────────── */
  function setupIntroMode() {
    var vi = videos.intro;
    setClass(body, 'is-scrub', scrubMode);
    if (!vi) return;

    if (scrubMode) {
      /* 摘掉 loop/autoplay 并停住：鼠标静止时画面必须定住不动（验收 12） */
      vi.pause();
      vi.loop = false;
      vi.removeAttribute('loop');
      vi.removeAttribute('autoplay');
    } else {
      vi.loop = true;
      var pr = vi.play();
      if (pr && pr.catch) pr.catch(noop);
    }
  }

  /* ── 分节刻度：由 CONFIG.beatCuts 生成 ─────────────────────────────
     与导航、HUD 序号同源。刻度是纯装饰，不进无障碍树。 */
  function buildTicks() {
    if (!hudTrack) return;
    sectionTicks().forEach(function (p) {
      var tick = document.createElement('i');
      tick.className = 'hud__tick';
      tick.setAttribute('aria-hidden', 'true');
      tick.style.left = (p * 100).toFixed(2) + '%';
      hudTrack.appendChild(tick);
    });
  }

  /* ── 暂停互动 ──────────────────────────────────────────────────────
     只暂停「互动」这一层（鼠标擦洗 / 首屏自动循环），不暂停滚动叙事 ——
     页面的推进始终归滚动管，关掉它是另一件事，不是这个按钮的职责。

     两个标签都取自 HTML：一个读按钮现成的文字，另一个读 data-paused-label。
     写在 JS 里的话，改文案要翻两个文件。 */
  var pauseIdleLabel = pauseBtn ? pauseBtn.textContent.trim() : '暂停互动';
  var pauseBusyLabel = (pauseBtn && pauseBtn.dataset.pausedLabel) || '继续互动';

  function setPaused(on) {
    if (interactionPaused === on) return;
    interactionPaused = on;
    setClass(pauseBtn, 'is-paused', on);
    setText(pauseBtn, on ? pauseBusyLabel : pauseIdleLabel);
    /* 暂停会改变「首屏该不该播」，播放态必须立刻跟着走 */
    syncPlayback(lastSeg);
  }

  if (pauseBtn) {
    pauseBtn.addEventListener('click', function () { setPaused(!interactionPaused); });
  }

  /* ── 作品文件夹面板的收起 ──────────────────────────────────────────
     三条入口（收起按钮 / ESC / 点空白处）都汇到 closePanel。
     面板是 data-copy="1"，即节下标 2（节下标 = beat + 1），收起后去下一节。 */
  var folderSection = (folderEl && !isNaN(parseInt(folderEl.dataset.copy, 10)))
                    ? parseInt(folderEl.dataset.copy, 10) + 2 : -1;

  function closePanel() {
    /* 只在面板真的在屏上时才动滚动 —— ESC 是全站按键，
       在别的节按一下不该把页面弹到作品预览去。 */
    if (!folderEl || !folderEl.classList.contains('is-active')) return;
    if (folderSection < 0) return;
    goToSection(folderSection);
  }

  if (folderEl) {
    var closeBtn = folderEl.querySelector('[data-close-panel]');
    if (closeBtn) closeBtn.addEventListener('click', function (e) {
      if (e && e.preventDefault) e.preventDefault();
      closePanel();
    });

    window.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' || e.key === 'Esc') closePanel();
    });

    /* 点空白处。卡片与收起按钮是「东西」，点它们不算点空白 ——
       用户点卡片多半是想选中文案。 */
    folderEl.addEventListener('click', function (e) {
      var t = e.target;
      if (t && t.closest && t.closest('.fcard, [data-close-panel]')) return;
      closePanel();
    });
  }

  /* ── 视频就绪 / 失败 ─────────────────────────────────────────────── */
  /* 拿真实时长、重算页面高度。元数据可能早于本脚本就绪（本地小 mp4 很常见），
     所以既挂事件，也在末尾补查一次 readyState。 */
  function readDuration() {
    var v = videos.main;
    if (!v) return;
    var d = v.duration;
    if (!isFinite(d) || d <= 0 || d === duration) return;
    duration = d;
    layoutTrack();
    /* 不在这里写 hudTot —— HUD 的总时长按当前段取值（首屏是 intro 的），
       由 applyFrame 独占，写两处必然互相覆盖。 */
    /* 换成真实时长后必须重算 applied：否则它会停在按兜底时长算出的越界旧值上，
       表现为刷新在页面中部时「先跳到末尾再倒回来」。 */
    applied = progressToTime(progress, duration);
    writeSeek(applied);
  }

  function readIntroDuration() {
    var vi = videos.intro;
    if (!vi) return;
    var d = vi.duration;
    if (!isFinite(d) || d <= 0 || d === introDuration) return;

    /* 与 readDuration() 对称：首次从兜底时长跨到真时长时，目标帧会整体改变
       （目标 = 比例 × 时长）。这一刻必须把 introApplied 吸附到按真时长算出的
       值上，否则鼠标明明没动、画面却自己滑一段 —— 而「鼠标静止 = 画面静止」
       正是验收 12。注意不能只判 introApplied < 0：首帧就已经把它初始化成
       非负了，那个条件永远不成立。 */
    var firstReal = (introDuration === CONFIG.intro.fallbackDuration);
    introDuration = d;
    if (introApplied < 0 || firstReal) {
      /* 与 applyFrame 的 following 同条件：暂停中也走回正，
         否则元数据恰好在暂停期间到位时，画面会先跳向鼠标再滑回来。 */
      introApplied = (mouseMoved && lastSeg === 'intro' && !interactionPaused)
                   ? introTarget() : introResetTime();
    }
  }

  if (videos.main) {
    videos.main.addEventListener('loadedmetadata', readDuration);

    videos.main.addEventListener('canplay', function () {
      if (pendingSeek === null) return;
      videos.main.currentTime = pendingSeek;
      pendingSeek = null;
    });

    /* 首帧 nudge：canplay 之前先写一个极小偏移，逼解码器吐出第一帧，
       否则部分浏览器在 seek 发生前显示黑帧（会盖住下面的 backdrop）。
       只对「目标就是 0」做，位置随后仍由 canplay 收敛回精确的 0。
       若 pendingSeek 已为 null（canplay 早于本脚本执行），画面已被浏览器画好，
       不需要也不能再动它。 */
    videos.main.addEventListener('loadeddata', function () {
      if (pendingSeek !== 0) return;
      videos.main.currentTime = 0.001;
    });

    if (videos.main.readyState >= 1) readDuration();   /* 事件可能已经错过 */
  }

  if (videos.intro) {
    videos.intro.addEventListener('loadedmetadata', readIntroDuration);
    if (videos.intro.readyState >= 1) readIntroDuration();
  }

  /* 素材缺失 → 让出位置，露出下层 poster / backdrop。无需其它容错分支。 */
  [videos.intro, videos.main].forEach(function (v) {
    if (!v) return;
    v.addEventListener('error', function () {
      var st = v.closest('.stage');
      if (st) st.classList.add('is-missing');
    });
  });

  /* ── 启动 ────────────────────────────────────────────────────────── */
  buildTicks();
  layoutTrack();
  setupIntroMode();

  /* 首帧就位：刷新在页面中部时不要从 0 开始动画 */
  progress = computeProgress();
  applied  = progressToTime(progress, duration);
  writeSeek(applied);

  applyFrame();
  loop();
}

/* ── 双环境守卫 ─────────────────────────────────────────────────────────
   浏览器里初始化 DOM；node 里只导出纯函数供断言（无浏览器也能验证
   进度映射与鼠标擦洗映射）。所有 DOM 访问都在 init() 内，所以 node
   加载不会碰到 document。

   注意本仓库 frontend/package.json 声明了 "type": "module"，Node 会把本文件
   当 ES module 解析（浏览器不受影响，package.json 只管 Node）。这种制式下
   不能用 export 语法（浏览器端必须保持传统脚本），而且 Node 还会注入一个
   module shim —— 写 module.exports 会被静默丢弃。所以两个出口都开：
   CJS 用 module.exports，任何 Node 制式都同时挂到 globalThis：

     node -e "require('./frontend/public/showcase/showcase.js'); \
       const m = globalThis.__showcase; console.log(m.segmentOf(0.5));"

   浏览器里 document 存在，走第一支并立刻 return，不往全局挂任何东西。
   （用 IIFE 是为了不新增全局变量 API。） */
(function () {
  var API = { CONFIG: CONFIG, segmentOf: segmentOf, progressToTime: progressToTime,
              beatIndexAt: beatIndexAt, formatTime: formatTime,
              mouseToIntroTime: mouseToIntroTime, shouldWriteIntro: shouldWriteIntro,
              sectionTicks: sectionTicks, sectionSpans: sectionSpans,
              sectionTarget: sectionTarget, gazeLabel: gazeLabel };

  if (typeof document !== 'undefined') { init(); return; }   /* 浏览器 */
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  if (typeof globalThis !== 'undefined') globalThis.__showcase = API;
})();
